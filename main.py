"""Demo interactivo del asesor financiero multi-agente.

Corré: python main.py [thread_id]
Si no pasás un thread_id se genera uno nuevo; pasá uno existente (el que
imprime al arrancar) para retomar una conversación guardada en
`data/memory.db` entre corridas.

Probá, por ejemplo:
  - "¿cómo está AAPL?"
  - "¿cómo va mi portafolio?"
  - "comprar 5 AAPL"
"""
import sys
import uuid

from langchain_core.messages import HumanMessage

from src.db import init_db
from src.graph import build_graph
from src.message_utils import message_text
from src.observability.tracing import AgentTraceCallback


def console_sink(event) -> None:
    print(event.render())


def main():
    init_db()
    app = build_graph()
    thread_id = sys.argv[1] if len(sys.argv) > 1 else str(uuid.uuid4())
    tracer = AgentTraceCallback(thread_id=thread_id, sink=console_sink)
    config = {"configurable": {"thread_id": thread_id}, "callbacks": [tracer]}

    print("Asesor financiero multi-agente (demo) — escribí 'salir' para terminar.")
    print(f"thread_id: {thread_id} (pasalo como argumento para retomar esta conversación)")
    print('Probá: "¿cómo está AAPL?" · "¿cómo va mi portafolio?" · "comprar 5 AAPL"\n')

    snapshot = app.get_state(config)
    printed = len(snapshot.values.get("messages", [])) if snapshot.values else 0

    while True:
        try:
            user_input = input("Vos: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"salir", "exit", "quit"}:
            break

        result = app.invoke({"messages": [HumanMessage(content=user_input)]}, config)
        messages = result["messages"]
        for message in messages[printed:]:
            if message.type == "ai":
                print(f"Asesor: {message_text(message)}\n")
        printed = len(messages)


if __name__ == "__main__":
    main()
