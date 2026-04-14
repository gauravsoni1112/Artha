"""
Agent Router — capability-based dispatch to domain agents.

Accepts a user query with a capability hint, looks up a HEALTHY agent that
declares that capability in the registry, and forwards the request to its
/run endpoint. Returns the agent's AgentResponse envelope unchanged.

Endpoint:
  POST /router/query   — dispatch to a domain agent by capability
  GET  /router/agents  — list registered agents visible to the router (proxy)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from libs.schemas.agent_envelope import AgentRequest, AgentResponse
from libs.schemas.db_models import AgentRegistryEntry
from libs.schemas.user_profile import UserProfile

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/router", tags=["agent-router"])

_DEFAULT_TIMEOUT_S = 30.0


# ── Schemas ───────────────────────────────────────────────────────────────────


class RouterQueryRequest(BaseModel):
    """
    Thin wrapper around AgentRequest that adds a *capability* routing hint.

    The capability is used to look up which agent to dispatch to.
    All other fields are forwarded verbatim in the AgentRequest.
    """

    query: str = Field(min_length=1, max_length=4000)
    capability: str = Field(
        description="Capability tag to route to, e.g. 'cashflow', 'risk', 'tax', 'goal'"
    )
    user_profile: UserProfile
    context: dict[str, Any] = Field(default_factory=dict)
    trace_id: uuid.UUID = Field(default_factory=uuid.uuid4)


class RouterQueryResponse(BaseModel):
    """AgentResponse envelope plus routing metadata."""

    routed_to: str = Field(description="agent_id that handled the request")
    agent_endpoint: str = Field(description="Endpoint the request was sent to")
    response: AgentResponse


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _pick_agent(
    capability: str,
    session: AsyncSession,
) -> AgentRegistryEntry | None:
    """
    Return the first HEALTHY agent that declares *capability*.
    Returns None if no matching agent is available.
    """
    stmt = (
        select(AgentRegistryEntry)
        .where(
            AgentRegistryEntry.status == "HEALTHY",
            AgentRegistryEntry.capabilities.contains(
                cast([capability], ARRAY(String))
            ),
        )
        .order_by(AgentRegistryEntry.agent_id)
        .limit(1)
    )
    return await session.scalar(stmt)


async def _forward_to_agent(
    agent: AgentRegistryEntry,
    request: AgentRequest,
) -> AgentResponse:
    """POST the AgentRequest to the agent's /run endpoint and return the response."""
    run_url = f"{agent.endpoint}/run"
    timeout_s = agent.timeout_ms / 1000.0

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        try:
            resp = await client.post(
                run_url,
                json=request.model_dump(mode="json"),
            )
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504,
                detail=f"Agent '{agent.agent_id}' timed out after {timeout_s}s",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Agent '{agent.agent_id}' returned {exc.response.status_code}: "
                       f"{exc.response.text[:200]}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Could not reach agent '{agent.agent_id}': {exc}",
            ) from exc

    return AgentResponse.model_validate(resp.json())


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/query", response_model=RouterQueryResponse)
async def route_query(
    body: RouterQueryRequest,
    session: AsyncSession = Depends(get_session),
) -> RouterQueryResponse:
    """
    Dispatch a query to a domain agent by capability.

    Looks up a HEALTHY agent in the registry that declares *capability*,
    forwards the full AgentRequest to its /run endpoint, and returns the
    AgentResponse together with routing metadata.

    Returns 503 if no HEALTHY agent is available for the requested capability.
    Returns 502 / 504 if the agent call fails or times out.
    """
    log.info(
        "router.query.received",
        capability=body.capability,
        trace_id=str(body.trace_id),
        query=body.query[:80],
    )

    agent = await _pick_agent(body.capability, session)
    if agent is None:
        log.warning("router.no_agent", capability=body.capability)
        raise HTTPException(
            status_code=503,
            detail=f"No healthy agent available for capability '{body.capability}'",
        )

    agent_request = AgentRequest(
        query=body.query,
        context=body.context,
        user_profile=body.user_profile,
        trace_id=body.trace_id,
        request_timestamp=datetime.now(timezone.utc),
    )

    log.info(
        "router.dispatch",
        agent_id=agent.agent_id,
        endpoint=agent.endpoint,
        trace_id=str(body.trace_id),
    )

    agent_response = await _forward_to_agent(agent, agent_request)

    log.info(
        "router.query.complete",
        agent_id=agent.agent_id,
        trace_id=str(body.trace_id),
        confidence=agent_response.confidence,
        risk_level=agent_response.risk_level,
    )

    return RouterQueryResponse(
        routed_to=agent.agent_id,
        agent_endpoint=agent.endpoint,
        response=agent_response,
    )


@router.get("/agents", response_model=list[dict])
async def list_routable_agents(
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """
    List all HEALTHY agents visible to the router with their capability tags.
    Useful for clients that want to know which capabilities are available.
    """
    stmt = (
        select(
            AgentRegistryEntry.agent_id,
            AgentRegistryEntry.capabilities,
            AgentRegistryEntry.scope,
            AgentRegistryEntry.status,
            AgentRegistryEntry.last_heartbeat,
        )
        .where(AgentRegistryEntry.status == "HEALTHY")
        .order_by(AgentRegistryEntry.agent_id)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "agent_id": r.agent_id,
            "capabilities": r.capabilities,
            "scope": r.scope,
            "status": r.status,
            "last_heartbeat": r.last_heartbeat.isoformat() if r.last_heartbeat else None,
        }
        for r in rows
    ]
