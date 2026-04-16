"""
Recommendation lifecycle + audit writer (Phase 5).

All writes are append-only:
  - recommendations    — immutable header, written once at plan completion
  - recommendation_events — state log, one new row per transition

Public API:
  create_snapshot()      — freeze UserProfile at request time
  create_recommendation() — write header + GENERATED event
  transition_state()     — append event, update denormalised current_state
  get_recommendation()   — load header + events for a given ID

Callers (Planner → API layer) are responsible for committing the session.
Functions here only add objects and flush (to materialise IDs / check FKs).
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.confidence.composition import CompositeResult
from libs.confidence.tier import FallbackTier
from libs.schemas.db_models import (
    Recommendation,
    RecommendationEvent,
    UserProfileSnapshot,
)
from libs.schemas.enums import RecommendationState
from libs.schemas.recommendation import VALID_TRANSITIONS, is_valid_transition
from libs.schemas.user_profile import UserProfile
from services.orchestrator.critic import CriticResult
from services.orchestrator.dispatch import DispatchedResult
from services.orchestrator.plan import Plan

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InvalidTransitionError(Exception):
    """Raised when a requested state transition is not allowed."""

    def __init__(self, from_state: RecommendationState, to_state: RecommendationState) -> None:
        super().__init__(
            f"Invalid transition: {from_state} → {to_state}. "
            f"Allowed from {from_state}: {VALID_TRANSITIONS[from_state]}"
        )
        self.from_state = from_state
        self.to_state = to_state


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialise_results(dispatched_results: list[DispatchedResult]) -> list[dict[str, Any]]:
    """
    Convert DispatchedResult list to a JSON-serialisable form for audit storage.
    Stored verbatim in recommendations.agent_outputs_json for the replay harness.
    """
    out = []
    for r in dispatched_results:
        entry: dict[str, Any] = {
            "agent_id": r.agent_id,
            "fallback_tier": r.fallback_tier.value,
            "error": r.error,
            "response": r.response.model_dump(mode="json") if r.response is not None else None,
        }
        out.append(entry)
    return out


def _serialise_critic(critic_result: CriticResult) -> dict[str, Any]:
    return {
        "final_confidence": critic_result.final_confidence,
        "baseline_confidence": critic_result.baseline_confidence,
        "total_penalty": critic_result.total_penalty,
        "consistency_flags": [dataclasses.asdict(f) for f in critic_result.consistency_flags],
        "schema_warnings": critic_result.schema_warnings,
        "gaps": critic_result.gaps,
        "warnings": critic_result.warnings,
    }


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


async def create_snapshot(
    session: AsyncSession,
    profile_id: uuid.UUID,
    profile: UserProfile,
) -> UserProfileSnapshot:
    """
    Freeze the current UserProfile as an immutable snapshot.

    Called by the Planner at the start of each recommendation request,
    before any agent calls.  The snapshot_id is attached to every
    RecommendationEvent so the audit log is fully reproducible.
    """
    snapshot = UserProfileSnapshot(
        profile_id=profile_id,
        snapshot_json=profile.model_dump(mode="json"),
    )
    session.add(snapshot)
    await session.flush()
    log.info("audit.snapshot_created", snapshot_id=str(snapshot.id))
    return snapshot


# ---------------------------------------------------------------------------
# Recommendation header
# ---------------------------------------------------------------------------


async def create_recommendation(
    session: AsyncSession,
    owner_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    query: str,
    plan: Plan,
    dispatched_results: list[DispatchedResult],
    critic_result: CriticResult,
) -> Recommendation:
    """
    Write the immutable recommendation header and the initial GENERATED event.

    final_output_json stores the Critic's full evaluation for display.
    agent_outputs_json stores full agent I/O verbatim for replay.
    composite_confidence is the Critic's final adjusted score.

    Returns the Recommendation ORM object (id is populated after flush).
    """
    rec = Recommendation(
        owner_id=owner_id,
        snapshot_id=snapshot_id,
        query=query,
        plan_json=plan.to_dict(),
        agent_outputs_json=_serialise_results(dispatched_results),
        final_output_json=_serialise_critic(critic_result),
        composite_confidence=critic_result.final_confidence,
        current_state=RecommendationState.GENERATED.value,
    )
    session.add(rec)
    await session.flush()  # materialise rec.id

    # Initial event — no actor (system-generated)
    event = RecommendationEvent(
        recommendation_id=rec.id,
        event_type=RecommendationState.GENERATED.value,
        actor_user_id=None,
        payload={"plan_id": str(plan.plan_id)},
    )
    session.add(event)
    await session.flush()

    log.info(
        "audit.recommendation_created",
        rec_id=str(rec.id),
        confidence=critic_result.final_confidence,
        gaps=critic_result.gaps,
    )
    return rec


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def transition_state(
    session: AsyncSession,
    recommendation_id: uuid.UUID,
    to_state: RecommendationState,
    actor_user_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
) -> RecommendationEvent:
    """
    Append a state-transition event and update the denormalised current_state.

    Raises InvalidTransitionError if the transition is not allowed by the
    state machine.  The session is NOT committed here; caller commits.
    """
    rec = await session.get(Recommendation, recommendation_id)
    if rec is None:
        raise ValueError(f"Recommendation {recommendation_id} not found")

    current = RecommendationState(rec.current_state)
    if not is_valid_transition(current, to_state):
        raise InvalidTransitionError(current, to_state)

    event = RecommendationEvent(
        recommendation_id=recommendation_id,
        event_type=to_state.value,
        actor_user_id=actor_user_id,
        payload=payload or {},
    )
    session.add(event)

    # Update denormalised cache — events table is authoritative
    rec.current_state = to_state.value
    await session.flush()

    log.info(
        "audit.state_transition",
        rec_id=str(recommendation_id),
        from_state=current.value,
        to_state=to_state.value,
        actor=str(actor_user_id),
    )
    return event


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


async def get_recommendation(
    session: AsyncSession,
    recommendation_id: uuid.UUID,
) -> Recommendation | None:
    """Load recommendation header. Events are available via rec.events (lazy)."""
    return await session.get(Recommendation, recommendation_id)


async def get_recommendation_events(
    session: AsyncSession,
    recommendation_id: uuid.UUID,
) -> list[RecommendationEvent]:
    """Return all events for a recommendation in chronological order."""
    result = await session.execute(
        select(RecommendationEvent)
        .where(RecommendationEvent.recommendation_id == recommendation_id)
        .order_by(RecommendationEvent.created_at)
    )
    return list(result.scalars().all())
