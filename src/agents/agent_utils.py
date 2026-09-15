"""Utilidades compartidas por los agentes especialistas que usan
`create_react_agent` (research, portafolio, ejecución de órdenes)."""
import json
from typing import List, Optional

from langchain_core.messages import BaseMessage, ToolMessage

from src.message_utils import message_text


def new_messages_since(before: List[BaseMessage], after: List[BaseMessage]) -> List[BaseMessage]:
    """Los mensajes que agregó el agente en esta invocación (tool calls,
    resultados de tools, y la respuesta final)."""
    return after[len(before):]


def find_tool_result(messages: List[BaseMessage], tool_name: str) -> Optional[dict]:
    """Busca, de atrás para adelante, el resultado (ya parseado) de la última
    llamada a `tool_name` entre los mensajes dados."""
    for message in reversed(messages):
        if isinstance(message, ToolMessage) and message.name == tool_name:
            try:
                return json.loads(message.content)
            except (TypeError, ValueError):
                return None
    return None


def last_ai_text_message(messages: List[BaseMessage]) -> Optional[BaseMessage]:
    """La última respuesta en lenguaje natural del agente (ignora los
    mensajes intermedios que solo contienen tool calls)."""
    for message in reversed(messages):
        if message.type == "ai" and message_text(message).strip():
            return message
    return None
