"""Arma el grafo de LangGraph: triage decide, los agentes especializados
responden, compliance revisa (y es quien ejecuta la orden) antes de cerrar
el turno.
"""
from langgraph.graph import END, START, StateGraph

from src.agents.compliance import compliance_node
from src.agents.general_chat import general_chat_node
from src.agents.market_research import market_research_node
from src.agents.order_execution import cancel_node, order_execution_node
from src.agents.portfolio_analysis import portfolio_analysis_node
from src.agents.triage import triage_node
from src.memory import get_checkpointer
from src.observability.tracing import with_node_name
from src.state import AgentState


def _route_from_triage(state):
    return state["intent"]


def build_graph():
    graph = StateGraph(AgentState)

    # market_research/portfolio_analysis/order_execution ya vienen decoradas
    # con with_node_name en su propio módulo (fijan CURRENT_AGENT antes de
    # invocar a su agente LangChain). Acá se decoran también las demás, para
    # que las trazas de tool-calls (buy_stock en compliance, el LLM opcional
    # de "otro") queden atribuidas al nodo correcto.
    graph.add_node("triage", with_node_name("triage")(triage_node))
    graph.add_node("market_research", market_research_node)
    graph.add_node("portfolio_analysis", portfolio_analysis_node)
    graph.add_node("order_execution", order_execution_node)
    graph.add_node("cancelar", with_node_name("cancelar")(cancel_node))
    graph.add_node("otro", with_node_name("otro")(general_chat_node))
    graph.add_node("compliance", with_node_name("compliance")(compliance_node))

    graph.add_edge(START, "triage")
    graph.add_conditional_edges(
        "triage",
        _route_from_triage,
        {
            "mercado": "market_research",
            "portafolio": "portfolio_analysis",
            "operar": "order_execution",
            "cancelar": "cancelar",
            "otro": "otro",
        },
    )
    for node in ("market_research", "portfolio_analysis", "order_execution", "cancelar", "otro"):
        graph.add_edge(node, "compliance")
    graph.add_edge("compliance", END)

    return graph.compile(checkpointer=get_checkpointer())
