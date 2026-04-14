"""
Agent router — Phase 2 Single-Agent Assistant.

Endpoints:
  POST /agent/chat   — send a natural language question, get an AI answer
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.rate_limit import limiter
from services.agent.agent import ArthaAgent
from services.agent.config import LLMConfig

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    owner_id: uuid.UUID = Field(description="UUID of the data owner")
    message: str = Field(min_length=1, max_length=2000, description="Natural language question")
    session_id: uuid.UUID | None = Field(None, description="Optional session ID for multi-turn conversations")


class ChatResponse(BaseModel):
    owner_id: uuid.UUID
    message: str
    response: str
    tool_calls: list[str]
    session_id: uuid.UUID
    run_id: uuid.UUID


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """
    Ask the Artha agent a natural language question about your finances.

    Example:
        {"owner_id": "...", "message": "What did I spend on groceries last month?"}
    """
    log.info(
        "agent.chat.received",
        owner_id=str(body.owner_id),
        message_len=len(body.message),
        session_id=str(body.session_id) if body.session_id else None,
    )

    try:
        config = LLMConfig.from_env()
        agent = ArthaAgent(session=session, config=config)
        result = await agent.chat(
            owner_id=str(body.owner_id),
            message=body.message,
            session_id=str(body.session_id) if body.session_id else None,
        )
    except Exception as exc:
        log.error("agent.chat.error", error=str(exc), owner_id=str(body.owner_id))
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    log.info(
        "agent.chat.complete",
        owner_id=str(body.owner_id),
        tool_calls=result["tool_calls"],
        session_id=result.get("session_id"),
        run_id=result.get("run_id"),
    )

    return ChatResponse(
        owner_id=body.owner_id,
        message=body.message,
        response=result["response"],
        tool_calls=result["tool_calls"],
        session_id=uuid.UUID(result["session_id"]),
        run_id=uuid.UUID(result["run_id"]),
    )
