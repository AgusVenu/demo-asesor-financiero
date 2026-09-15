"""Agente de triage.

Clasifica la intención del mensaje y decide si hay que retomar una orden
pendiente. Es una clasificación por reglas, determinística y auditable a
propósito — cuando hay una posible compra de por medio, preferimos algo
que se pueda explicar línea por línea antes que la caja negra de un LLM.
"""
import re
from typing import Optional

from src.config import DEMO_TICKERS

CONFIRM_WORDS = {"si", "sí", "confirmo", "dale", "adelante", "comprar", "confirmar", "ok", "yes", "hazlo", "hacelo"}
CANCEL_WORDS = {"no", "cancelar", "cancela", "olvidalo", "dejalo"}
MARKET_KEYWORDS = {
    "mercado", "accion", "acción", "acciones", "cotiza", "cotizacion", "cotización", "precio", "yahoo",
    "inflacion", "inflación", "ipc", "dolar", "dólar", "blue",
}
PORTFOLIO_KEYWORDS = {"portafolio", "cartera", "posiciones", "posicion", "posición", "rendimiento"}
OPERATE_KEYWORDS = {"comprar", "compra", "operar", "orden"}


def tokenize(text: str) -> set:
    return set(re.findall(r"[a-záéíóúñ0-9]+", text.lower()))


def extract_ticker(text: str) -> Optional[str]:
    for word in re.findall(r"\b[A-Za-z\-]{1,6}\b", text):
        if word.upper() in DEMO_TICKERS:
            return word.upper()
    return None


def extract_quantity(text: str) -> Optional[int]:
    match = re.search(r"\b(\d{1,6})\b", text)
    return int(match.group(1)) if match else None


def classify_intent(text: str, pending_order: Optional[dict]) -> str:
    tokens = tokenize(text)

    if pending_order and pending_order.get("status") in ("awaiting_details", "ready"):
        return "cancelar" if tokens & CANCEL_WORDS else "operar"

    if tokens & OPERATE_KEYWORDS:
        return "operar"
    if extract_ticker(text):
        return "mercado"
    if tokens & PORTFOLIO_KEYWORDS or "mi cuenta" in text.lower():
        return "portafolio"
    if tokens & MARKET_KEYWORDS:
        return "mercado"
    return "otro"


def triage_node(state, config=None):
    last_human = next((m for m in reversed(state["messages"]) if m.type == "human"), None)
    text = last_human.content if last_human else ""
    intent = classify_intent(text, state.get("pending_order"))
    return {"intent": intent}
