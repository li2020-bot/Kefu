"""Chat API routes - core conversation endpoints with streaming support."""

import asyncio
import json
import uuid

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent.graph import agent_graph

from src.api.middleware.auth import verify_tenant
from src.core.security import PIIFilter, PromptInjectionGuard

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(description="User message text")
    session_id: str | None = Field(default=None, description="Session ID for continuing conversation")
    customer_id: str | None = Field(default=None, description="Customer identifier")
    tenant_id: str = Field(default="default")


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    skill: str | None = None
    intent: str | None = None
    sources: list[str] = Field(default_factory=list)
    needs_handoff: bool = False
    handoff_reason: str | None = None
    pending_handoff: bool = False
    pending_handoff_reason: str | None = None


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, tenant: str = Depends(verify_tenant)):
    """Send a message and get the full AI response (non-streaming)."""
    # Security checks
    if PromptInjectionGuard.detect(request.message):
        raise HTTPException(status_code=400, detail="Invalid input detected")

    # Mask PII in logs
    safe_message = PIIFilter.mask(request.message)
    logger.info("chat_request", session_id=request.session_id, message=safe_message)

    # Create or reuse session
    session_id = request.session_id or str(uuid.uuid4())

    config = {"configurable": {"thread_id": session_id}}

    try:
        # Only pass the new user message — the checkpointer will merge it with
        # the saved state. Do NOT pass a full AgentState with defaults, as that
        # would overwrite active_skill, available_tools, etc. from the previous turn.
        result = await agent_graph.ainvoke(
            {"messages": [{"role": "user", "content": request.message}]},
            config,
        )

        # Verify add_messages is appending and state fields are preserved from checkpoint
        msg_count = len(result.get("messages", []))
        tools_count = len(result.get("available_tools", []))
        active_skill = result.get("active_skill")
        logger.info(
            "state_checkpoint_verify",
            session_id=session_id,
            msg_count=msg_count,
            active_skill=str(active_skill),
            tools_count=tools_count,
        )

        answer = result.get("final_answer", "抱歉，我暂时无法处理您的问题。")

        # Handle enum/non-dict values from AgentState (active_skill -> SkillName, intent -> IntentType, retrieved_docs -> RetrievalResult)
        skill_val = result.get("active_skill")
        skill_str = skill_val.value if hasattr(skill_val, "value") else (str(skill_val) if skill_val else None)

        intent_val = result.get("intent")
        intent_str = intent_val.value if hasattr(intent_val, "value") else (str(intent_val) if intent_val else None)

        sources = [
            doc.source if hasattr(doc, "source") else doc.get("source", "")
            for doc in result.get("retrieved_docs", [])
        ]

        return ChatResponse(
            session_id=session_id,
            answer=answer,
            skill=skill_str,
            intent=intent_str,
            sources=sources,
            needs_handoff=result.get("needs_handoff", False),
            handoff_reason=result.get("handoff_reason"),
            pending_handoff=result.get("pending_handoff", False),
            pending_handoff_reason=result.get("pending_handoff_reason"),
        )
    except Exception as e:
        logger.error("chat_error", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@router.get("/{session_id}/stream")
async def chat_stream(session_id: str, message: str, tenant: str = Depends(verify_tenant)):
    """SSE streaming endpoint for token-by-token response."""
    if PromptInjectionGuard.detect(message):
        raise HTTPException(status_code=400, detail="Invalid input detected")

    async def event_generator():
        try:
            config = {"configurable": {"thread_id": session_id}}

            # Only pass the new user message to avoid overwriting saved state fields
            async for event in agent_graph.astream_events(
                {"messages": [{"role": "user", "content": message}]}, config, version="v2"
            ):
                event_type = event.get("event", "")

                if event_type == "on_chat_model_stream":
                    content = event.get("data", {}).get("chunk", "")
                    if content:
                        yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

                elif event_type == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name})}\n\n"

                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    yield f"data: {json.dumps({'type': 'tool_end', 'tool': tool_name})}\n\n"

            yield f"data: {json.dumps({'type': 'end', 'session_id': session_id})}\n\n"

        except Exception as e:
            logger.error("stream_error", session_id=session_id, error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
