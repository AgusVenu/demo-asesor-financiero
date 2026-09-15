"""Estado compartido del grafo multi-agente."""
from typing import Annotated, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class PendingOrder(TypedDict, total=False):
    ticker: str
    qty: int
    status: str  # "awaiting_details" | "ready" | "confirmed"
    reference_price: float


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    intent: Optional[str]
    pending_order: Optional[PendingOrder]
