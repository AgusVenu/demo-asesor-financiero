"""Tool de variables macroeconómicas de Argentina: histórico mensual real vía
la API pública de ArgentinaDatos (https://api.argentinadatos.com), sin auth.

Igual que `market_data.py`, expone un cálculo puro (`extract_macro_indicator`)
para que el nodo de LangGraph pueda resolver, de forma determinística, qué
indicador pidió el cliente antes de invocar al agente — mismo espíritu que
`extract_ticker` en `src/agents/triage.py`."""
from typing import List, Optional, Tuple

import requests
from langchain_core.tools import tool

from src.tools.chart_ascii import ascii_bar_chart

_BASE_URL = "https://api.argentinadatos.com/v1"

_INDICATORS = {
    "inflacion": {
        "title": "Inflación mensual (IPC)",
        "unit": "%",
        "endpoint": f"{_BASE_URL}/finanzas/indices/inflacion",
    },
    "dolar_oficial": {
        "title": "Dólar oficial (venta, cierre de cada mes)",
        "unit": " ARS",
        "endpoint": f"{_BASE_URL}/cotizaciones/dolares/oficial",
    },
    "dolar_blue": {
        "title": "Dólar blue (venta, cierre de cada mes)",
        "unit": " ARS",
        "endpoint": f"{_BASE_URL}/cotizaciones/dolares/blue",
    },
}


def extract_macro_indicator(text: str) -> Optional[str]:
    """Heurística simple por palabras clave — mismo espíritu que
    `extract_ticker`, para resolver el indicador de forma determinística
    antes de pasarle el dato al agente como contexto."""
    lowered = text.lower()
    if "inflacion" in lowered or "inflación" in lowered or "ipc" in lowered:
        return "inflacion"
    if "blue" in lowered and ("dolar" in lowered or "dólar" in lowered):
        return "dolar_blue"
    if "dolar" in lowered or "dólar" in lowered or "tipo de cambio" in lowered:
        return "dolar_oficial"
    return None


def _fetch_json(url: str) -> list:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


def _monthly_from_indexed(records: list, months: int) -> List[Tuple[str, float]]:
    ordered = sorted(records, key=lambda r: r["fecha"])
    return [(r["fecha"][:7], r["valor"]) for r in ordered[-months:]]


def _monthly_close(records: list, months: int, price_key: str = "venta") -> List[Tuple[str, float]]:
    by_month = {}
    for record in sorted(records, key=lambda r: r["fecha"]):
        by_month[record["fecha"][:7]] = record[price_key]
    return [(mes, by_month[mes]) for mes in sorted(by_month)[-months:]]


def _fetch_series(indicator: str, months: int) -> dict:
    meta = _INDICATORS[indicator]
    data = _fetch_json(meta["endpoint"])
    if indicator == "inflacion":
        points = _monthly_from_indexed(data, months)
    else:
        points = _monthly_close(data, months)

    return {
        "indicator": indicator,
        "title": meta["title"],
        "unit": meta["unit"].strip(),
        "series": [{"mes": mes, "valor": valor} for mes, valor in points],
        "chart": ascii_bar_chart(points, unit=meta["unit"]),
        "source": "ArgentinaDatos (api.argentinadatos.com)",
    }


@tool
def get_macro_series(indicator: str, months: int = 12) -> dict:
    """Devuelve el histórico mensual real de una variable macroeconómica de
    Argentina (fuente: ArgentinaDatos, api.argentinadatos.com), junto con un
    gráfico de barras en texto (ASCII, campo `chart`) listo para pegar tal
    cual en la respuesta dentro de un bloque de código. Usar siempre que el
    cliente pregunte por inflación, IPC, dólar o tipo de cambio.

    `indicator` (obligatorio, uno de estos tres):
    - "inflacion": variación % mensual del IPC.
    - "dolar_oficial": cotización de venta del dólar oficial, cierre de cada mes.
    - "dolar_blue": cotización de venta del dólar blue, cierre de cada mes.

    `months` (default 12, máximo 60): cuántos meses recientes traer."""
    if indicator not in _INDICATORS:
        valid = ", ".join(_INDICATORS)
        raise ValueError(f"indicator inválido: {indicator!r}. Valores válidos: {valid}")
    months = max(1, min(months, 60))
    return _fetch_series(indicator, months)
