"""Regresión: algunos modelos (Claude con bloques de razonamiento, por ejemplo)
devuelven `message.content` como lista de bloques en vez de string plano."""
from langchain_core.messages import AIMessage

from src.message_utils import message_text


def test_message_text_with_plain_string():
    assert message_text(AIMessage(content="hola")) == "hola"


def test_message_text_with_list_of_text_blocks():
    message = AIMessage(content=[{"type": "text", "text": "hola"}, {"type": "text", "text": "mundo"}])
    assert message_text(message) == "hola\nmundo"


def test_message_text_ignores_non_text_blocks():
    message = AIMessage(
        content=[
            {"type": "thinking", "thinking": "razonamiento interno"},
            {"type": "text", "text": "respuesta final"},
        ]
    )
    assert message_text(message) == "respuesta final"
