"""
Pydantic models for the recommendation lifecycle (Phase 5).

INVARIANTS:
- recommendations rows are immutable after insert; current_state is a denormalized cache.
- All state transitions happen via new recommendation_events rows — never updates.
- actor_user_id is required for every post-GENERATED event (surfaced/accepted/etc.).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from libs.schemas.enums import RecommendationState


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[RecommendationState, set[RecommendationState]] = {
    RecommendationState.GENERATED: {RecommendationState.SURFACED},
    RecommendationState.SURFACED: {
        RecommendationState.ACCEPTED,
        RecommendationState.REJECTED,
        RecommendationState.MODIFIED,
    },
    RecommendationState.ACCEPTED: {RecommendationState.OUTCOME_PENDING},
    RecommendationState.REJECTED: set(),
    RecommendationState.MODIFIED: {RecommendationState.OUTCOME_PENDING},
    RecommendationState.OUTCOME_PENDING: {RecommendationState.OUTCOME_CONFIRMED},
    RecommendationState.OUTCOME_CONFIRMED: set(),
}


def is_valid_transition(from_state: RecommendationState, to_state: RecommendationState) -> bool:
    return to_state in VALID_TRANSITIONS.get(from_state, set())


# ---------------------------------------------------------------------------
# Recommendation header (immutable after write)
# ---------------------------------------------------------------------------


class RecommendationCreate(BaseModel):
    owner_id: uuid.UUID
    snapshot_id: uuid.UUID
    query: str = Field(..., min_length=1, max_length=2000)
    plan_json: dict[str, Any]
    agent_outputs_json: list[dict[str, Any]]
    final_output_json: dict[str, Any]
    composite_confidence: float = Field(..., ge=0.0, le=100.0)


class RecommendationRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    snapshot_id: uuid.UUID
    query: str
    plan_json: dict[str, Any]
    agent_outputs_json: list[dict[str, Any]]
    final_output_json: dict[str, Any]
    composite_confidence: float
    current_state: RecommendationState
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Recommendation event (append-only state log)
# ---------------------------------------------------------------------------


class RecommendationEventCreate(BaseModel):
    recommendation_id: uuid.UUID
    event_type: RecommendationState
    actor_user_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def actor_required_after_generated(self) -> "RecommendationEventCreate":
        if self.event_type != RecommendationState.GENERATED and self.actor_user_id is None:
            raise ValueError(
                f"actor_user_id is required for event_type={self.event_type}"
            )
        return self


class RecommendationEventRead(BaseModel):
    id: uuid.UUID
    recommendation_id: uuid.UUID
    event_type: RecommendationState
    actor_user_id: uuid.UUID | None
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# UserProfile snapshot Pydantic model (the frozen point-in-time copy)
# ---------------------------------------------------------------------------


class UserProfileSnapshotCreate(BaseModel):
    profile_id: uuid.UUID
    snapshot_json: dict[str, Any]  # full serialized UserProfile (from user_profile.py)


class UserProfileSnapshotRead(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    snapshot_json: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
