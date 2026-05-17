"""Feedback API routes."""

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.middleware.auth import verify_tenant

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    session_id: str
    rating: int = Field(ge=1, le=5, description="1-5 rating")
    comment: str | None = None
    category: str | None = Field(default=None, description="Feedback category")


class FeedbackResponse(BaseModel):
    status: str
    message: str


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest, tenant: str = Depends(verify_tenant)):
    """Submit feedback for a conversation."""
    logger.info(
        "feedback_received",
        session_id=request.session_id,
        rating=request.rating,
        category=request.category,
    )

    if request.rating <= 2:
        logger.info("low_rating_alert", session_id=request.session_id, rating=request.rating, comment=request.comment)

    return FeedbackResponse(
        status="received",
        message="感谢您的反馈！我们会持续改进服务质量。",
    )
