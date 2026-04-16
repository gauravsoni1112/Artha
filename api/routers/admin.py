"""
Admin router — admin-only operational endpoints.

GET /admin/audit-log          — paginated recommendations + events across all owners
GET /admin/ingestion-runs     — cross-owner ingestion run history
GET /admin/agents             — agent registry passthrough (read-only)
GET /admin/quarantine         — quarantined records pending review
PATCH /admin/quarantine/{id}  — resolve / reject a quarantine record
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.deps import require_admin
from libs.schemas.db_models import (
    AgentRegistryEntry,
    IngestionRun,
    Owner,
    Recommendation,
    RecommendationEvent,
    TransactionQuarantine,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AuditRecommendationOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    query: str
    composite_confidence: float
    current_state: str
    created_at: datetime
    event_count: int


class AuditEventOut(BaseModel):
    id: uuid.UUID
    recommendation_id: uuid.UUID
    event_type: str
    actor_user_id: uuid.UUID | None
    payload: dict[str, Any]
    created_at: datetime


class IngestionRunOut(BaseModel):
    id: uuid.UUID
    source: str
    trigger_type: str
    status: str
    records_fetched: int
    records_passed: int
    records_quarantined: int
    started_at: datetime
    completed_at: datetime | None


class AgentStatusOut(BaseModel):
    agent_id: str
    capabilities: list[str]
    status: str
    last_heartbeat: datetime | None
    endpoint: str
    scope: str


class QuarantineOut(BaseModel):
    id: uuid.UUID
    failure_stage: str
    failure_reasons: list[Any]
    raw_amount_text: str | None
    raw_date_text: str | None
    quarantine_status: str
    created_at: datetime


class PatchQuarantineRequest(BaseModel):
    quarantine_status: str  # RESOLVED | REJECTED
    resolution_notes: str | None = None
    resolved_by: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/audit-log", response_model=list[AuditRecommendationOut])
async def list_audit_log(
    _admin: Annotated[Owner, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
    owner_id: uuid.UUID | None = Query(default=None, description="Filter by owner"),
    state: str | None = Query(default=None, description="Filter by current_state"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[AuditRecommendationOut]:
    q = select(Recommendation).order_by(desc(Recommendation.created_at))
    if owner_id is not None:
        q = q.where(Recommendation.owner_id == owner_id)
    if state is not None:
        q = q.where(Recommendation.current_state == state)
    q = q.offset(offset).limit(limit)

    result = await session.execute(q)
    recs = result.scalars().all()

    out = []
    for rec in recs:
        # Count events without loading them all
        event_result = await session.execute(
            select(RecommendationEvent).where(RecommendationEvent.recommendation_id == rec.id)
        )
        event_count = len(event_result.scalars().all())
        out.append(
            AuditRecommendationOut(
                id=rec.id,
                owner_id=rec.owner_id,
                query=rec.query,
                composite_confidence=rec.composite_confidence,
                current_state=rec.current_state,
                created_at=rec.created_at,
                event_count=event_count,
            )
        )
    return out


@router.get("/audit-log/{recommendation_id}/events", response_model=list[AuditEventOut])
async def get_recommendation_events(
    recommendation_id: uuid.UUID,
    _admin: Annotated[Owner, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> list[AuditEventOut]:
    result = await session.execute(
        select(RecommendationEvent)
        .where(RecommendationEvent.recommendation_id == recommendation_id)
        .order_by(RecommendationEvent.created_at)
    )
    return result.scalars().all()


@router.get("/ingestion-runs", response_model=list[IngestionRunOut])
async def list_all_ingestion_runs(
    _admin: Annotated[Owner, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
    source: str | None = Query(default=None),
    run_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[IngestionRunOut]:
    q = select(IngestionRun).order_by(desc(IngestionRun.started_at))
    if source is not None:
        q = q.where(IngestionRun.source == source)
    if run_status is not None:
        q = q.where(IngestionRun.status == run_status)
    q = q.offset(offset).limit(limit)

    result = await session.execute(q)
    return result.scalars().all()


@router.get("/agents", response_model=list[AgentStatusOut])
async def list_agents(
    _admin: Annotated[Owner, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> list[AgentStatusOut]:
    result = await session.execute(
        select(AgentRegistryEntry).order_by(AgentRegistryEntry.agent_id)
    )
    agents = result.scalars().all()
    return [
        AgentStatusOut(
            agent_id=a.agent_id,
            capabilities=a.capabilities,
            status=a.status,
            last_heartbeat=a.last_heartbeat,
            endpoint=a.endpoint,
            scope=a.scope,
        )
        for a in agents
    ]


@router.get("/quarantine", response_model=list[QuarantineOut])
async def list_quarantine(
    _admin: Annotated[Owner, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
    quarantine_status: str = Query(default="PENDING_REVIEW"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[QuarantineOut]:
    result = await session.execute(
        select(TransactionQuarantine)
        .where(TransactionQuarantine.quarantine_status == quarantine_status)
        .order_by(desc(TransactionQuarantine.created_at))
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


@router.patch("/quarantine/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def resolve_quarantine(
    record_id: uuid.UUID,
    body: PatchQuarantineRequest,
    _admin: Annotated[Owner, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> None:
    from fastapi import HTTPException
    from datetime import timezone

    result = await session.execute(
        select(TransactionQuarantine).where(TransactionQuarantine.id == record_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Quarantine record not found")

    allowed = {"RESOLVED", "REJECTED"}
    if body.quarantine_status not in allowed:
        raise HTTPException(status_code=422, detail=f"quarantine_status must be one of {allowed}")

    record.quarantine_status = body.quarantine_status
    record.resolution_notes = body.resolution_notes
    record.resolved_by = body.resolved_by or str(_admin.id)
    record.resolved_at = datetime.now(timezone.utc)
    await session.commit()
    log.info("admin.quarantine_resolved", record_id=str(record_id), status=body.quarantine_status)
