from typing import Iterator, List, Union

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

import src.db as db_module
import src.memory as memory_module
from src.broker import ppi_broker


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Corre cada test contra una base SQLite descartable (`tmp_path/memory.db`)
    en vez de `data/memory.db`, sembrada con el mismo portafolio de ejemplo."""
    test_db_path = tmp_path / "memory.db"
    monkeypatch.setattr(db_module, "DB_PATH", test_db_path)
    monkeypatch.setattr(db_module, "_connection", None)
    monkeypatch.setattr(db_module, "_initialized", False)
    monkeypatch.setattr(memory_module, "_checkpointer", None)
    db_module.init_db()
    return {"db_path": test_db_path}


class FakeSnapshotTool:
    """Reemplazo mínimo de get_market_snapshot para tests deterministas (sin red)."""

    def __init__(self, snapshot: dict):
        self.snapshot = snapshot

    def invoke(self, _args, config=None):
        return self.snapshot


class FakeOverviewTool:
    """Reemplazo mínimo de get_market_overview para tests deterministas (sin red)."""

    def __init__(self, overview: list):
        self.overview = overview

    def invoke(self, _args, config=None):
        return self.overview


class FakeToolCallingLLM(GenericFakeChatModel):
    """Chat model falso para probar el camino de tool-calling real sin pegarle
    a ninguna API. Se le da, de antemano, la secuencia exacta de `AIMessage`
    (con o sin `tool_calls`) que debe devolver en cada paso del loop de
    `create_react_agent` — no interpreta el input en absoluto.
    """

    def bind_tools(self, tools, **kwargs):
        return self


def fake_llm(messages: List[Union[AIMessage, str]]) -> FakeToolCallingLLM:
    return FakeToolCallingLLM(messages=iter(messages))


@pytest.fixture
def no_llm(monkeypatch):
    """Fuerza a los tres agentes especialistas a su fallback por reglas (sin
    LLM), para que los tests de siempre sigan siendo gratis y determinísticos
    aunque haya una API key real en el entorno."""
    from src.agents import market_research, order_execution, portfolio_analysis

    monkeypatch.setattr(market_research, "get_llm", lambda: None)
    monkeypatch.setattr(order_execution, "get_llm", lambda: None)
    monkeypatch.setattr(portfolio_analysis, "get_llm", lambda: None)


class FakeBroker:
    """Reemplazo mínimo de PPIBroker para tests: en memoria, sin red ni PPI
    real. Mismo espíritu que FakeToolCallingLLM — nunca pega a una API real,
    ni siquiera de PPI."""

    def __init__(self, cash: float = 100_000.0, price: float = 100.0, positions=None):
        self.cash = cash
        self.price = price
        self.positions = positions or []
        self.sent_orders: List[tuple] = []

    def get_available_cash(self) -> float:
        return self.cash

    def get_portfolio(self):
        return self.positions

    def get_quote(self, ticker: str):
        return ppi_broker.Quote(ticker=ticker, price=self.price)

    def place_market_buy(self, ticker: str, quantity: int):
        order_id = f"FAKE-{len(self.sent_orders) + 1}"
        self.sent_orders.append((ticker, quantity))
        return order_id, {"fake": True}


@pytest.fixture
def fake_broker(monkeypatch) -> FakeBroker:
    """Reemplaza `ppi_broker.get_broker` por un `FakeBroker` controlable —
    ninguna tool de portafolio/compra toca la red ni PPI real durante los
    tests."""
    broker = FakeBroker()
    monkeypatch.setattr(ppi_broker, "get_broker", lambda: broker)
    return broker


@pytest.fixture
def opportunity_snapshot():
    return {
        "ticker": "AAPL",
        "last_price": 100.0,
        "change_pct": -1.2,
        "fifty_day_avg": 120.0,
        "two_hundred_day_avg": 110.0,
        "year_low": 98.0,
        "year_high": 200.0,
        "source": "Yahoo Finance",
    }
