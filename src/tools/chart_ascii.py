"""Gráfico de barras en texto plano (ASCII), pensado para lugares sin UI
gráfica disponible (la TUI/CLI de Hermes, la consola de `main.py`) — se
puede pegar tal cual dentro de un bloque de código y queda alineado en
cualquier fuente monoespaciada."""
from typing import Sequence, Tuple

Point = Tuple[str, float]


def ascii_bar_chart(points: Sequence[Point], unit: str = "", width: int = 28) -> str:
    """Arma un gráfico de barras horizontal a partir de pares (etiqueta, valor).

    Escala todas las barras contra el mayor valor absoluto de la serie, así
    que sirve tanto para series siempre positivas (dólar) como para series
    que pueden tener valores negativos (inflación mensual, en una deflación)."""
    if not points:
        return "(sin datos)"

    max_abs = max(abs(value) for _, value in points) or 1.0
    label_width = max(len(label) for label, _ in points)

    lines = []
    for label, value in points:
        bar_len = round(abs(value) / max_abs * width) if value else 0
        bar = "█" * bar_len
        sign = "-" if value < 0 else ""
        lines.append(f"{label.rjust(label_width)} │ {bar:<{width}} {sign}{abs(value):g}{unit}")
    return "\n".join(lines)
