"""Agente de research de mercado.

Con LLM disponible: un agente LangChain real (`create_react_agent`). El nodo
resuelve primero qué datos hacen falta —snapshot de un ticker puntual, o un
panorama de varias acciones principales si el cliente no mencionó ninguna en
particular— y se los da al agente como contexto ya resuelto; el agente no
vuelve a llamar a esas tools él mismo (evita pegarle dos veces a Yahoo Finance
por el mismo dato) y solo se ocupa de redactar la respuesta y, si corresponde,
de la tool `propose_pending_order`. El pre-fetch del nodo se invoca con el
mismo `config` que trae el callback de tracing, así que igual queda visible
en la UI/consola como un tool-call real, aunque no lo dispare el LLM.

La heurística de oportunidad (`detect_opportunity`) se mantiene como función
Python pura — es un cálculo numérico determinístico, no un juicio para
dejarle a un LLM.

Variables macroeconómicas (inflación, dólar): mismo patrón de prefetch —
`extract_macro_indicator` resuelve por reglas qué indicador pidió el
cliente y el nodo llama a `get_macro_series` (ArgentinaDatos) antes de
invocar al agente, que solo redacta la respuesta a partir del dato (y el
gráfico ASCII) ya obtenido.

Sin LLM (modo offline / tests): se mantiene el comportamiento original por
reglas, armando la respuesta a mano a partir de los datos.
"""
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from src.agents.agent_utils import last_ai_text_message, new_messages_since, find_tool_result
from src.agents.registry import get_skill
from src.agents.triage import extract_ticker
from src.config import get_llm
from src.observability.tracing import with_node_name
from src.tools.macro_data import extract_macro_indicator, get_macro_series
from src.tools.market_data import detect_opportunity, get_market_overview, get_market_snapshot


def _overview_lines(overview: list) -> list:
    lines = ["Panorama de las principales acciones (Yahoo Finance):"]
    for item in overview:
        if item.get("error"):
            continue
        change = item.get("change_pct")
        change_txt = f"{'+' if (change or 0) >= 0 else ''}{change}%" if change is not None else "s/d"
        lines.append(f"  · {item['ticker']}: ${item['last_price']} ({change_txt})")
    lines.append('\n¿Querés el detalle de alguna en particular? Decime el ticker (ej: "cómo está AAPL").')
    return lines


def _snapshot_lines(snapshot: dict, opportunity) -> tuple:
    change = snapshot["change_pct"]
    change_txt = f"{'+' if (change or 0) >= 0 else ''}{change}%" if change is not None else "s/d"
    lines = [
        f"{snapshot['ticker']}: ${snapshot['last_price']} ({change_txt} hoy).",
        f"Promedio 50 días: ${snapshot['fifty_day_avg']} · Promedio 200 días: ${snapshot['two_hundred_day_avg']}.",
        f"Rango de las últimas 52 semanas: ${snapshot['year_low']} – ${snapshot['year_high']}.",
        "Fuente: Yahoo Finance.",
    ]
    pending_order = None
    if opportunity:
        lines.append(f"\nNoto una posible oportunidad: {opportunity}.")
        lines.append(
            f'¿Querés que evalúe comprar {snapshot["ticker"]}? Decime el ticker y la '
            f'cantidad (por ejemplo: "comprar 5 {snapshot["ticker"]}").'
        )
        pending_order = {
            "ticker": snapshot["ticker"],
            "status": "awaiting_details",
            "reference_price": snapshot["last_price"],
        }
    return lines, pending_order


def _macro_lines(macro: dict) -> list:
    return [
        f"{macro['title']}, últimos {len(macro['series'])} meses:",
        "```",
        macro["chart"],
        "```",
        f"Fuente: {macro['source']}.",
    ]


def _rule_based(state) -> dict:
    last_human = next((m for m in reversed(state["messages"]) if m.type == "human"), None)
    text = last_human.content if last_human else ""
    ticker = extract_ticker(text)
    macro_indicator = None if ticker else extract_macro_indicator(text)

    if macro_indicator:
        try:
            macro = get_macro_series.invoke({"indicator": macro_indicator})
        except Exception as exc:
            return {"messages": [AIMessage(content=f"No pude traer el dato macroeconómico ({exc}).")]}
        return {"messages": [AIMessage(content="\n".join(_macro_lines(macro)))]}

    if not ticker:
        try:
            overview = get_market_overview.invoke({})
        except Exception as exc:
            return {"messages": [AIMessage(content=f"No pude traer el panorama del mercado ({exc}).")]}
        return {"messages": [AIMessage(content="\n".join(_overview_lines(overview)))]}

    try:
        snapshot = get_market_snapshot.invoke({"ticker": ticker})
    except Exception as exc:  # yfinance sin red, ticker inválido, etc.
        return {"messages": [AIMessage(content=f"No pude traer datos de {ticker} en este momento ({exc}).")]}

    lines, pending_order = _snapshot_lines(snapshot, detect_opportunity(snapshot))
    return {"messages": [AIMessage(content="\n".join(lines))], "pending_order": pending_order}


def _build_agent(llm):
    skill = get_skill("market_research")
    return create_react_agent(llm, tools=skill.tools, prompt=skill.system_prompt)


@with_node_name("market_research")
def market_research_node(state, config=None):
    llm = get_llm()
    if llm is None:
        return _rule_based(state)

    last_human = next((m for m in reversed(state["messages"]) if m.type == "human"), None)
    text = last_human.content if last_human else ""
    ticker = extract_ticker(text)
    macro_indicator = None if ticker else extract_macro_indicator(text)
    opportunity = None

    if macro_indicator:
        try:
            macro = get_macro_series.invoke({"indicator": macro_indicator}, config=config)
        except Exception as exc:
            return {"messages": [AIMessage(content=f"No pude traer el dato macroeconómico ({exc}).")]}
        context = (
            f"El cliente preguntó por una variable macroeconómica ('{macro_indicator}'). "
            f"Dato ya obtenido (incluye el gráfico ASCII listo en el campo 'chart'): {macro}."
        )
    elif not ticker:
        try:
            overview = get_market_overview.invoke({}, config=config)
        except Exception as exc:
            return {"messages": [AIMessage(content=f"No pude traer el panorama del mercado ({exc}).")]}
        context = (
            "El cliente preguntó en general por el mercado, sin un ticker puntual. "
            f"Panorama ya obtenido: {overview}."
        )
    else:
        try:
            snapshot = get_market_snapshot.invoke({"ticker": ticker}, config=config)
        except Exception as exc:
            return {"messages": [AIMessage(content=f"No pude traer datos de {ticker} en este momento ({exc}).")]}
        opportunity = detect_opportunity(snapshot)
        context = (
            f"El cliente preguntó por un ticker puntual. Snapshot ya obtenido: {snapshot}. "
            + (
                f"Oportunidad detectada: {opportunity}."
                if opportunity
                else "No se detectó ninguna oportunidad particular para este ticker ahora."
            )
        )

    agent = _build_agent(llm)
    before = list(state["messages"])
    agent_input = {"messages": [SystemMessage(content=context), *before]}
    result = agent.invoke(agent_input, config=config)
    new_messages = new_messages_since(before, result["messages"])

    pending_order = state.get("pending_order")
    if opportunity:
        proposal = find_tool_result(new_messages, "propose_pending_order")
        if proposal:
            pending_order = proposal

    if macro_indicator:
        fallback = AIMessage(content="\n".join(_macro_lines(macro)))
    elif ticker:
        fallback = AIMessage(content=f"{snapshot['ticker']}: ${snapshot['last_price']}. Fuente: Yahoo Finance.")
    else:
        fallback = AIMessage(content="\n".join(_overview_lines(overview)))

    final_message = last_ai_text_message(new_messages) or fallback
    return {"messages": [final_message], "pending_order": pending_order}
