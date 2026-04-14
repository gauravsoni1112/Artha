"""
Agent Registry — CRUD endpoints.

Agents call PUT /registry/agents on startup (via self_register.py).
The router calls GET /registry/agents/by-capability/{capability} to dispatch.

Endpoints:
  PUT  /registry/agents                          — upsert registration (idempotent)
  GET  /registry/agents                          — list all agents
  GET  /registry/agents/{agent_id}               — single agent
  GET  /registry/agents/by-capability/{cap}      — all HEALTHY agents for a capability
  DELETE /registry/agents/{agent_id}             — deregister
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from libs.schemas.db_models import AgentRegistryEntry

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/registry", tags=["registry"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class AgentRegistrationPayload(BaseModel):
    """Sent by agents on startup via self_register.py."""

    agent_id: str = Field(description="Stable snake_case agent identifier")
    endpoint: str = Field(description="Base URL of the agent container")
    health_endpoint: str = Field(description="Health-check URL")
    capabilities: list[str] = Field(description="Capability tags this agent handles")
    schema_version: str = Field("1.0")
    timeout_ms: int = Field(10_000)
    fallback_strategy: str = Field("cached_response")
    cache_ttl_hours: float = Field(1.0)
    scope: str = Field("individual")


class AgentRegistrationResponse(BaseModel):
    agent_id: str
    endpoint: str
    health_endpoint: str
    capabilities: list[str]
    schema_version: str
    timeout_ms: int
    fallback_strategy: str
    cache_ttl_hours: float
    scope: str
    status: str
    last_heartbeat: datetime | None
    registered_at: datetime
    updated_at: datetime


def _to_response(entry: AgentRegistryEntry) -> AgentRegistrationResponse:
    return AgentRegistrationResponse(
        agent_id=entry.agent_id,
        endpoint=entry.endpoint,
        health_endpoint=entry.health_endpoint,
        capabilities=entry.capabilities,
        schema_version=entry.schema_version,
        timeout_ms=entry.timeout_ms,
        fallback_strategy=entry.fallback_strategy,
        cache_ttl_hours=float(entry.cache_ttl_hours),
        scope=entry.scope,
        status=entry.status,
        last_heartbeat=entry.last_heartbeat,
        registered_at=entry.registered_at,
        updated_at=entry.updated_at,
    )


# ── Routes ────────────────────────────────────────────────────────────────────


@router.put("/agents", response_model=AgentRegistrationResponse)
async def register_agent(
    payload: AgentRegistrationPayload,
    session: AsyncSession = Depends(get_session),
) -> AgentRegistrationResponse:
    """
    Register or update an agent.  Called by each agent container on startup.
    Idempotent — re-registering the same agent_id updates all fields and
    resets last_heartbeat and status to HEALTHY.
    """
    now = datetime.now(timezone.utc)

    stmt = (
        pg_insert(AgentRegistryEntry)
        .values(
            agent_id=payload.agent_id,
            endpoint=payload.endpoint,
            health_endpoint=payload.health_endpoint,
            capabilities=payload.capabilities,
            schema_version=payload.schema_version,
            timeout_ms=payload.timeout_ms,
            fallback_strategy=payload.fallback_strategy,
            cache_ttl_hours=payload.cache_ttl_hours,
            scope=payload.scope,
            status="HEALTHY",
            last_heartbeat=now,
            registered_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["agent_id"],
            set_={
                "endpoint": payload.endpoint,
                "health_endpoint": payload.health_endpoint,
                "capabilities": payload.capabilities,
                "schema_version": payload.schema_version,
                "timeout_ms": payload.timeout_ms,
                "fallback_strategy": payload.fallback_strategy,
                "cache_ttl_hours": payload.cache_ttl_hours,
                "scope": payload.scope,
                "status": "HEALTHY",
                "last_heartbeat": now,
                "updated_at": now,
            },
        )
        .returning(AgentRegistryEntry)
    )

    result = await session.execute(stmt)
    entry = result.scalar_one()
    await session.commit()

    log.info(
        "registry.agent.registered",
        agent_id=payload.agent_id,
        endpoint=payload.endpoint,
        capabilities=payload.capabilities,
    )
    return _to_response(entry)


@router.get("/agents", response_model=list[AgentRegistrationResponse])
async def list_agents(
    status: str | None = None,
    scope: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[AgentRegistrationResponse]:
    """List all registered agents. Optionally filter by status or scope."""
    stmt = select(AgentRegistryEntry)
    if status:
        stmt = stmt.where(AgentRegistryEntry.status == status.upper())
    if scope:
        stmt = stmt.where(AgentRegistryEntry.scope == scope.lower())
    stmt = stmt.order_by(AgentRegistryEntry.agent_id)

    entries = (await session.scalars(stmt)).all()
    return [_to_response(e) for e in entries]


@router.get("/agents/by-capability/{capability}", response_model=list[AgentRegistrationResponse])
async def agents_by_capability(
    capability: str,
    session: AsyncSession = Depends(get_session),
) -> list[AgentRegistrationResponse]:
    """Return all HEALTHY agents that declare the given capability."""
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import ARRAY
    from sqlalchemy import String

    stmt = select(AgentRegistryEntry).where(
        AgentRegistryEntry.status == "HEALTHY",
        AgentRegistryEntry.capabilities.contains(cast([capability], ARRAY(String))),
    )
    entries = (await session.scalars(stmt)).all()
    return [_to_response(e) for e in entries]


@router.get("/agents/{agent_id}", response_model=AgentRegistrationResponse)
async def get_agent(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
) -> AgentRegistrationResponse:
    """Get a single registered agent by agent_id."""
    entry = await session.get(AgentRegistryEntry, agent_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return _to_response(entry)


@router.delete("/agents/{agent_id}", status_code=204)
async def deregister_agent(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove an agent from the registry."""
    entry = await session.get(AgentRegistryEntry, agent_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    await session.delete(entry)
    await session.commit()
    log.info("registry.agent.deregistered", agent_id=agent_id)
