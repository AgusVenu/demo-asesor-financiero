"""Agente de análisis de portafolio.

Con LLM disponible: agente LangChain real con la tool `get_portfolio_summary`.
Sin LLM (modo offline / tests): arma el resumen a mano, como antes.
"""
from langchain_core.messages import AIMessage
from langgraph.prebuilt import create_react_agent

from src.agents.agent_utils import last_ai_text_message, new_messages_since
from src.agents.registry import get_skill
from src.config import get_llm
from src.observability.tracing import with_node_name
from src.tools.portfolio import get_portfolio_summary


def _rule_based(state) -> dict:
    data = get_portfolio_summary.invoke({})
    lines = [f"Perfil de riesgo: {data['risk_profile']} · Efectivo disponible: ${data['cash_balance']}."]
    if data["positions"]:
        lines.append("Posiciones actuales:")
        for position in data["positions"]:
            lines.append(f"  · {position['qty']} {position['ticker']} a un precio promedio de ${position['avg_price']}")
    else:
        lines.append("No hay posiciones abiertas todavía.")
    return {"messages": [AIMessage(content="\n".join(lines))]}


def _build_agent(llm):
    skill = get_skill("portfolio_analysis")
    return create_react_agent(llm, tools=skill.tools, prompt=skill.system_prompt)


@with_node_name("portfolio_analysis")
def portfolio_analysis_node(state, config=None):
    llm = get_llm()
    if llm is None:
        return _rule_based(state)

    agent = _build_agent(llm)
    before = list(state["messages"])
    result = agent.invoke({"messages": before}, config=config)
    new_messages = new_messages_since(before, result["messages"])

    final_message = last_ai_text_message(new_messages) or AIMessage(
        content="No pude armar el resumen de tu portafolio en este momento."
    )
    return {"messages": [final_message]}
