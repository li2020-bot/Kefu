"""Main LangGraph StateGraph - assembles all nodes and edges for the customer service agent."""

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.agent.nodes.evaluation import evaluate_satisfaction
from src.agent.nodes.generation import generate_answer
from src.agent.nodes.handoff import handle_handoff
from src.agent.nodes.intent import classify_intent
from src.agent.nodes.rag import retrieve_knowledge
from src.agent.nodes.skill_dispatch import dispatch_skill
from src.agent.state import AgentState, IntentType

checkpointer = MemorySaver()


def _should_handoff(state: AgentState) -> str:
    """Conditional edge: check if handoff is needed (post-evaluation)."""
    if state.needs_handoff:
        return "handoff"
    return "end"


def _should_skip_to_handoff(state: AgentState) -> str:
    """Conditional edge after skill_dispatch: skip directly to handoff if already flagged."""
    if state.needs_handoff:
        return "handoff"
    return "continue"


def _route_after_intent(state: AgentState) -> str:
    """Route based on intent: slot-filling goes through skill_dispatch but preserves active skill."""
    if state.intent == IntentType.HUMAN_HANDOFF:
        return "handoff"
    return "skill_dispatch"


def build_graph() -> StateGraph:
    """Build and compile the customer service agent StateGraph.

    Flow:
    START -> intent_classify -> [human_handoff -> handoff]
                               -> [skill_dispatch -> retrieve_knowledge -> generate_answer]
                               -> evaluate -> [handoff | END]
    Slot-filling goes through skill_dispatch but preserves the active skill and tools.
    """
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("intent_classify", classify_intent)
    workflow.add_node("skill_dispatch", dispatch_skill)
    workflow.add_node("retrieve_knowledge", retrieve_knowledge)
    workflow.add_node("generate_answer", generate_answer)
    workflow.add_node("evaluate", evaluate_satisfaction)
    workflow.add_node("handoff", handle_handoff)

    # Edges
    workflow.add_edge(START, "intent_classify")

    # Conditional edge: human_handoff goes to handoff, everything else (including slot_filling) goes through skill_dispatch
    workflow.add_conditional_edges(
        "intent_classify",
        _route_after_intent,
        {
            "handoff": "handoff",
            "skill_dispatch": "skill_dispatch",
        },
    )

    workflow.add_conditional_edges(
        "skill_dispatch",
        _should_skip_to_handoff,
        {
            "handoff": "handoff",
            "continue": "retrieve_knowledge",
        },
    )
    workflow.add_edge("retrieve_knowledge", "generate_answer")
    workflow.add_edge("generate_answer", "evaluate")

    # Conditional edge: handoff or end
    workflow.add_conditional_edges(
        "evaluate",
        _should_handoff,
        {
            "handoff": "handoff",
            "end": END,
        },
    )
    workflow.add_edge("handoff", END)

    return workflow.compile(checkpointer=checkpointer)


# Singleton graph instance
agent_graph = build_graph()
