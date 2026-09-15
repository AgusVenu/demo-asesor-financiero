"""Tests de las tools: no dependen de un LLM, sólo de yfinance (red real) y de
un `fake_broker` (nunca PPI real) + la base SQLite aislada (`isolated_data`)
para portafolio/órdenes."""
import pytest

from src.db import get_connection
from src.tools.macro_data import extract_macro_indicator, get_macro_series
from src.tools.market_data import detect_opportunity, get_market_snapshot
from src.tools.portfolio import get_portfolio_summary
from src.tools.trading import buy_stock


def test_market_snapshot_shape():
    snapshot = get_market_snapshot.invoke({"ticker": "AAPL"})
    assert snapshot["ticker"] == "AAPL"
    assert isinstance(snapshot["last_price"], float)
    assert snapshot["source"] == "Yahoo Finance"


def test_detect_opportunity_flags_year_low():
    snapshot = {"last_price": 100, "fifty_day_avg": 120, "two_hundred_day_avg": 110, "year_low": 98, "year_high": 200}
    assert detect_opportunity(snapshot) is not None


def test_detect_opportunity_none_when_no_signal():
    snapshot = {"last_price": 150, "fifty_day_avg": 120, "two_hundred_day_avg": 110, "year_low": 50, "year_high": 200}
    assert detect_opportunity(snapshot) is None


def test_extract_macro_indicator_recognizes_inflacion_y_dolar():
    assert extract_macro_indicator("¿cómo viene la inflación?") == "inflacion"
    assert extract_macro_indicator("a cuánto está el dólar blue") == "dolar_blue"
    assert extract_macro_indicator("a cuánto está el dólar") == "dolar_oficial"
    assert extract_macro_indicator("cómo está AAPL") is None


def test_macro_series_inflacion_shape():
    data = get_macro_series.invoke({"indicator": "inflacion", "months": 6})
    assert data["indicator"] == "inflacion"
    assert data["source"].startswith("ArgentinaDatos")
    assert len(data["series"]) == 6
    assert isinstance(data["chart"], str) and data["chart"]


def test_macro_series_dolar_blue_is_monthly_aggregated():
    data = get_macro_series.invoke({"indicator": "dolar_blue", "months": 4})
    assert len(data["series"]) == 4
    meses = [item["mes"] for item in data["series"]]
    assert meses == sorted(meses)  # cronológico, sin duplicados por día


def test_macro_series_invalid_indicator_raises():
    with pytest.raises(ValueError):
        get_macro_series.invoke({"indicator": "no_existe"})


def test_portfolio_summary_has_positions(isolated_data, fake_broker):
    data = get_portfolio_summary.invoke({})
    assert "positions" in data and "cash_balance" in data
    assert data["cash_balance"] == fake_broker.cash


def test_buy_stock_rejects_unsupported_ticker_without_touching_broker(isolated_data, fake_broker):
    result = buy_stock.invoke({"ticker": "AAPL", "quantity": 5, "reference_price": 300.0})
    assert result["status"] == "rechazada"
    assert fake_broker.sent_orders == []  # nunca se llegó a cotizar/operar


def test_buy_stock_rejects_when_insufficient_cash(isolated_data, fake_broker):
    fake_broker.cash = 100.0
    result = buy_stock.invoke({"ticker": "GGAL", "quantity": 10_000, "reference_price": 300.0})
    assert result["status"] == "rechazada"
    assert fake_broker.sent_orders == []


def test_buy_stock_executes_and_records_order(isolated_data, fake_broker):
    result = buy_stock.invoke({"ticker": "GGAL", "quantity": 2, "reference_price": 999.0})
    assert result["status"].startswith("ejecutada")
    assert fake_broker.sent_orders == [("GGAL", 2)]
    # el costo se calcula con la cotización del fake broker, no con el
    # reference_price (obsoleto) que vino del chat.
    assert result["price"] == fake_broker.price

    orders = get_connection().execute("SELECT * FROM orders").fetchall()
    assert len(orders) == 1
    assert orders[0]["ticker"] == "GGAL"
    assert orders[0]["qty"] == 2
