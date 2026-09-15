"""Base de memoria del demo: un único archivo SQLite (`data/memory.db`).

Guarda todo lo que antes vivía en JSON sueltos o en RAM:
- `portfolio` / `positions`: posiciones y efectivo del cliente (antes
  `data/portfolio.json`).
- `orders`: historial de compras (reales para GGAL/YPF vía PPI; antes
  `data/orders.json`).
- `tool_calls`: log de auditoría de qué tool llamó cada agente, con qué
  argumentos y qué devolvió (ver `src/observability/tracing.py`).
- `token_usage`: tokens y costo estimado de cada llamada al LLM.

El checkpointer de LangGraph (`src/memory.py:get_checkpointer`) usa la misma
conexión, así que la conversación en curso vive en el mismo archivo.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "memory.db"
SEED_PORTFOLIO_PATH = DATA_DIR / "portfolio.json"

LOCK = threading.RLock()
_connection: sqlite3.Connection | None = None
_initialized = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    client_id TEXT NOT NULL,
    risk_profile TEXT NOT NULL,
    cash_balance REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    ticker TEXT PRIMARY KEY,
    qty INTEGER NOT NULL,
    avg_price REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    qty INTEGER NOT NULL,
    price REAL NOT NULL,
    cost REAL NOT NULL,
    side TEXT NOT NULL,
    status TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT,
    timestamp TEXT NOT NULL,
    agent TEXT,
    tool_name TEXT NOT NULL,
    args_json TEXT NOT NULL,
    result_json TEXT,
    duration_ms REAL
);

CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT,
    timestamp TEXT NOT NULL,
    agent TEXT,
    model TEXT,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL
);
"""


def get_connection() -> sqlite3.Connection:
    """Conexión compartida (una por proceso) a `data/memory.db`.

    `check_same_thread=False` porque Streamlit, el checkpointer de LangGraph
    y el pool de hilos interno de LangGraph pueden operar sobre esta conexión
    desde hilos distintos al que la abrió. Un `sqlite3.Connection` no es
    seguro para accesos *concurrentes* aunque `check_same_thread=False` lo
    permita — por eso todo acceso a la conexión (acá, en `memory.py` y en
    `observability/tracing.py`) va protegido por `LOCK`.
    """
    global _connection
    if _connection is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _connection.row_factory = sqlite3.Row
    return _connection


def init_db() -> None:
    """Crea las tablas si no existen y siembra el portafolio de ejemplo la
    primera vez (para no perder el dato de muestra del repo). Es barato
    llamarla en cada operación: no vuelve a tocar la base una vez
    inicializada en este proceso."""
    global _initialized
    with LOCK:
        if _initialized:
            return
        conn = get_connection()
        conn.executescript(SCHEMA)
        conn.commit()
        _seed_portfolio_if_empty(conn)
        _initialized = True


def _seed_portfolio_if_empty(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT 1 FROM portfolio WHERE id = 1").fetchone()
    if row is not None:
        return
    if not SEED_PORTFOLIO_PATH.exists():
        return
    seed = json.loads(SEED_PORTFOLIO_PATH.read_text())
    conn.execute(
        "INSERT INTO portfolio (id, client_id, risk_profile, cash_balance) VALUES (1, ?, ?, ?)",
        (seed["client_id"], seed["risk_profile"], seed["cash_balance"]),
    )
    for position in seed.get("positions", []):
        conn.execute(
            "INSERT INTO positions (ticker, qty, avg_price) VALUES (?, ?, ?)",
            (position["ticker"], position["qty"], position["avg_price"]),
        )
    conn.commit()
