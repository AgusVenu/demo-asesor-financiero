"""Agente de compliance.

Es la única puerta que puede disparar la ejecución REAL (contra la cuenta de
PPI, para GGAL/YPF) de una orden ya confirmada por el cliente, y quien
agrega el disclaimer a cualquier respuesta con contenido financiero. No
tiene memoria propia a propósito: cada respuesta —y cada orden— se valida
sola, sin arrastrar criterios de turnos anteriores.
"""
from langchain_core.messages import AIMessage

from src.message_utils import message_text
from src.tools.trading import buy_stock

BANNED_PHRASES = ["te recomiendo comprar", "te aseguro que", "es una compra segura", "garantizado"]
DISCLAIMER = "Esto es una demo educativa — no es asesoramiento financiero real. Este agente sí puede enviar órdenes reales a tu cuenta de PPI para GGAL/YPF: revisá siempre antes de confirmar."


def compliance_node(state, config=None):
    pending = state.get("pending_order")

    if pending and pending.get("status") == "confirmed":
        result = buy_stock.invoke(
            {
                "ticker": pending["ticker"],
                "quantity": pending["qty"],
                "reference_price": pending.get("reference_price") or 0.0,
            },
            config=config,
        )
        if result["status"].startswith("ejecutada"):
            content = (
                f"Listo: compré {result['qty']} {result['ticker']} a ${result['price']} "
                f"(costo ${result['cost']}, orden real de PPI #{result['ppi_order_id']}). "
                f"Quedó registrada en data/memory.db.\n\n{DISCLAIMER}"
            )
        else:
            content = f"No ejecuté la orden: {result.get('motivo')}.\n\n{DISCLAIMER}"
        return {"messages": [AIMessage(content=content)], "pending_order": None}

    last_ai = next((m for m in reversed(state["messages"]) if m.type == "ai"), None)
    if not last_ai:
        return {}

    lowered = message_text(last_ai).lower()
    notes = []
    if any(phrase in lowered for phrase in BANNED_PHRASES):
        notes.append(
            "Compliance: reformulá esa frase, sonaba a recomendación directa — esto es información, no asesoramiento."
        )
    if any(k in lowered for k in ("precio", "mercado", "portafolio", "posiciones", "acciones", "$")):
        notes.append(DISCLAIMER)

    if notes:
        return {"messages": [AIMessage(content="\n".join(notes))]}
    return {}
