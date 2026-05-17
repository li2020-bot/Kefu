"""Intent classification node - identifies user intent from messages."""

import re

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from src.agent.state import AgentState, IntentType, _get_msg_content, _get_msg_role
from src.core.config import settings

from src.agent.nodes.intent_classifier import IntentClassifier

# Patterns indicating the assistant is asking the user for data
_ASSISTANT_ASKING_PATTERNS = [
    r"(?:请|麻烦|方便)(?:提供|告诉|输入|说|发|给一下|发一下)",
    r"(?:手机号|电话|号码|联系方式|订单号|快递单号|地址|姓名|邮箱|验证码|身份证)",
    r"[?？]",
]

# Common data formats that look like slot-filling
_DATA_PATTERNS = [
    r"^\d{11}$",              # phone number
    r"^ORD-\d{8}-\d{4}$",     # order ID
    r"^\d{6}$",               # verification code
    r"^\w+@\w+\.\w+$",        # email
    r"^(是|对|嗯|好|可以|行|ok|yes|没有|不是|不对|no)$",  # yes/no
]

# Patterns indicating the user has a question/request — disqualifies slot-filling
_QUESTION_PATTERNS = [
    r"[?？]",
    r"(?:怎么|如何|为什么|什么|哪里|哪个|多少钱|多久|能不能|可以吗|行吗|对吗)",
    r"(?:帮我|查一下|查查|查一查|看看|找一下|搜一下|问一下|告诉我)",
    r"(?:物流|订单|退款|退货|换货|发货|快递|查询)",
]


def _is_slot_filling(user_text: str, state: AgentState) -> bool:
    """Fast-path: detect if the user is just providing data in response to an agent question.

    Only triggers when the user message is PURE data — no questions,
    requests, or task descriptions mixed in.
    """
    user_text_stripped = user_text.strip()

    # Check if user message is short data-like response
    is_short = len(user_text_stripped) <= 30
    is_data = any(re.fullmatch(p, user_text_stripped) for p in _DATA_PATTERNS)

    if not (is_short or is_data):
        return False

    # Reject if the user message contains question/request patterns
    # e.g. "138xxxx, 帮我查物流" is NOT slot-filling — it has a task
    if any(re.search(p, user_text_stripped) for p in _QUESTION_PATTERNS):
        return False

    # Check if the preceding assistant message was asking for information
    for msg in list(reversed(state.messages))[1:]:
        role = _get_msg_role(msg)
        if role == "assistant":
            content = _get_msg_content(msg)
            return any(re.search(p, content) for p in _ASSISTANT_ASKING_PATTERNS)
        elif role == "user":
            break

    return False


async def classify_intent(state: AgentState) -> dict:
    """Classify user intent from the latest message using BERT semantic similarity."""
    if not state.messages:
        return {"intent": IntentType.GENERAL_INQUIRY, "intent_confidence": 0.5}

    last_msg = state.messages[-1]
    user_text = _get_msg_content(last_msg)

    # Slot-filling detection: user is just providing data (phone, order ID, etc.)
    if _is_slot_filling(user_text, state):
        logger.info("slot_filling_detected", user_text=user_text[:30])
        return {"intent": IntentType.SLOT_FILLING, "intent_confidence": 0.95}

    # BERT semantic similarity classification
    try:
        classifier = IntentClassifier.get_instance()
        intent, confidence = await classifier.classify(user_text)

        # Diagnostic: log top-3 predictions for debugging misclassifications
        top_k = await classifier.classify_top_k(user_text, k=3)
        top_k_str = ", ".join(f"{i.value}:{c:.3f}" for i, c in top_k)
        logger.info("bert_intent_top3", top3=top_k_str, user_text=user_text[:50])

        logger.info("bert_intent_classified", intent=intent.value, confidence=round(confidence, 3))
        return {"intent": intent, "intent_confidence": confidence}

    except Exception as e:
        logger.warning("intent_classify_failed", error=str(e))
        return {"intent": IntentType.GENERAL_INQUIRY, "intent_confidence": 0.3}
