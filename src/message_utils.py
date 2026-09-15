"""Utilidades para leer mensajes de LangChain de forma robusta.

Algunos modelos (p. ej. Claude, cuando devuelve razonamiento extendido u otros
bloques) arman `message.content` como una lista de bloques en vez de un string
plano. Cualquier nodo que necesite el texto de un mensaje debe pasar por acá
en lugar de asumir `message.content` como string.
"""


def message_text(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(part for part in parts if part)
    return str(content)
