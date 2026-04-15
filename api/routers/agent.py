"""
Agent router — Phase 3 + Phase 4 unified chat endpoint.

Endpoints:
  POST /agent/chat   — natural language question → AI answer with reasoning

Phase 3 path (default, backward-compatible):
  Uses the monolithic ArthaAgent (LangGraph planner→executor→reflect) and
  persists the conversation to chat_sessions / agent_runs tables.

Phase 4 path (opt-in via `capability` + `user_profile`):
  Routes to a domain agent via the agent registry and capability router.
  No session persistence at this layer — the domain agent handles its own context.
  Returns the same ChatResponse shape for API stability.

Switching is controlled by the presence of the `capability` field:
  - capability absent → Phase 3 ArthaAgent
  - capability present (user_profile required) → Phase 4 domain agent
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.rate_limit import limiter
from libs.schemas.user_profile import UserProfile
from services.agent.agent import ArthaAgent
from services.agent.config import LLMConfig
from services.agent.schemas import AgentAnswer

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    owner_id: uuid.UUID = Field(description="UUID of the data owner")
    message: str = Field(min_length=1, max_length=2000, description="Natural language question")
    session_id: uuid.UUID | None = Field(None, description="Session ID for multi-turn (Phase 3)")

    # ── Phase 4 fields (both required together if either is present) ──────────
    capability: str | None = Field(
        None,
        description=(
            "Capability tag to route to a domain agent "
            "(e.g. 'cashflow', 'risk', 'tax', 'goal', 'investment'). "
            "When set, user_profile is also required and the Phase 4 domain "
            "router is used instead of the monolithic Phase 3 agent."
        ),
    )
    user_profile: UserProfile | None = Field(
        None,
        description="Required when capability is set. Injected into the domain agent request.",
    )

    @model_validator(mode="after")
    def _validate_phase4_fields(self) -> "ChatRequest":
        has_cap = self.capability is not None
        has_prof = self.user_profile is not None
        if has_cap and not has_prof:
            raise ValueError("user_profile is required when capability is specified")
        if has_prof and not has_cap:
            raise ValueError("capability is required when user_profile is specified")
        return self


class ChatResponse(BaseModel):
    owner_id: uuid.UUID
    message: str
    response: str
    tool_calls: list[str]
    session_id: uuid.UUID
    run_id: uuid.UUID
    # Structured reasoning (Phase 3 scratchpad; Phase 4 agent reasoning)
    confidence: float = Field(default=1.0)
    reasoning_steps: list[str] = Field(default_factory=list)
    supporting_data: list[dict[str, Any]] = Field(default_factory=list)
    # Phase 4 routing metadata (None when Phase 3 path used)
    routed_to: str | None = Field(None, description="agent_id that handled the request (Phase 4)")


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """
    Ask Artha a natural language question about your finances.

    **Phase 3 (default):** omit `capability` — uses the monolithic reasoning agent.

    **Phase 4:** set `capability` + `user_profile` — routes to a domain agent
    (cashflow / investment / tax / risk / goal).
    """
    log.info(
        "agent.chat.received",
        owner_id=str(body.owner_id),
        capability=body.capability,
        message_len=len(body.message),
    )

    if body.capability:
        return await _handle_domain_agent(body, session)
    else:
        return await _handle_phase3_agent(body, session)


# ── Phase 3 path ──────────────────────────────────────────────────────────────


async def _handle_phase3_agent(body: ChatRequest, session: AsyncSession) -> ChatResponse:
    try:
        config = LLMConfig.from_env()
        agent = ArthaAgent(session=session, config=config)
        result = await agent.chat(
            owner_id=str(body.owner_id),
            message=body.message,
            session_id=str(body.session_id) if body.session_id else None,
        )
    except Exception as exc:
        log.error("agent.chat.phase3.error", error=str(exc), owner_id=str(body.owner_id))
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    structured = AgentAnswer.from_agent_result(
        response=result["response"],
        scratchpad=result.get("scratchpad"),
        confidence_score=result.get("confidence_score"),
    )

    log.info(
        "agent.chat.phase3.complete",
        owner_id=str(body.owner_id),
        tool_calls=result["tool_calls"],
        confidence=structured.confidence,
    )

    return ChatResponse(
        owner_id=body.owner_id,
        message=body.message,
        response=result["response"],
        tool_calls=result["tool_calls"],
        session_id=uuid.UUID(result["session_id"]),
        run_id=uuid.UUID(result["run_id"]),
        confidence=structured.confidence,
        reasoning_steps=structured.reasoning_steps,
        supporting_data=structured.supporting_data,
        routed_to=None,
    )


# ── Phase 4 path ──────────────────────────────────────────────────────────────


async def _handle_domain_agent(body: ChatRequest, session: AsyncSession) -> ChatResponse:
    """Dispatch to a registered domain agent by capability, return ChatResponse."""
    from api.routers.agent_router import _forward_to_agent, _pick_agent
    from libs.schemas.agent_envelope import AgentRequest

    capability = body.capability  # validated non-None in model_validator
    user_profile = body.user_profile  # validated non-None

    agent_entry = await _pick_agent(capability, session)
    if agent_entry is None:
        log.warning("agent.chat.no_domain_agent", capability=capability)
        raise HTTPException(
            status_code=503,
            detail=f"No healthy agent available for capability '{capability}'. "
                   "Ensure the domain agent container is running and registered.",
        )

    trace_id = uuid.uuid4()
    agent_request = AgentRequest(
        query=body.message,
        user_profile=user_profile,
        context={"owner_id": str(body.owner_id)},
        trace_id=trace_id,
    )

    log.info(
        "agent.chat.phase4.dispatch",
        capability=capability,
        agent_id=agent_entry.agent_id,
        trace_id=str(trace_id),
    )

    agent_response = await _forward_to_agent(agent_entry, agent_request)

    # Map AgentResponse → ChatResponse (stable API contract for callers)
    answer = agent_response.result.get("answer", "")
    if not answer:
        answer = str(agent_response.result)

    supporting_data = [
        {
            "data_tier": agent_response.data_tier,
            "data_freshness_hours": agent_response.data_freshness_hours,
            "risk_level": agent_response.risk_level,
            "warnings": agent_response.warnings,
            "fallback_used": agent_response.fallback_used,
        }
    ]

    log.info(
        "agent.chat.phase4.complete",
        agent_id=agent_entry.agent_id,
        confidence=agent_response.confidence,
        trace_id=str(trace_id),
    )

    return ChatResponse(
        owner_id=body.owner_id,
        message=body.message,
        response=answer,
        tool_calls=[],          # domain agents don't surface tool names at this layer
        session_id=trace_id,    # no persistent session — trace_id serves as correlation
        run_id=agent_response.trace_id,
        confidence=agent_response.confidence,
        reasoning_steps=[agent_response.reasoning] if agent_response.reasoning else [],
        supporting_data=supporting_data,
        routed_to=agent_entry.agent_id,
    )
