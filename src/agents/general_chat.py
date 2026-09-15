"""Agente de conversación general: atiende lo que no es mercado, portafolio ni una operación."""
from langchain_core.messages import AIMessage, SystemMessage

from src.config import get_llm

FALLBACK_TEXT = (
    'Puedo ayudarte con el mercado (ej: "¿cómo está AAPL?"), '
    'con tu portafolio ("¿cómo va mi portafolio?") o para operar ("comprar 5 AAPL").'
)

SYSTEM_PROMPT = (
    "Sos el asistente conversacional de un demo de asesor financiero multi-agente. "
    "Otros agentes del sistema ya se encargan de: cotizaciones de mercado (Yahoo Finance), "
    "análisis del portafolio real del cliente en PPI, y la ejecución de compras reales de "
    "acciones (por ahora GGAL/YPF). Vos atendés lo que no encaja en esas categorías: saludos, "
    "preguntas generales o pedidos fuera de alcance. Respondé breve y en español. Si la "
    "consulta en realidad es sobre mercado, portafolio u operar, sugerí reformularla (ej. "
    '"¿cómo está AAPL?", "¿cómo va mi portafolio?", "comprar 5 GGAL"). Si corresponde, aclará '
    "que es una demo educativa, no asesoramiento financiero real, pero que las compras de "
    "GGAL/YPF sí son órdenes reales a la cuenta de PPI conectada."
)


def general_chat_node(state, config=None):
    llm = get_llm()
    if llm is None:
        return {"messages": [AIMessage(content=FALLBACK_TEXT)]}
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    response = llm.invoke(messages, config=config)
    return {"messages": [response]}
