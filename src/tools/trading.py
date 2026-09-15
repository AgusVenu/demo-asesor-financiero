"""Tool de ejecución de órdenes.

Compra REAL contra la cuenta de PPI conectada — la usa exclusivamente el
agente de compliance, y solo después de que el cliente confirmó
explícitamente la orden (`pending_order["status"] == "confirmed"`).

Alcance v1: solo `GGAL` y `YPF` (ver `src/broker/ppi_broker.py`). Cualquier
otro ticker se rechaza acá mismo, sin tocar la API de PPI ni simular nada —
esta es la puerta de seguridad real, independiente de lo que haya propuesto
el agente de ejecución de órdenes.

El `reference_price` que llega del chat viene del research de Yahoo Finance
(a veces en USD) y es solo informativo: el costo real siempre se calcula con
una cotización fresca de PPI (en ARS) tomada en este mismo momento.
"""
from datetime import datetime, timezone

from langchain_core.tools import tool

from src.broker import ppi_broker
from src.broker.ppi_broker import REAL_TRADING_TICKERS, BrokerError
from src.memory import append_order


@tool
def buy_stock(ticker: str, quantity: int, reference_price: float) -> dict:
    """Ejecuta una compra REAL de `quantity` acciones de `ticker` contra la
    cuenta de PPI conectada. Por ahora solo están habilitados GGAL y YPF —
    para cualquier otro ticker, la orden se rechaza sin ejecutar nada. Nunca
    llamar sin una confirmación explícita del cliente."""
    if quantity <= 0:
        raise ValueError("La cantidad debe ser mayor a cero")

    ticker = ticker.upper().strip()

    if ticker not in REAL_TRADING_TICKERS:
        return {
            "status": "rechazada",
            "motivo": (
                f"compra real no disponible todavía para {ticker} "
                f"(por ahora solo {', '.join(sorted(REAL_TRADING_TICKERS))})"
            ),
        }

    broker = ppi_broker.get_broker()

    try:
        quote = broker.get_quote(ticker)
    except BrokerError as exc:
        return {"status": "rechazada", "motivo": f"no se pudo cotizar {ticker}: {exc}"}

    cost = round(quantity * quote.price, 2)

    try:
        available_cash = broker.get_available_cash()
    except BrokerError as exc:
        return {"status": "rechazada", "motivo": f"no se pudo verificar el saldo: {exc}"}

    if cost > available_cash:
        return {
            "status": "rechazada",
            "motivo": "saldo insuficiente en la cuenta de PPI",
            "costo_estimado": cost,
            "saldo_disponible": available_cash,
        }

    try:
        order_id, _raw = broker.place_market_buy(ticker, quantity)
    except BrokerError as exc:
        return {"status": "rechazada", "motivo": f"la orden fue rechazada por PPI: {exc}"}

    order = {
        "ticker": ticker,
        "qty": quantity,
        "price": quote.price,
        "cost": cost,
        "side": "buy",
        "status": f"ejecutada (real, PPI order {order_id})",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    append_order(order)
    return {"status": "ejecutada (real)", "ppi_order_id": order_id, **order}
