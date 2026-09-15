"""UI en tiempo real del asesor financiero multi-agente.

Corré: streamlit run ui/app.py

Muestra, además del chat, un panel en vivo con cada tool que se llama durante
el turno (qué agente la llamó, con qué argumentos, qué devolvió) y un panel
de detalle **persistente** (columna derecha) con el historial completo de
tool-calls de la conversación — leído directo de `data/memory.db`, así que
sobrevive a un `st.rerun()` y a reabrir la página. El sidebar tiene el
registro de agentes, sus "skills" y las tools que tiene permitido usar cada
uno, más el costo acumulado.
"""
import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage  # noqa: E402

from src.agents.registry import AGENT_SKILLS  # noqa: E402
from src.db import init_db  # noqa: E402
from src.graph import build_graph  # noqa: E402
from src.message_utils import message_text  # noqa: E402
from src.observability.tracing import AgentTraceCallback, get_thread_totals, get_tool_calls  # noqa: E402

st.set_page_config(page_title="Asesor financiero multi-agente", page_icon="💹", layout="wide")


@st.cache_resource
def get_app():
    init_db()
    return build_graph()


def _new_thread_id() -> str:
    return str(uuid.uuid4())[:8]


def _render_tool_call(call: dict) -> None:
    duration = f" · {call['duration_ms']:.0f} ms" if call.get("duration_ms") is not None else ""
    label = f"🔧 [{call['agent']}] {call['tool_name']}{duration}"
    with st.expander(label):
        st.caption(call["timestamp"])
        st.markdown("**Argumentos**")
        st.json(call["args"])
        st.markdown("**Resultado**")
        if isinstance(call["result"], (dict, list)):
            st.json(call["result"])
        else:
            st.code(str(call["result"]))


if "thread_id" not in st.session_state:
    st.session_state.thread_id = _new_thread_id()

app = get_app()

# -- Sidebar: registro de skills/tools + costo acumulado --------------------
with st.sidebar:
    st.header("💹 Asesor financiero (demo)")
    st.caption("Multi-agente con LangChain/LangGraph — no es asesoramiento financiero real.")

    st.subheader("Conversación")
    thread_input = st.text_input("thread_id", value=st.session_state.thread_id)
    col_a, col_b = st.columns(2)
    if col_a.button("Retomar", use_container_width=True) and thread_input:
        st.session_state.thread_id = thread_input
        st.rerun()
    if col_b.button("Nueva", use_container_width=True):
        st.session_state.thread_id = _new_thread_id()
        st.rerun()

    st.subheader("Costo acumulado (este thread)")
    totals = get_thread_totals(st.session_state.thread_id)
    cost = totals.get("cost_usd")
    st.metric("Tokens in / out", f"{totals['input_tokens']} / {totals['output_tokens']}")
    st.metric("Costo estimado", f"${cost:.5f}" if cost is not None else "n/d")
    st.caption("Estimado con una tabla de precios local — ver `src/observability/pricing.py`.")

    st.subheader("Agentes, skills y tools")
    for skill in AGENT_SKILLS:
        badge = "🧠 LLM" if skill.llm_driven else "⚙️ reglas"
        with st.expander(f"{skill.label} · {badge}"):
            st.write(skill.description)
            if skill.tools:
                st.caption("Tools: " + ", ".join(t.name for t in skill.tools))
            else:
                st.caption("Sin tools.")

# -- Layout principal: chat a la izquierda, detalle de tools a la derecha ----
config = {"configurable": {"thread_id": st.session_state.thread_id}}
snapshot = app.get_state(config)
history = snapshot.values.get("messages", []) if snapshot.values else []

main_col, trace_col = st.columns([3, 2], gap="large")

with main_col:
    st.subheader("Chat")
    for message in history:
        if message.type in ("human", "ai") and message_text(message).strip():
            with st.chat_message("user" if message.type == "human" else "assistant"):
                st.markdown(message_text(message))

    user_input = st.chat_input("Escribí tu consulta (ej: '¿cómo está AAPL?')")

    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.status("Procesando...", expanded=True) as status:

            def live_sink(event):
                status.write(event.render())

            tracer = AgentTraceCallback(thread_id=st.session_state.thread_id, sink=live_sink)
            run_config = {**config, "callbacks": [tracer]}
            before = len(history)
            result = app.invoke({"messages": [HumanMessage(content=user_input)]}, run_config)
            status.update(label="Listo", state="complete", expanded=False)

        new_messages = result["messages"][before:]
        for message in new_messages:
            if message.type == "ai" and message_text(message).strip():
                with st.chat_message("assistant"):
                    st.markdown(message_text(message))

        st.rerun()

with trace_col:
    st.subheader("🔍 Detalle de tool-calls")
    st.caption(
        "Historial completo de esta conversación (más reciente primero) — "
        "persiste entre turnos y entre sesiones, leído de `data/memory.db`."
    )
    tool_calls = get_tool_calls(st.session_state.thread_id, limit=30)
    if not tool_calls:
        st.info("Todavía no se llamó ninguna tool en esta conversación.")
    else:
        for call in tool_calls:
            _render_tool_call(call)
