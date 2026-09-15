"""Tabla de precios de LLM para estimar el costo de cada llamada.

Son precios aproximados en USD por millón de tokens (a la fecha en que se
escribió esto) — **no** se consultan de una API en vivo. Si el modelo
configurado no está en la tabla, se sigue guardando el conteo de tokens pero
sin costo (`cost_usd = None`) en vez de inventar un número.

Para mantenerlo al día: actualizá `MODEL_PRICING` cuando cambien los precios
del proveedor, o agregá el modelo nuevo que estés usando.
"""
from typing import Optional

# (precio input por 1M tokens, precio output por 1M tokens), en USD.
MODEL_PRICING = {
    # Anthropic
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-5": (15.0, 75.0),
    "claude-haiku-4-5-20251001": (0.8, 4.0),
    "claude-haiku-4.5": (0.8, 4.0),
    # OpenAI
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
}


def estimate_cost(model: Optional[str], input_tokens: int, output_tokens: int) -> Optional[float]:
    """Devuelve el costo estimado en USD, o `None` si no conocemos el precio
    de `model`."""
    if not model or model not in MODEL_PRICING:
        return None
    input_price, output_price = MODEL_PRICING[model]
    cost = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
    return round(cost, 6)
