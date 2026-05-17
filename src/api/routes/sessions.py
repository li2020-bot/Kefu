"""Session management API routes."""

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.middleware.auth import verify_tenant

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionInfo(BaseModel):
    session_id: str
    status: str
    active_skill: str | None = None
    message_count: int = 0
    created_at: str = ""


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str, tenant: str = Depends(verify_tenant)):
    """Get session information."""
    # In production: fetch from PostgresSaver
    return SessionInfo(
        session_id=session_id,
        status="active",
    )


@router.delete("/{session_id}")
async def close_session(session_id: str, tenant: str = Depends(verify_tenant)):
    """Close a session."""
    logger.info("session_closed", session_id=session_id)
    return {"status": "closed", "session_id": session_id}
