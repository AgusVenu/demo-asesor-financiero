"""Configuración central del demo.

Elige un modelo de LLM real si hay una API key en el entorno; si no hay ninguna,
`get_llm()` devuelve None y los agentes caen a su modo por reglas (ver
`src/agents/`). Así el demo funciona de punta a punta sin pedir presupuesto de
API para poder probarlo.
"""
import os

from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = os.getenv("AGENT_MODEL", "gpt-4o-mini")

# Tickers soportados en el demo (whitelist simple para extraer símbolos de un
# mensaje sin depender de un LLM). En un proyecto real esto se resolvería con
# un catálogo de instrumentos o un extractor más robusto.
DEMO_TICKERS = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "TSLA", "NVDA", "META",
    "MELI", "YPF", "GGAL", "KO", "DIS",
}


def get_llm():
    """Devuelve un chat model de LangChain, o None si no hay API key configurada."""
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=MODEL_NAME, temperature=0.2)
    if os.getenv("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic

        # Los modelos más nuevos de Claude (ej. claude-sonnet-5) no aceptan
        # `temperature` — lo dejamos en el valor por defecto del modelo.
        return ChatAnthropic(model=os.getenv("AGENT_MODEL", "claude-sonnet-5"))
    return None
