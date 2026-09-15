"""Smoke tests del grafo completo: corren una conversación de punta a punta.

La mayoría fuerza el modo sin LLM (`no_llm`, reglas determinísticas) para
seguir siendo gratis y no depender de red/API real, incluso si hay una API
key real en el entorno. Un par de tests aparte (al final) ejercitan el camino
con LLM real usando un chat model falso (`FakeToolCallingLLM`) con
tool-calling scripteado — tampoco pegan a ninguna API.

El research de mercado se mockea siempre (`FakeSnapshotTool`) para no
depender de la cotización real del día.
"""
import json

from langchain_core.messages import AIMessage, HumanMessage

from src.agents import market_research, order_execution
from src.db import get_connection
from src.graph import build_graph
from src.message_utils import message_text
from tests.conftest import FakeOverviewTool, FakeSnapshotTool, fake_llm


def _run(app, config, text):
    return app.invoke({"messages": [HumanMessage(content=text)]}, config)


def _orders(db_path):
    return get_connection().execute("SELECT * FROM orders").fetchall()


def test_market_flow_asks_for_confirmation_on_opportunity(isolated_data, opportunity_snapshot, monkeypatch, no_llm):
    monkeypatch.setattr(market_research, "get_market_snapshot", FakeSnapshotTool(opportunity_snapshot))

    app = build_graph()
    config = {"configurable": {"thread_id": "test-1"}}
    result = _run(app, config, "¿cómo está AAPL?")

    assert result["intent"] == "mercado"
    assert result["pending_order"]["status"] == "awaiting_details"
    assert result["pending_order"]["ticker"] == "AAPL"


def test_full_purchase_flow_requires_explicit_confirmation(
    isolated_data, opportunity_snapshot, monkeypatch, no_llm, fake_broker
):
    monkeypatch.setattr(market_research, "get_market_snapshot", FakeSnapshotTool(opportunity_snapshot))

    app = build_graph()
    config = {"configurable": {"thread_id": "test-2"}}

    _run(app, config, "¿cómo está AAPL?")
    ready = _run(app, config, "comprar 5 GGAL")
    assert ready["pending_order"]["status"] == "ready"
    assert ready["pending_order"]["ticker"] == "GGAL"
    assert ready["pending_order"]["qty"] == 5

    # todavía no se ejecutó nada: no confirmamos
    assert _orders(isolated_data["db_path"]) == []

    confirmed = _run(app, config, "confirmo")
    assert confirmed["pending_order"] is None  # se ejecutó y se limpió

    orders_after = _orders(isolated_data["db_path"])
    assert len(orders_after) == 1
    assert orders_after[0]["ticker"] == "GGAL"
    assert orders_after[0]["qty"] == 5
    assert fake_broker.sent_orders == [("GGAL", 5)]


def test_purchase_flow_rejects_unsupported_ticker(isolated_data, opportunity_snapshot, monkeypatch, no_llm, fake_broker):
    monkeypatch.setattr(market_research, "get_market_snapshot", FakeSnapshotTool(opportunity_snapshot))

    app = build_graph()
    config = {"configurable": {"thread_id": "test-2b"}}

    _run(app, config, "¿cómo está AAPL?")
    result = _run(app, config, "comprar 5 AAPL")

    # nunca llega a "ready": se informa de entrada que no está disponible.
    assert result["pending_order"] is None
    ai_text = " ".join(message_text(m) for m in result["messages"] if m.type == "ai").lower()
    assert "no está disponible" in ai_text or "no esta disponible" in ai_text
    assert _orders(isolated_data["db_path"]) == []
    assert fake_broker.sent_orders == []


def test_cancel_flow_clears_pending_order(isolated_data, opportunity_snapshot, monkeypatch, no_llm):
    monkeypatch.setattr(market_research, "get_market_snapshot", FakeSnapshotTool(opportunity_snapshot))

    app = build_graph()
    config = {"configurable": {"thread_id": "test-3"}}

    _run(app, config, "¿cómo está AAPL?")
    result = _run(app, config, "cancelar")

    assert result["pending_order"] is None
    assert _orders(isolated_data["db_path"]) == []


def test_market_overview_when_no_specific_ticker(isolated_data, monkeypatch, no_llm):
    overview = [
        {"ticker": "AAPL", "last_price": 333.0, "change_pct": 0.2},
        {"ticker": "TSLA", "last_price": 250.0, "change_pct": -1.5},
    ]
    monkeypatch.setattr(market_research, "get_market_overview", FakeOverviewTool(overview))

    app = build_graph()
    config = {"configurable": {"thread_id": "test-overview-1"}}
    result = _run(app, config, "¿cómo vienen las principales acciones del mercado?")

    assert result["intent"] == "mercado"
    assert "pending_order" not in result or result["pending_order"] is None
    ai_text = " ".join(message_text(m) for m in result["messages"] if m.type == "ai")
    assert "AAPL" in ai_text and "TSLA" in ai_text


def test_portfolio_intent_routes_to_portfolio_agent(isolated_data, no_llm, fake_broker):
    app = build_graph()
    config = {"configurable": {"thread_id": "test-4"}}
    result = _run(app, config, "¿cómo va mi portafolio?")
    assert result["intent"] == "portafolio"
    last_ai = [m for m in result["messages"] if m.type == "ai"][-1]
    text = message_text(last_ai).lower()
    assert "efectivo disponible" in text or "demo educativa" in text


# -- Camino con LLM (tool-calling real, sin red) --------------------------


def test_llm_path_market_research_calls_propose_pending_order(
    isolated_data, opportunity_snapshot, monkeypatch
):
    monkeypatch.setattr(market_research, "get_market_snapshot", FakeSnapshotTool(opportunity_snapshot))
    monkeypatch.setattr(
        market_research,
        "get_llm",
        lambda: fake_llm(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "propose_pending_order",
                            "args": {
                                "ticker": "AAPL",
                                "status": "awaiting_details",
                                "reference_price": 100.0,
                                "qty": None,
                            },
                            "id": "call_1",
                        }
                    ],
                ),
                AIMessage(content="Veo una posible oportunidad en AAPL. ¿Cuántas querés evaluar comprar?"),
            ]
        ),
    )

    app = build_graph()
    config = {"configurable": {"thread_id": "test-llm-1"}}
    result = _run(app, config, "¿cómo está AAPL?")

    assert result["pending_order"]["status"] == "awaiting_details"
    assert result["pending_order"]["ticker"] == "AAPL"
    ai_texts = " ".join(message_text(m) for m in result["messages"] if m.type == "ai").lower()
    assert "oportunidad" in ai_texts


def test_llm_path_order_execution_confirms_and_compliance_executes(isolated_data, monkeypatch, fake_broker):
    monkeypatch.setattr(
        order_execution,
        "get_llm",
        lambda: fake_llm(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "propose_pending_order",
                            "args": {
                                "ticker": "GGAL",
                                "status": "confirmed",
                                "qty": 5,
                                "reference_price": 100.0,
                            },
                            "id": "call_1",
                        }
                    ],
                ),
                AIMessage(content="Listo, confirmé la compra de 5 GGAL."),
            ]
        ),
    )

    app = build_graph()
    config = {"configurable": {"thread_id": "test-llm-2"}}
    result = app.invoke(
        {
            "messages": [HumanMessage(content="confirmo")],
            "pending_order": {"ticker": "GGAL", "qty": 5, "status": "ready", "reference_price": 100.0},
        },
        config,
    )

    assert result["pending_order"] is None  # compliance la ejecutó y la limpió
    orders_after = _orders(isolated_data["db_path"])
    assert len(orders_after) == 1
    assert orders_after[0]["ticker"] == "GGAL"
    assert orders_after[0]["qty"] == 5
    assert fake_broker.sent_orders == [("GGAL", 5)]


def test_llm_path_compliance_rejects_unsupported_ticker_even_if_llm_confirms(isolated_data, monkeypatch, fake_broker):
    """Defensa en profundidad: aunque el LLM del agente de ejecución de
    órdenes se equivoque y confirme un ticker no soportado, `buy_stock` (el
    gate real, en compliance) lo rechaza sin tocar el broker."""
    monkeypatch.setattr(
        order_execution,
        "get_llm",
        lambda: fake_llm(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "propose_pending_order",
                            "args": {
                                "ticker": "AAPL",
                                "status": "confirmed",
                                "qty": 5,
                                "reference_price": 100.0,
                            },
                            "id": "call_1",
                        }
                    ],
                ),
                AIMessage(content="Listo, confirmé la compra de 5 AAPL."),
            ]
        ),
    )

    app = build_graph()
    config = {"configurable": {"thread_id": "test-llm-2b"}}
    result = app.invoke(
        {
            "messages": [HumanMessage(content="confirmo")],
            "pending_order": {"ticker": "AAPL", "qty": 5, "status": "ready", "reference_price": 100.0},
        },
        config,
    )

    assert result["pending_order"] is None
    assert _orders(isolated_data["db_path"]) == []
    assert fake_broker.sent_orders == []
