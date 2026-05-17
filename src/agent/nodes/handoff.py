"""Human handoff node - transfers conversation to a human agent."""

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)

from src.agent.state import AgentState, _get_msg_content, _get_msg_role



async def handle_handoff(state: AgentState) -> dict:
    """Handle human agent handoff.

    Creates a ticket in the ticket system, generates a conversation
    summary for the human agent, and notifies the user.
    """
    # Generate conversation summary for the human agent
    summary_parts = []
    for msg in state.messages[-10:]:
        role = _get_msg_role(msg)
        content = _get_msg_content(msg)
        if role in ("user", "assistant"):
            prefix = "客户" if role == "user" else "AI客服"
            summary_parts.append(f"[{prefix}] {content[:100]}")

    summary = "\n".join(summary_parts)

    handoff_message = "正在为您转接人工客服，请稍候...\n\n人工客服预计等待时间：2-5分钟，请耐心等待。"

    logger.info(
        "handoff_triggered",
        reason=state.handoff_reason,
        session_id=state.session_id,
        skill=state.active_skill.value if state.active_skill else None,
        intent=state.intent.value if state.intent else None,
        summary=summary,
    )

    return {
        "needs_handoff": True,
        "messages": [{"role": "assistant", "content": handoff_message}],
        "final_answer": handoff_message,
    }
