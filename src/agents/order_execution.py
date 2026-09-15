"""Agente de ejecución de órdenes.

Con LLM disponible: un agente LangChain real que interpreta el mensaje del
cliente (ticker, cantidad, si está confirmando) y actualiza la orden pendiente
llamando a la tool `propose_pending_order` — nunca la ejecuta él mismo. La
transición de estado que queda en `state["pending_order"]` se lee del propio
`tool_call` (no del texto libre de la respuesta), así sigue siendo
determinística y auditable.

Sin LLM (modo offline / tests): reglas originales por palabras clave.

Quien dispara la compra real es siempre el agente de compliance, una vez
que el estado pasa a "confirmed" (y solo para GGAL/YPF — ver
`src/broker/ppi_broker.py:REAL_TRADING_TICKERS`).
"""
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from src.agents.agent_utils import find_tool_result, last_ai_text_message, new_messages_since
from src.agents.registry import get_skill
from src.agents.triage import CONFIRM_WORDS, extract_quantity, extract_ticker, tokenize
from src.broker.ppi_broker import REAL_TRADING_TICKERS
from src.config import get_llm
from src.observability.tracing import with_node_name
from src.tools.market_data import get_market_snapshot


def _rule_based(state) -> dict:
    last_human = next((m for m in reversed(state["messages"]) if m.type == "human"), None)
    text = last_human.content if last_human else ""
    pending = dict(state.get("pending_order") or {})

    ticker = extract_ticker(text) or pending.get("ticker")
    qty = extract_quantity(text) or pending.get("qty")
    is_confirmation = bool(tokenize(text) & CONFIRM_WORDS)

    if not ticker:
        return {"messages": [AIMessage(content="¿Qué acción querés operar? Decime el ticker, por ejemplo AAPL.")]}

    if ticker not in REAL_TRADING_TICKERS:
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"La compra real todavía no está disponible para {ticker} — por ahora solo "
                        f"opero compras reales de {' y '.join(sorted(REAL_TRADING_TICKERS))}."
                    )
                )
            ],
            "pending_order": None,
        }

    if pending.get("status") == "ready" and qty and is_confirmation:
        pending.update({"ticker": ticker, "qty": qty, "status": "confirmed"})
        return {"pending_order": pending}

    if not qty:
        pending.update({"ticker": ticker, "status": "awaiting_details"})
        return {
            "messages": [AIMessage(content=f"¿Cuántas acciones de {ticker} querés comprar?")],
            "pending_order": pending,
        }

    price = pending.get("reference_price")
    if price is None:
        try:
            price = get_market_snapshot.invoke({"ticker": ticker})["last_price"]
        except Exception:
            price = None

    pending.update({"ticker": ticker, "qty": qty, "status": "ready", "reference_price": price})
    price_txt = f"${price}" if price is not None else "a confirmar"
    return {
        "messages": [
            AIMessage(
                content=(
                    f"Vas a comprar {qty} acciones de {ticker} (precio de referencia {price_txt}, "
                    "orden REAL a tu cuenta de PPI — el costo final se recalcula con la cotización "
                    "del momento). "
                    'Respondé "confirmo" para enviarla o "cancelar" para dejarla sin efecto.'
                )
            )
        ],
        "pending_order": pending,
    }


def cancel_node(state, config=None):
    return {
        "messages": [AIMessage(content="Listo, cancelé la operación pendiente.")],
        "pending_order": None,
    }


def _build_agent(llm):
    skill = get_skill("order_execution")
    return create_react_agent(llm, tools=skill.tools, prompt=skill.system_prompt)


@with_node_name("order_execution")
def order_execution_node(state, config=None):
    llm = get_llm()
    if llm is None:
        return _rule_based(state)

    pending = state.get("pending_order") or {}
    context = SystemMessage(
        content=f"Estado actual de la orden pendiente (puede estar vacío si no hay ninguna): {pending}."
    )

    agent = _build_agent(llm)
    before = list(state["messages"])
    result = agent.invoke({"messages": [context, *before]}, config=config)
    new_messages = new_messages_since(before, result["messages"])

    proposal = find_tool_result(new_messages, "propose_pending_order")
    pending_order = dict(pending)
    if proposal:
        pending_order.update({k: v for k, v in proposal.items() if v is not None})

    final_message = last_ai_text_message(new_messages) or AIMessage(
        content="¿Qué acción querés operar? Decime el ticker, por ejemplo AAPL."
    )
    return {"messages": [final_message], "pending_order": pending_order or None}
