"""Satisfaction evaluation node - evaluates response quality."""

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)

from src.agent.state import AgentState, _get_msg_content, _get_msg_role
from src.core.config import settings


# Keywords that indicate user dissatisfaction
DISSATISFACTION_KEYWORDS = [
    "不满意", "不行", "没用", "听不懂", "答非所问",
    "还是不行", "解决不了", "你理解错了", "不是这个意思",
    "转人工", "人工客服", "找你们经理", "找主管",
    "太差了", "什么鬼", "无语", "......",
]


async def evaluate_satisfaction(state: AgentState) -> dict:
    """Evaluate the quality of the last interaction.

    Uses keyword heuristics for fast evaluation. In production,
    this would use an LLM-based quality assessment.
    """
    if not state.messages:
        return {"satisfaction_score": 5.0, "needs_handoff": False, "pending_handoff": False}

    # Check last user message for dissatisfaction signals
    last_user_msg = None
    for msg in reversed(state.messages):
        if _get_msg_role(msg) == "user":
            last_user_msg = _get_msg_content(msg)
            break

    # Handle handoff confirmation button clicks
    if last_user_msg in ["转人工", "确认转人工"]:
        return {
            "needs_handoff": True,
            "handoff_reason": "User confirmed handoff via button",
            "pending_handoff": False,
            "low_satisfaction_count": 0,
        }

    if last_user_msg in ["继续", "取消转接", "不需要转人工"]:
        return {
            "pending_handoff": False,
            "low_satisfaction_count": 0,
        }

    if not last_user_msg:
        return {"satisfaction_score": 5.0, "pending_handoff": False}

    # Check for explicit handoff request
    if any(kw in last_user_msg for kw in ["转人工", "人工客服", "找经理", "找主管"]):
        return {
            "satisfaction_score": 1.0,
            "needs_handoff": True,
            "handoff_reason": "User requested human agent",
            "pending_handoff": False,
        }

    # Check for dissatisfaction keywords
    dissatisfaction_count = sum(1 for kw in DISSATISFACTION_KEYWORDS if kw in last_user_msg)
    if dissatisfaction_count > 0:
        score = max(1.0, 4.0 - dissatisfaction_count * 1.5)
        new_low_count = state.low_satisfaction_count + 1
        needs_handoff = new_low_count >= settings.handoff_unsatisfied_threshold

        if needs_handoff:
            return {
                "satisfaction_score": score,
                "low_satisfaction_count": new_low_count,
                "pending_handoff": True,
                "pending_handoff_reason": f"连续 {new_low_count} 次表达不满，是否需要转接人工客服？",
            }

        return {
            "satisfaction_score": score,
            "low_satisfaction_count": new_low_count,
            "pending_handoff": False,
        }

    # Reset low satisfaction counter on positive interaction
    return {
        "satisfaction_score": 4.5,
        "low_satisfaction_count": 0,
        "pending_handoff": False,
    }
