"""MCP server que expone el asesor financiero (research, portafolio, órdenes)
como tools para Hermes Agent.

No reimplementa la lógica de negocio: importa y llama directamente a las
mismas funciones que ya usa el flujo LangGraph (`src/tools/*.py`,
`src/broker/ppi_broker.py`), así que el whitelist de tickers, la
re-cotización contra PPI y el chequeo de saldo dentro de `buy_stock` quedan
exactamente igual, sin duplicar esa lógica acá.

Lo único nuevo de este archivo es el "gate de confirmación": en el flujo
LangGraph, nada llega a `buy_stock` salvo que el nodo de compliance (código
Python) vea `pending_order["status"] == "confirmed"`, y en ese caso arma la
compra con el ticker/cantidad/precio guardados en esa orden — nunca con
valores que el LLM pase en el momento de ejecutar (ver
`src/agents/compliance.py::compliance_node`). Hermes no tiene ese nodo: el
LLM decide libremente qué tool llamar. Para no perder esa garantía:

- `propose_pending_order` es el único lugar que escribe `_pending_orders`.
- `buy_stock` acá solo recibe `ticker` (no cantidad ni precio) y ejecuta con
  los valores que hayan quedado guardados en una orden en estado
  "confirmed" — el modelo no puede alterar la cantidad al momento de
  comprar.
- Si además `ALLOW_REAL_TRADES` no es "true", la compra se simula sin tocar
  PPI (dry-run por defecto).

Cada llamada (research, portafolio, propuesta u orden) se audita en la
misma tabla `tool_calls` de `data/memory.db` que ya usa
`src/observability/tracing.py`, con `thread_id="hermes"` (o
`HERMES_SESSION_ID` si Hermes lo expone), para que el registro de auditoría
sea uno solo sin importar si la llamada vino de LangGraph o de Hermes. La
visibilidad en vivo de qué tool se está usando la da el streaming nativo de
la TUI/CLI de Hermes — esto es auditoría persistente, no la UI en vivo.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Hermes lanza este proceso con un cwd arbitrario (no necesariamente este
# proyecto) — hace falta el path absoluto para poder importar `src.*` y para
# que `load_dotenv()` encuentre el `.env` correcto sin depender del cwd.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from mcp.server.mcpserver import MCPServer

from src.broker.ppi_broker import REAL_TRADING_TICKERS
from src.db import LOCK, get_connection, init_db
from src.tools.macro_data import get_macro_series as _get_macro_series_tool
from src.tools.market_data import get_market_overview as _get_market_overview_tool
from src.tools.market_data import get_market_snapshot as _get_market_snapshot_tool
from src.tools.orders_state import propose_pending_order as _propose_pending_order_tool
from src.tools.portfolio import get_portfolio_summary as _get_portfolio_summary_tool
from src.tools.trading import buy_stock as _buy_stock_tool

ALLOW_REAL_TRADES = os.getenv("ALLOW_REAL_TRADES", "false").strip().lower() == "true"
THREAD_ID = os.getenv("HERMES_SESSION_ID", "hermes")
_REAL_TICKERS_TXT = " y ".join(sorted(REAL_TRADING_TICKERS))

mcp = MCPServer("asesor-financiero")

# Gate de confirmación (ver docstring del módulo). Vive en memoria del
# proceso: alcanza para una sesión de chat con Hermes, igual que el
# `pending_order` de LangGraph vive solo en el estado de un `thread_id`.
_pending_orders: dict[str, dict] = {}


def _audit(tool_name: str, args: dict, result: object, duration_ms: float) -> None:
    init_db()
    with LOCK:
        conn = get_connection()
        conn.execute(
            """INSERT INTO tool_calls
               (thread_id, timestamp, agent, tool_name, args_json, result_json, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                THREAD_ID,
                datetime.now(timezone.utc).isoformat(),
                "hermes",
                tool_name,
                json.dumps(args, default=str, ensure_ascii=False),
                json.dumps(result, default=str, ensure_ascii=False),
                duration_ms,
            ),
        )
        conn.commit()


@mcp.tool()
def get_market_snapshot(ticker: str) -> dict:
    """Devuelve una foto real (Yahoo Finance) de un ticker puntual: precio
    actual, variación % del día, promedios móviles de 50 y 200 días, y el
    rango de las últimas 52 semanas. Usar siempre que el cliente pregunte
    por una acción puntual (ej. "¿cómo está GGAL hoy?")."""
    start = time.monotonic()
    result = _get_market_snapshot_tool.func(ticker=ticker)
    _audit("get_market_snapshot", {"ticker": ticker}, result, (time.monotonic() - start) * 1000)
    return result


@mcp.tool()
def get_market_overview() -> list:
    """Devuelve un panorama real (Yahoo Finance) de un puñado de acciones
    principales (AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA, META, MELI). Usar
    cuando el cliente pregunte en general por "el mercado" o "las
    principales acciones", sin mencionar un ticker puntual."""
    start = time.monotonic()
    result = _get_market_overview_tool.func()
    _audit("get_market_overview", {}, result, (time.monotonic() - start) * 1000)
    return result


@mcp.tool()
def get_macro_series(indicator: str, months: int = 12) -> dict:
    """Devuelve el histórico mensual real de una variable macroeconómica de
    Argentina (fuente: ArgentinaDatos, api.argentinadatos.com), junto con un
    gráfico de barras en texto (ASCII, campo "chart") para mostrar tal cual
    en la respuesta, dentro de un bloque de código. Usar siempre que el
    cliente pregunte por inflación, IPC, dólar o tipo de cambio.

    `indicator` (obligatorio, uno de estos tres):
    - "inflacion": variación % mensual del IPC.
    - "dolar_oficial": cotización de venta del dólar oficial, cierre de cada mes.
    - "dolar_blue": cotización de venta del dólar blue, cierre de cada mes.

    `months` (default 12, máximo 60): cuántos meses recientes traer."""
    start = time.monotonic()
    args = {"indicator": indicator, "months": months}
    result = _get_macro_series_tool.func(indicator=indicator, months=months)
    _audit("get_macro_series", args, result, (time.monotonic() - start) * 1000)
    return result


@mcp.tool()
def get_portfolio_summary() -> dict:
    """Devuelve las posiciones y el efectivo disponible REALES de la cuenta
    de PPI conectada, junto con el perfil de riesgo declarado del cliente."""
    start = time.monotonic()
    result = _get_portfolio_summary_tool.func()
    _audit("get_portfolio_summary", {}, result, (time.monotonic() - start) * 1000)
    return result


@mcp.tool()
def propose_pending_order(
    ticker: str,
    status: str,
    qty: Optional[int] = None,
    reference_price: Optional[float] = None,
) -> dict:
    """Registrá el estado de la orden que el cliente está armando. No
    ejecuta ninguna compra — es el único paso que puede dejar una orden en
    condiciones de ejecutarse. Usar `status`:
    - "awaiting_details": ya sabés el ticker pero falta la cantidad.
    - "ready": tenés ticker y cantidad, esperando que el cliente confirme.
    - "confirmed": el cliente confirmó explícitamente ("confirmo", "dale",
      "sí", etc.) una orden que ya estaba en "ready". Nunca uses
      "confirmed" si el cliente no confirmó en este mismo mensaje una orden
      ya armada. Solo después de este paso, con status="confirmed", se
      puede llamar a `buy_stock` para ese ticker — y esa llamada va a usar
      la cantidad y el precio que quedaron acá, no los que se le pasen a
      `buy_stock` en ese momento (`buy_stock` no acepta cantidad/precio)."""
    start = time.monotonic()
    result = _propose_pending_order_tool.func(
        ticker=ticker, status=status, qty=qty, reference_price=reference_price
    )
    _pending_orders[result["ticker"]] = result
    _audit(
        "propose_pending_order",
        {"ticker": ticker, "status": status, "qty": qty, "reference_price": reference_price},
        result,
        (time.monotonic() - start) * 1000,
    )
    return result


_BUY_STOCK_DESC = (
    "Ejecuta (o simula, según configuración) la compra ya CONFIRMADA para "
    "`ticker`. Solo funciona si antes se llamó a `propose_pending_order` "
    "con status=\"confirmed\" para ese mismo ticker — no acepta cantidad ni "
    "precio como parámetro, usa siempre los valores de esa orden "
    "confirmada, así que no hace falta (ni es posible) indicárselos acá. "
    f"Por ahora la compra real solo está habilitada para {_REAL_TICKERS_TXT}"
    " — para cualquier otro ticker se rechaza sin ejecutar nada. Nunca "
    "llamar sin que el cliente haya confirmado explícitamente."
)


@mcp.tool(description=_BUY_STOCK_DESC)
def buy_stock(ticker: str) -> dict:
    start = time.monotonic()
    args = {"ticker": ticker}
    ticker_key = ticker.upper().strip()
    pending = _pending_orders.get(ticker_key)

    if not pending or pending.get("status") != "confirmed":
        result = {
            "status": "rechazada",
            "motivo": (
                f"no hay una orden confirmada para {ticker_key} — antes hay que "
                "llamar a propose_pending_order con status='confirmed', después "
                "de que el cliente confirmó explícitamente"
            ),
        }
        _audit("buy_stock", args, result, (time.monotonic() - start) * 1000)
        return result

    if not ALLOW_REAL_TRADES:
        result = {
            "status": "simulada",
            "motivo": (
                "ALLOW_REAL_TRADES no está en 'true' en .env — no se envió "
                "ninguna orden real a PPI (dry-run)."
            ),
            "ticker": ticker_key,
            "qty": pending.get("qty"),
            "reference_price": pending.get("reference_price"),
        }
        _audit("buy_stock", args, result, (time.monotonic() - start) * 1000)
        return result

    result = _buy_stock_tool.func(
        ticker=ticker_key,
        quantity=pending.get("qty"),
        reference_price=pending.get("reference_price") or 0.0,
    )
    if result.get("status", "").startswith("ejecutada"):
        _pending_orders.pop(ticker_key, None)
    _audit("buy_stock", args, result, (time.monotonic() - start) * 1000)
    return result


def main() -> None:
    """Entry point para `uvx`/`pip install` (ver pyproject.toml) — permite
    que otra instancia de Hermes agregue este MCP server con
    Transport: stdio, Command: uvx, Args: --from git+<repo> asesor-financiero-mcp,
    sin necesitar el archivo en el filesystem de esa instancia: uvx lo
    descarga e instala en un entorno aislado en el momento."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
