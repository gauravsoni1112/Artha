"""
Orchestrator API — Phase 5 Planner + Critic endpoints.

Endpoints:
  POST /orchestrator/recommendation          — full pipeline → auditable recommendation
  POST /orchestrator/recommendation/{id}/events — surface / accept / reject / …

The full pipeline per request:
  scope resolve → snapshot → decompose → dispatch → compose → critic → audit write

Singletons (registry, breaker, response_cache) are stored in app.state and
accessed via FastAPI dependencies.  Override them in tests via dependency_overrides.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.deps import current_owner
from libs.confidence.composition import AgentConfidenceInput, compose
from libs.confidence.tier import FallbackTier
from libs.schemas.db_models import (
    Owner,
    Recommendation,
    UserProfile as UserProfileORM,
    UserProfileScope,
)
from libs.schemas.enums import RecommendationState
from libs.schemas.user_profile import EMI, FinancialGoal, IncomeSource, UserProfile
from libs.telemetry.langfuse_handler import create_trace, flush as lf_flush, score_trace
from libs.telemetry.tracing import start_span
from services.orchestrator.audit import (
    InvalidTransitionError,
    create_recommendation,
    create_snapshot,
    transition_state,
)
from services.orchestrator.breaker import InMemoryBreakerStore
from services.orchestrator.cache import AgentResponseCache
from services.orchestrator.critic import evaluate as critic_evaluate
from services.orchestrator.decompose import RegisteredAgent, decompose, decompose_with_llm_fallback
from services.orchestrator.synthesizer import synthesize
from services.orchestrator.dispatch import dispatch_plan
from services.orchestrator.metrics import (
    record_breaker_state,
    record_dispatch_tier,
    record_pipeline_stage,
    record_recommendation,
    record_transition,
)
from services.orchestrator.registry import AgentRegistryCache
from services.orchestrator.scope import (
    ScopeMember,
    query_implies_family,
    resolve_scope,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


# ---------------------------------------------------------------------------
# App-state dependencies  (override in tests via dependency_overrides)
# ---------------------------------------------------------------------------


def get_registry(request: Request) -> AgentRegistryCache:
    return request.app.state.registry


def get_breaker(request: Request) -> InMemoryBreakerStore:
    return request.app.state.breaker


def get_response_cache(request: Request) -> AgentResponseCache:
    return request.app.state.response_cache


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class RecommendationRequest(BaseModel):
    owner_id: uuid.UUID
    query: str = Field(..., min_length=1, max_length=2000)


class RecommendationResponse(BaseModel):
    recommendation_id: uuid.UUID
    final_confidence: float
    state: str
    warnings: list[str]
    gaps: list[str]
    final_output: dict[str, Any]
    synthesized_answer: str = ""
    plan_json: dict[str, Any] | None = None
    agent_outputs_json: list[dict[str, Any]] | None = None


class EventRequest(BaseModel):
    event_type: RecommendationState
    actor_user_id: uuid.UUID
    payload: dict[str, Any] = Field(default_factory=dict)


class EventResponse(BaseModel):
    event_id: uuid.UUID
    recommendation_id: uuid.UUID
    event_type: str
    current_state: str


class RecommendationSummary(BaseModel):
    """Lightweight recommendation row for history listing."""

    id: uuid.UUID
    query: str
    composite_confidence: float
    current_state: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _load_profile_and_members(
    session: AsyncSession,
    owner_id: uuid.UUID,
) -> tuple[UserProfile, uuid.UUID] | None:
    """
    Load UserProfileORM + Owner and build a Pydantic UserProfile.
    Returns (pydantic_profile, profile_id) or None if no profile exists.
    """
    profile_orm: UserProfileORM | None = await session.scalar(
        select(UserProfileORM).where(UserProfileORM.owner_id == owner_id)
    )
    if profile_orm is None:
        return None

    owner: Owner | None = await session.get(Owner, owner_id)
    name = owner.name if owner else "User"

    pydantic_profile = UserProfile(
        owner_id=owner_id,
        name=name,
        risk_appetite=profile_orm.risk_appetite,
        age=profile_orm.age,
        is_family_scope=profile_orm.is_family_scope,
        total_monthly_income_paise=profile_orm.total_monthly_income_paise,
        income_sources=[IncomeSource(**s) for s in (profile_orm.income_sources_json or [])],
        emis=[EMI(**e) for e in (profile_orm.emis_json or [])],
    )
    return pydantic_profile, profile_orm.id


async def _load_scope_members(
    session: AsyncSession,
    profile_id: uuid.UUID,
) -> list[ScopeMember]:
    rows = await session.execute(
        select(UserProfileScope).where(UserProfileScope.profile_id == profile_id)
    )
    return [
        ScopeMember(owner_id=row.owner_id, scope=row.scope)  # type: ignore[arg-type]
        for row in rows.scalars().all()
    ]


def _build_confidence_inputs(
    dispatched_results: list,
) -> list[AgentConfidenceInput]:
    inputs = []
    for r in dispatched_results:
        if r.fallback_tier == FallbackTier.FAILURE:
            inputs.append(AgentConfidenceInput(r.agent_id, 0.0, FallbackTier.FAILURE))
        else:
            confidence = r.response.confidence if r.response else 0.0
            inputs.append(AgentConfidenceInput(r.agent_id, confidence, r.fallback_tier))
    return inputs


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/recommendation", response_model=RecommendationResponse, status_code=201)
async def create_recommendation_endpoint(
    body: RecommendationRequest,
    request: Request,
    owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
    registry: AgentRegistryCache = Depends(get_registry),
    breaker: InMemoryBreakerStore = Depends(get_breaker),
    response_cache: AgentResponseCache = Depends(get_response_cache),
) -> RecommendationResponse:
    """
    Run the full Planner + Critic pipeline and persist the result.

    1. Scope resolve (UserProfile + membership scoping)
    2. Snapshot (freeze profile at request time)
    3. Decompose query → Plan
    4. Dispatch Plan → agent responses
    5. Compose baseline confidence (tier penalties)
    6. Critic evaluate (consistency checks, downward adjustment)
    7. Audit write (recommendations + GENERATED event)
    """
    if body.owner_id != owner.id:
        raise HTTPException(
            status_code=403,
            detail="owner_id in request body does not match authenticated owner",
        )

    trace_id = uuid.uuid4()

    # Open a top-level Langfuse trace. All domain agents share the same
    # trace_id so their LLM/tool spans appear nested under this trace.
    lf_trace = create_trace(
        trace_id=str(trace_id),
        name="orchestrator.recommendation",
        user_id=str(body.owner_id),
        input={"query": body.query},
        metadata={"owner_id": str(body.owner_id)},
    )

    _e2e_t0 = time.perf_counter()
    with start_span("orchestrator.recommend", {"owner_id": str(body.owner_id), "trace_id": str(trace_id)}):

        # 1. Load user profile
        result = await _load_profile_and_members(session, body.owner_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"No user profile found for owner_id={body.owner_id}. "
                       "Create a profile before requesting recommendations.",
            )
        pydantic_profile, profile_id = result

        _t0 = time.perf_counter()
        with start_span("planner.scope_resolve"):
            members = await _load_scope_members(session, profile_id)
            is_family = query_implies_family(body.query)
            scope = resolve_scope(pydantic_profile, members, query_requests_family=is_family)
        record_pipeline_stage("scope_resolve", time.perf_counter() - _t0)

        # 2. Snapshot
        _t0 = time.perf_counter()
        with start_span("planner.snapshot"):
            snapshot = await create_snapshot(session, profile_id, pydantic_profile)
        record_pipeline_stage("snapshot", time.perf_counter() - _t0)

        # 3. Decompose
        available_agents: list[RegisteredAgent] = registry.list_available()
        _t0 = time.perf_counter()
        with start_span("planner.decompose", {"agent_count": str(len(available_agents))}):
            plan = await decompose_with_llm_fallback(body.query, scope, available_agents)
        record_pipeline_stage("decompose", time.perf_counter() - _t0)

        log.info(
            "orchestrator.plan_built",
            trace_id=str(trace_id),
            agents=plan.agent_ids(),
            query=body.query[:80],
        )

        # 4. Dispatch
        _t0 = time.perf_counter()
        with start_span("orchestrator.dispatch", {"plan_id": str(plan.plan_id)}):
            dispatched_results = await dispatch_plan(
                plan, pydantic_profile, registry, breaker, response_cache, trace_id
            )
        record_pipeline_stage("dispatch", time.perf_counter() - _t0)

        # Record tier metrics
        for dr in dispatched_results:
            record_dispatch_tier(dr.agent_id, dr.fallback_tier.value)
            record_breaker_state(dr.agent_id, breaker.get_state(dr.agent_id).value)

        # 5. Compose baseline confidence
        _t0 = time.perf_counter()
        confidence_inputs = _build_confidence_inputs(dispatched_results)
        baseline = compose(confidence_inputs)
        record_pipeline_stage("compose", time.perf_counter() - _t0)

        # 6. Critic
        _t0 = time.perf_counter()
        with start_span("critic.evaluate"):
            critic_result = critic_evaluate(body.query, dispatched_results, baseline)
        record_pipeline_stage("critic", time.perf_counter() - _t0)
        if lf_trace is not None:
            try:
                cs = lf_trace.span(
                    name="orchestrator/critic",
                    input={
                        "baseline_confidence": baseline.score,
                        "agents": [r.agent_id for r in dispatched_results],
                    },
                    output={
                        "final_confidence": critic_result.final_confidence,
                        "total_penalty": critic_result.total_penalty,
                        "flags": [f.check_type for f in critic_result.consistency_flags],
                        "gaps": critic_result.gaps,
                        "warnings": critic_result.warnings,
                    },
                    metadata={"node": "critic"},
                )
                cs.end()
            except Exception:
                pass

        # 7. Synthesize — merge all agent answers into one narrative
        _t0 = time.perf_counter()
        with start_span("synthesizer.run"):
            synthesized_answer = await synthesize(
                body.query, dispatched_results, critic_result=critic_result, trace_id=str(trace_id)
            )
        record_pipeline_stage("synthesize", time.perf_counter() - _t0)

        # 8. Audit write
        _t0 = time.perf_counter()
        with start_span("audit.write"):
            rec = await create_recommendation(
                session,
                owner_id=body.owner_id,
                snapshot_id=snapshot.id,
                query=body.query,
                plan=plan,
                dispatched_results=dispatched_results,
                critic_result=critic_result,
                synthesized_answer=synthesized_answer,
            )
            await session.commit()
        record_pipeline_stage("audit_write", time.perf_counter() - _t0)

        # Finalise the Langfuse trace with the orchestrator's output summary,
        # then flush so events appear in the dashboard without waiting for the
        # background batch timer.
        if lf_trace is not None:
            lf_trace.update(
                output={
                    "recommendation_id": str(rec.id),
                    "final_confidence": round(critic_result.final_confidence / 100.0, 4),
                    "agents_called": plan.agent_ids(),
                    "gaps": critic_result.gaps,
                    "critic_penalty": round(critic_result.total_penalty / 100.0, 4),
                }
            )
        # Attach the orchestrator-level confidence score so it's queryable in
        # the Langfuse dashboard alongside per-agent confidence scores.
        score_trace(
            str(trace_id),
            name="orchestrator.confidence",
            value=round(critic_result.final_confidence / 100.0, 4),
            comment=f"baseline={round(baseline.score / 100.0, 4)} penalty={critic_result.total_penalty}pp",
        )
        lf_flush()

        # Record metrics
        record_recommendation(
            confidence=critic_result.final_confidence,
            state=RecommendationState.GENERATED.value,
            gap_count=len(critic_result.gaps),
            critic_penalty=critic_result.total_penalty,
        )
        record_pipeline_stage("e2e", time.perf_counter() - _e2e_t0)

        log.info(
            "orchestrator.recommendation_complete",
            rec_id=str(rec.id),
            trace_id=str(trace_id),
            confidence=critic_result.final_confidence,
            gaps=critic_result.gaps,
            penalty=critic_result.total_penalty,
        )

        # Normalise confidence values to 0-1 fraction before returning.
        # Internally composition.py and critic.py operate in percentage-point
        # (0–100) scale; the frontend and API contract expect 0-1 floats.
        raw = rec.final_output_json
        normalised_final_output = {
            **raw,
            "final_confidence": round(raw.get("final_confidence", 0) / 100.0, 4),
            "baseline_confidence": round(raw.get("baseline_confidence", 0) / 100.0, 4),
            "total_penalty": round(raw.get("total_penalty", 0) / 100.0, 4),
        }

        return RecommendationResponse(
            recommendation_id=rec.id,
            final_confidence=round(critic_result.final_confidence / 100.0, 4),
            state=RecommendationState.GENERATED.value,
            warnings=critic_result.warnings,
            gaps=critic_result.gaps,
            final_output=normalised_final_output,
            synthesized_answer=synthesized_answer,
            plan_json=rec.plan_json,
            agent_outputs_json=rec.agent_outputs_json,
        )


@router.post(
    "/recommendation/{recommendation_id}/events",
    response_model=EventResponse,
    status_code=200,
)
async def add_recommendation_event(
    recommendation_id: uuid.UUID,
    body: EventRequest,
    owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> EventResponse:
    """
    Append a lifecycle event to a recommendation (surface, accept, reject, …).

    actor_user_id is required for all transitions — this is the simple
    user identity check enforced per commit 1 architecture decisions.

    Returns 422 if the transition is not allowed by the state machine.
    Returns 404 if the recommendation does not exist.
    """
    if body.actor_user_id != owner.id:
        raise HTTPException(
            status_code=403,
            detail="actor_user_id does not match authenticated owner",
        )

    try:
        event = await transition_state(
            session,
            recommendation_id=recommendation_id,
            to_state=body.event_type,
            actor_user_id=body.actor_user_id,
            payload=body.payload,
        )
        await session.commit()

        # Load updated recommendation for current_state
        rec: Recommendation | None = await session.get(Recommendation, recommendation_id)
        current_state = rec.current_state if rec else body.event_type.value

        record_transition(
            from_state="unknown",  # could load prev event but not worth the query
            to_state=body.event_type.value,
        )

        log.info(
            "orchestrator.event_added",
            rec_id=str(recommendation_id),
            event_type=body.event_type.value,
            actor=str(body.actor_user_id),
        )

        return EventResponse(
            event_id=event.id,
            recommendation_id=recommendation_id,
            event_type=event.event_type,
            current_state=current_state,
        )

    except InvalidTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/recommendations", response_model=list[RecommendationSummary])
async def list_my_recommendations(
    owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
    state: str | None = Query(default=None, description="Filter by state"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[RecommendationSummary]:
    """List recommendations for the authenticated owner, newest first."""
    q = (
        select(Recommendation)
        .where(Recommendation.owner_id == owner.id)
        .order_by(desc(Recommendation.created_at))
        .offset(offset)
        .limit(limit)
    )
    if state is not None:
        q = q.where(Recommendation.current_state == state)

    result = await session.execute(q)
    recs = result.scalars().all()

    return [
        RecommendationSummary(
            id=r.id,
            query=r.query,
            composite_confidence=r.composite_confidence,
            current_state=r.current_state,
            created_at=r.created_at,
        )
        for r in recs
    ]
