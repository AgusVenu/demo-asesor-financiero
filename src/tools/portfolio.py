"""Tool de análisis de portafolio: lee la posición real de la cuenta de PPI.

`client_id` y `risk_profile` son metadata local (PPI no tiene ese concepto);
`cash_balance` y `positions` vienen siempre de la cuenta real — ver
`src/broker/ppi_broker.py`.
"""
from langchain_core.tools import tool

from src.broker import ppi_broker
from src.memory import load_portfolio


@tool
def get_portfolio_summary() -> dict:
    """Devuelve las posiciones actuales del cliente, su efectivo disponible
    y su perfil de riesgo declarado. Posiciones y efectivo son datos reales
    de la cuenta de PPI conectada."""
    local = load_portfolio()
    broker = ppi_broker.get_broker()
    return {
        "client_id": local["client_id"],
        "risk_profile": local["risk_profile"],
        "cash_balance": broker.get_available_cash(),
        "positions": [
            {"ticker": p.ticker, "qty": p.quantity, "avg_price": p.avg_price}
            for p in broker.get_portfolio()
        ],
    }
