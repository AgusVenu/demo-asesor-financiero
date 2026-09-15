"""Trazas en vivo: qué tool llamó cada agente, y cuánto costó cada llamada al LLM.

`CURRENT_AGENT` es un `ContextVar` que cada nodo del grafo setea (via
`with_node_name`) antes de invocar a su agente — así, cuando el callback ve un
tool-call que en realidad ocurrió *dentro* del sub-grafo interno de
`create_react_agent` (donde LangGraph solo sabe que el nodo se llama "tools"
o "agent"), igual sabemos que fue "market_research" o "order_execution" quien
lo disparó.

`AgentTraceCallback` es el callback de LangChain que loguea cada evento: lo
persiste siempre en SQLite (auditoría, funciona incluso sin UI) y, si se le
pasa un `sink`, también lo manda para mostrarlo en vivo (consola, Streamlit).
"""
from __future__ import annotations

import contextvars
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from langchain_core.callbacks import BaseCallbackHandler

from src.db import LOCK, get_connection, init_db
from src.observability.pricing import estimate_cost

CURRENT_AGENT: "contextvars.ContextVar[str]" = contextvars.ContextVar("CURRENT_AGENT", default="?")


def with_node_name(name: str):
    """Decorador para funciones-nodo del grafo: mientras corren, `CURRENT_AGENT`
    queda seteado a `name`, para que las trazas de tools/LLM sepan qué agente
    de alto nivel está activo.

    El wrapper declara `config` explícitamente (no `*args, **kwargs`) porque
    LangGraph decide si inyecta el `RunnableConfig` inspeccionando el nombre
    de los parámetros de la función — con `**kwargs` no lo detecta y las
    tools/LLM invocados dentro del nodo se quedan sin los callbacks del
    tracer. Por eso todo nodo del grafo tiene la firma `(state, config=None)`.
    """

    def decorator(fn):
        def wrapped(state, config=None):
            token = CURRENT_AGENT.set(name)
            try:
                return fn(state, config)
            finally:
                CURRENT_AGENT.reset(token)

        wrapped.__name__ = getattr(fn, "__name__", name)
        return wrapped

    return decorator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceEvent:
    kind: str  # "tool" | "llm"
    agent: str
    timestamp: str
    tool_name: Optional[str] = None
    args: Optional[dict] = None
    result: Optional[str] = None
    duration_ms: Optional[float] = None
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None

    def render(self) -> str:
        if self.kind == "tool":
            args_txt = ", ".join(f"{k}={v!r}" for k, v in (self.args or {}).items())
            result_txt = self.result if len(self.result or "") <= 200 else self.result[:200] + "…"
            return f"🔧 [{self.agent}] {self.tool_name}({args_txt}) → {result_txt}"
        cost_txt = f"${self.cost_usd:.5f}" if self.cost_usd is not None else "costo no disponible"
        return (
            f"💬 [{self.agent}] {self.model}: {self.input_tokens} tokens in / "
            f"{self.output_tokens} tokens out ({cost_txt})"
        )


class AgentTraceCallback(BaseCallbackHandler):
    """Callback de LangChain: persiste cada tool-call y cada uso de LLM en
    `data/memory.db`, y opcionalmente los reenvía en vivo a `sink`."""

    def __init__(self, thread_id: str, sink: Optional[Callable[[TraceEvent], None]] = None):
        init_db()
        self.thread_id = thread_id
        self.sink = sink
        self._tool_starts: dict = {}

    def _emit(self, event: TraceEvent) -> None:
        if self.sink is not None:
            self.sink(event)

    # -- Tools -----------------------------------------------------------
    def on_tool_start(
        self,
        serialized: dict,
        input_str: str,
        *,
        run_id,
        parent_run_id=None,
        tags=None,
        metadata=None,
        inputs: Optional[dict] = None,
        **kwargs: Any,
    ) -> None:
        self._tool_starts[run_id] = {
            "start": time.monotonic(),
            "name": serialized.get("name", "tool"),
            "args": inputs if inputs is not None else {"input": input_str},
        }

    def on_tool_end(self, output: Any, *, run_id, parent_run_id=None, **kwargs: Any) -> None:
        started = self._tool_starts.pop(run_id, {})
        duration_ms = (
            (time.monotonic() - started["start"]) * 1000 if started.get("start") else None
        )
        tool_name = started.get("name") or getattr(output, "name", None) or "tool"
        args = started.get("args") or {}
        result_text = getattr(output, "content", None)
        if result_text is None:
            result_text = str(output)

        event = TraceEvent(
            kind="tool",
            agent=CURRENT_AGENT.get(),
            timestamp=_now(),
            tool_name=tool_name,
            args=args,
            result=str(result_text),
            duration_ms=duration_ms,
        )
        self._persist_tool_call(event)
        self._emit(event)

    def _persist_tool_call(self, event: TraceEvent) -> None:
        with LOCK:
            conn = get_connection()
            conn.execute(
                """INSERT INTO tool_calls (thread_id, timestamp, agent, tool_name, args_json, result_json, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.thread_id,
                    event.timestamp,
                    event.agent,
                    event.tool_name,
                    json.dumps(event.args, default=str, ensure_ascii=False),
                    event.result,
                    event.duration_ms,
                ),
            )
            conn.commit()

    # -- LLM (tokens/costo) -----------------------------------------------
    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs: Any) -> None:
        try:
            message = response.generations[0][0].message
        except (IndexError, AttributeError):
            return
        usage = getattr(message, "usage_metadata", None)
        if not usage:
            return
        model = None
        response_metadata = getattr(message, "response_metadata", None) or {}
        model = response_metadata.get("model") or response_metadata.get("model_name")

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = estimate_cost(model, input_tokens, output_tokens)

        event = TraceEvent(
            kind="llm",
            agent=CURRENT_AGENT.get(),
            timestamp=_now(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        self._persist_token_usage(event)
        self._emit(event)

    def _persist_token_usage(self, event: TraceEvent) -> None:
        with LOCK:
            conn = get_connection()
            conn.execute(
                """INSERT INTO token_usage (thread_id, timestamp, agent, model, input_tokens, output_tokens, cost_usd)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.thread_id,
                    event.timestamp,
                    event.agent,
                    event.model,
                    event.input_tokens,
                    event.output_tokens,
                    event.cost_usd,
                ),
            )
            conn.commit()


def get_thread_totals(thread_id: str) -> dict:
    """Tokens y costo acumulados de un `thread_id` (para mostrar en la UI)."""
    init_db()
    with LOCK:
        conn = get_connection()
        row = conn.execute(
            """SELECT COALESCE(SUM(input_tokens), 0) AS input_tokens,
                      COALESCE(SUM(output_tokens), 0) AS output_tokens,
                      SUM(cost_usd) AS cost_usd
               FROM token_usage WHERE thread_id = ?""",
            (thread_id,),
        ).fetchone()
        return dict(row)


def get_tool_calls(thread_id: str, limit: int = 100) -> list:
    """Historial completo (más reciente primero) de tool-calls de un
    `thread_id`, con argumentos y resultado ya deserializados — para el panel
    de detalle de la UI (o cualquier auditoría fuera de la UI)."""
    init_db()
    with LOCK:
        conn = get_connection()
        rows = conn.execute(
            """SELECT timestamp, agent, tool_name, args_json, result_json, duration_ms
               FROM tool_calls WHERE thread_id = ? ORDER BY id DESC LIMIT ?""",
            (thread_id, limit),
        ).fetchall()

    calls = []
    for row in rows:
        call = dict(row)
        try:
            call["args"] = json.loads(call.pop("args_json"))
        except (TypeError, ValueError):
            call["args"] = call.pop("args_json")
        result_raw = call.pop("result_json")
        try:
            call["result"] = json.loads(result_raw)
        except (TypeError, ValueError):
            call["result"] = result_raw
        calls.append(call)
    return calls
