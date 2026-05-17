"""Agent state definition - the shared state that flows through all LangGraph nodes."""

import operator
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field

try:
    from langgraph.graph.message import add_messages
except ImportError:
    add_messages = operator.add


class IntentType(str, Enum):
    PRODUCT_INQUIRY = "product_inquiry"
    PRICING_INQUIRY = "pricing_inquiry"
    STOCK_CHECK = "stock_check"
    ORDER_STATUS = "order_status"
    LOGISTICS_QUERY = "logistics_query"
    MODIFY_ORDER = "modify_order"
    RETURN_REQUEST = "return_request"
    EXCHANGE_REQUEST = "exchange_request"
    REFUND_INQUIRY = "refund_inquiry"
    COMPLAINT = "complaint"
    TECHNICAL_ISSUE = "technical_issue"
    ACCOUNT_ISSUE = "account_issue"
    GENERAL_INQUIRY = "general_inquiry"
    HUMAN_HANDOFF = "human_handoff"
    SLOT_FILLING = "slot_filling"


class SkillName(str, Enum):
    PRE_SALES = "pre_sales"
    AFTER_SALES = "after_sales"
    COMPLAINT = "complaint"
    RETURN_EXCHANGE = "return_exchange"
    TECHNICAL_SUPPORT = "technical_support"
    ACCOUNT_MGMT = "account_mgmt"


class ExtractedEntities(BaseModel):
    order_ids: list[str] = Field(default_factory=list)
    product_names: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    amounts: list[float] = Field(default_factory=list)
    customer_phone: str | None = None
    customer_email: str | None = None
    issue_category: str | None = None
    tracking_numbers: list[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    content: str
    source: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


def _get_msg_content(msg: Any) -> str:
    """Extract text content from a message, whether it's a dict or LangChain message object."""
    if isinstance(msg, dict):
        return msg.get("content", "")
    return getattr(msg, "content", str(msg))


def _get_msg_role(msg: Any) -> str:
    """Extract role from a message, normalizing LangChain types to standard roles.

    LangGraph add_messages converts dicts to LangChain objects:
      {"role":"user"} -> HumanMessage(type="human")
      {"role":"assistant"} -> AIMessage(type="ai")
      {"role":"system"} -> SystemMessage(type="system")
    """
    if isinstance(msg, dict):
        return msg.get("role", "")
    msg_type = getattr(msg, "type", getattr(msg, "role", ""))
    # Normalize LangChain types to standard OpenAI roles
    if msg_type == "human":
        return "user"
    if msg_type == "ai":
        return "assistant"
    return msg_type


class AgentState(BaseModel):
    """Shared state across all LangGraph nodes.

    Fields with Annotated[..., add_messages] use additive merging across nodes.
    """

    messages: Annotated[list[Any], add_messages] = Field(default_factory=list)

    # Intent and skill routing
    intent: IntentType | None = None
    intent_confidence: float = 0.0
    active_skill: SkillName | None = None
    knowledge_namespaces: list[str] = Field(default_factory=list)

    # Entity extraction
    extracted_entities: ExtractedEntities = Field(default_factory=ExtractedEntities)

    # RAG
    retrieved_docs: list[RetrievalResult] = Field(default_factory=list)
    query_rewritten: str | None = None

    # MCP Tools (OpenAI function-calling format schemas)
    available_tools: list[dict] = Field(default_factory=list)
    tool_call_count: int = 0

    # Generation
    final_answer: str | None = None
    cited_sources: list[str] = Field(default_factory=list)

    # Evaluation
    satisfaction_score: float | None = None
    needs_handoff: bool = False
    handoff_reason: str | None = None
    low_satisfaction_count: int = 0

    # Session metadata
    tenant_id: str = "default"
    customer_id: str | None = None
    session_id: str = ""
    turn_count: int = 0

    model_config = {"arbitrary_types_allowed": True}
