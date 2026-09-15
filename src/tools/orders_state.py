"""Tool de "reporte de estado" para la orden pendiente.

No toca nada externo (no compra, no descuenta efectivo) — solo valida y
devuelve la propuesta de `pending_order` que arma el agente de research o el
de ejecución. El nodo que envuelve al agente lee el `tool_call` resultante
para actualizar `state["pending_order"]`, así la transición de estado sigue
siendo determinística y auditable (no se infiere de texto libre del LLM),
aunque la decisión de *cuándo* dispararla la tome el LLM.
"""
from typing import Optional

from langchain_core.tools import tool

VALID_STATUSES = {"awaiting_details", "ready", "confirmed"}


@tool
def propose_pending_order(
    ticker: str,
    status: str,
    qty: Optional[int] = None,
    reference_price: Optional[float] = None,
) -> dict:
    """Registrá el estado de la orden que el cliente está armando (no ejecuta
    ninguna compra). Usar `status`:
    - "awaiting_details": ya sabés el ticker pero falta la cantidad.
    - "ready": tenés ticker y cantidad, esperando que el cliente confirme.
    - "confirmed": el cliente confirmó explícitamente ("confirmo", "dale",
      "sí", etc.) una orden que ya estaba en "ready". Nunca uses "confirmed"
      si el cliente no confirmó una orden ya armada en este mismo mensaje.
    """
    ticker = ticker.upper().strip()
    if status not in VALID_STATUSES:
        raise ValueError(f"status inválido: {status!r} (debe ser uno de {VALID_STATUSES})")
    return {
        "ticker": ticker,
        "status": status,
        "qty": qty,
        "reference_price": reference_price,
    }
