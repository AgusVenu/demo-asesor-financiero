"""Memoria del demo.

- Corto plazo (la conversación actual, incluyendo `pending_order`): checkpointer
  de LangGraph sobre SQLite (`SqliteSaver`), por `thread_id` — persiste entre
  corridas, a diferencia de un `MemorySaver` en RAM.
- Largo plazo (entre sesiones): portafolio y libro de órdenes, también en
  `data/memory.db` (ver `src/db.py`). En un sistema real esto sería una base
  de datos gestionada y la cuenta de un broker.

Las funciones de acá mantienen la misma firma que antes (cuando leían/escribían
JSON) para que `src/tools/portfolio.py` y `src/tools/trading.py` no tengan que
cambiar. Todo acceso a la conexión de la app va bajo `db.LOCK` — ver la nota
en `src/db.py:get_connection`.

El checkpointer usa su **propia** conexión sqlite3 al mismo archivo (en vez de
compartir la de `db.get_connection()`): `SqliteSaver` ya serializa el acceso a
su conexión con su propio lock interno, y dos locks distintos protegiendo la
misma conexión compartida no dan exclusión mutua entre sí — mezclarlos
producía corrupción de verdad (crashes intermitentes del intérprete) cuando
LangGraph tocaba el checkpoint en un hilo mientras un nodo leía el portafolio
en otro.
"""
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

import src.db as db
from src.db import LOCK, get_connection, init_db

_checkpointer = None


def get_checkpointer():
    """Checkpointer de LangGraph persistido en `data/memory.db` (conexión propia).

    Usa `db.DB_PATH` (atributo del módulo, no un `from ... import DB_PATH`)
    para que los tests puedan seguir apuntándolo a una base temporal vía
    `monkeypatch.setattr(db, "DB_PATH", ...)` — un import por valor copiaría
    el path original y el checkpointer terminaría escribiendo siempre sobre
    `data/memory.db` real, aunque el resto de la memoria esté aislado.
    """
    global _checkpointer
    if _checkpointer is None:
        init_db()
        checkpointer_conn = sqlite3.connect(str(db.DB_PATH), check_same_thread=False)
        _checkpointer = SqliteSaver(checkpointer_conn)
        _checkpointer.setup()
    return _checkpointer


def load_portfolio() -> dict:
    init_db()
    with LOCK:
        conn = get_connection()
        row = conn.execute(
            "SELECT client_id, risk_profile, cash_balance FROM portfolio WHERE id = 1"
        ).fetchone()
        positions = conn.execute("SELECT ticker, qty, avg_price FROM positions").fetchall()
        return {
            "client_id": row["client_id"],
            "risk_profile": row["risk_profile"],
            "cash_balance": row["cash_balance"],
            "positions": [dict(p) for p in positions],
        }


def save_portfolio(data: dict) -> None:
    init_db()
    with LOCK:
        conn = get_connection()
        conn.execute(
            "UPDATE portfolio SET client_id = ?, risk_profile = ?, cash_balance = ? WHERE id = 1",
            (data["client_id"], data["risk_profile"], data["cash_balance"]),
        )
        conn.execute("DELETE FROM positions")
        for position in data.get("positions", []):
            conn.execute(
                "INSERT INTO positions (ticker, qty, avg_price) VALUES (?, ?, ?)",
                (position["ticker"], position["qty"], position["avg_price"]),
            )
        conn.commit()


def load_orders() -> list:
    init_db()
    with LOCK:
        conn = get_connection()
        rows = conn.execute(
            "SELECT ticker, qty, price, cost, side, status, timestamp FROM orders ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def append_order(order: dict) -> None:
    init_db()
    with LOCK:
        conn = get_connection()
        conn.execute(
            """INSERT INTO orders (ticker, qty, price, cost, side, status, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                order["ticker"],
                order["qty"],
                order["price"],
                order["cost"],
                order["side"],
                order["status"],
                order["timestamp"],
            ),
        )
        conn.commit()
