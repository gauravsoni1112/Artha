"""
Agent router — Phase 2 Single-Agent Assistant.

Endpoints:
  POST /agent/chat   — send a natural language question, get an AI answer
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import AsyncSessionLocal
from services.agent.agent import ArthaAgent
from services.agent.config import LLMConfig

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


# ── Dependency ────────────────────────────────────────────────────────────────

async def get_db_session() -> AsyncSession:  # type: ignore[return]
    async with AsyncSessionLocal() as session:
        yield session


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    owner_id: uuid.UUID = Field(description="UUID of the data owner")
    message: str = Field(min_length=1, max_length=2000, description="Natural language question")


class ChatResponse(BaseModel):
    owner_id: uuid.UUID
    message: str
    response: str
    tool_calls: list[str]


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    """
    Ask the Artha agent a natural language question about your finances.

    Example:
        {"owner_id": "...", "message": "What did I spend on groceries last month?"}
    """
    log.info("agent.chat.received", owner_id=str(body.owner_id), message_len=len(body.message))

    try:
        config = LLMConfig.from_env()
        agent = ArthaAgent(session=session, config=config)
        result = await agent.chat(
            owner_id=str(body.owner_id),
            message=body.message,
        )
    except Exception as exc:
        log.error("agent.chat.error", error=str(exc), owner_id=str(body.owner_id))
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    log.info(
        "agent.chat.complete",
        owner_id=str(body.owner_id),
        tool_calls=result["tool_calls"],
    )

    return ChatResponse(
        owner_id=body.owner_id,
        message=body.message,
        response=result["response"],
        tool_calls=result["tool_calls"],
    )
