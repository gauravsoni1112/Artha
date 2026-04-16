"""Unit tests for Phase 5 recommendation schemas and state machine."""

import uuid

import pytest
from pydantic import ValidationError

from libs.schemas.enums import AccessScope, RecommendationState
from libs.schemas.recommendation import (
    VALID_TRANSITIONS,
    RecommendationCreate,
    RecommendationEventCreate,
    UserProfileSnapshotCreate,
    is_valid_transition,
)


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


def test_access_scope_values():
    assert set(AccessScope) == {
        AccessScope.PRIMARY,
        AccessScope.SPOUSE,
        AccessScope.DEPENDENT,
    }


def test_recommendation_state_full_lifecycle():
    expected = {
        "GENERATED", "SURFACED", "ACCEPTED", "REJECTED",
        "MODIFIED", "OUTCOME_PENDING", "OUTCOME_CONFIRMED",
    }
    assert {s.value for s in RecommendationState} == expected


# ---------------------------------------------------------------------------
# State machine transitions
# ---------------------------------------------------------------------------


def test_generated_to_surfaced_allowed():
    assert is_valid_transition(RecommendationState.GENERATED, RecommendationState.SURFACED)


def test_surfaced_to_accepted_allowed():
    assert is_valid_transition(RecommendationState.SURFACED, RecommendationState.ACCEPTED)


def test_surfaced_to_rejected_allowed():
    assert is_valid_transition(RecommendationState.SURFACED, RecommendationState.REJECTED)


def test_surfaced_to_modified_allowed():
    assert is_valid_transition(RecommendationState.SURFACED, RecommendationState.MODIFIED)


def test_accepted_to_outcome_pending_allowed():
    assert is_valid_transition(RecommendationState.ACCEPTED, RecommendationState.OUTCOME_PENDING)


def test_modified_to_outcome_pending_allowed():
    assert is_valid_transition(RecommendationState.MODIFIED, RecommendationState.OUTCOME_PENDING)


def test_outcome_pending_to_confirmed_allowed():
    assert is_valid_transition(
        RecommendationState.OUTCOME_PENDING, RecommendationState.OUTCOME_CONFIRMED
    )


def test_rejected_is_terminal():
    for state in RecommendationState:
        assert not is_valid_transition(RecommendationState.REJECTED, state)


def test_outcome_confirmed_is_terminal():
    for state in RecommendationState:
        assert not is_valid_transition(RecommendationState.OUTCOME_CONFIRMED, state)


def test_no_skipping_states():
    # Cannot jump from GENERATED directly to ACCEPTED
    assert not is_valid_transition(RecommendationState.GENERATED, RecommendationState.ACCEPTED)
    # Cannot jump from SURFACED to OUTCOME_PENDING
    assert not is_valid_transition(RecommendationState.SURFACED, RecommendationState.OUTCOME_PENDING)


def test_valid_transitions_covers_all_states():
    assert set(VALID_TRANSITIONS.keys()) == set(RecommendationState)


# ---------------------------------------------------------------------------
# RecommendationCreate
# ---------------------------------------------------------------------------


def _rec_create(**kwargs):
    defaults = dict(
        owner_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        query="Should I increase SIP by ₹10k?",
        plan_json={"agents": ["cashflow", "investment", "goal"], "mode": "parallel"},
        agent_outputs_json=[{"agent_id": "cashflow", "result": {"surplus_paise": 1_800_000}}],
        final_output_json={"recommendation": "Yes, increase SIP", "reasoning": "..."},
        composite_confidence=72.5,
    )
    defaults.update(kwargs)
    return RecommendationCreate(**defaults)


def test_recommendation_create_valid():
    r = _rec_create()
    assert r.composite_confidence == 72.5
    assert r.query == "Should I increase SIP by ₹10k?"


def test_recommendation_confidence_bounds():
    _rec_create(composite_confidence=0.0)
    _rec_create(composite_confidence=100.0)
    with pytest.raises(ValidationError):
        _rec_create(composite_confidence=-0.1)
    with pytest.raises(ValidationError):
        _rec_create(composite_confidence=100.1)


def test_recommendation_empty_query_rejected():
    with pytest.raises(ValidationError):
        _rec_create(query="")


# ---------------------------------------------------------------------------
# RecommendationEventCreate
# ---------------------------------------------------------------------------


def test_generated_event_no_actor_required():
    ev = RecommendationEventCreate(
        recommendation_id=uuid.uuid4(),
        event_type=RecommendationState.GENERATED,
        actor_user_id=None,
    )
    assert ev.actor_user_id is None


def test_non_generated_event_requires_actor():
    for state in RecommendationState:
        if state == RecommendationState.GENERATED:
            continue
        with pytest.raises(ValidationError, match="actor_user_id"):
            RecommendationEventCreate(
                recommendation_id=uuid.uuid4(),
                event_type=state,
                actor_user_id=None,
            )


def test_event_with_actor():
    ev = RecommendationEventCreate(
        recommendation_id=uuid.uuid4(),
        event_type=RecommendationState.ACCEPTED,
        actor_user_id=uuid.uuid4(),
        payload={"note": "Looks good"},
    )
    assert ev.payload == {"note": "Looks good"}


def test_event_default_payload_is_empty_dict():
    ev = RecommendationEventCreate(
        recommendation_id=uuid.uuid4(),
        event_type=RecommendationState.GENERATED,
    )
    assert ev.payload == {}


# ---------------------------------------------------------------------------
# UserProfileSnapshotCreate
# ---------------------------------------------------------------------------


def test_snapshot_create_stores_arbitrary_profile():
    snap = UserProfileSnapshotCreate(
        profile_id=uuid.uuid4(),
        snapshot_json={
            "owner_id": str(uuid.uuid4()),
            "name": "Rahul",
            "risk_appetite": "moderate",
            "total_monthly_income_paise": 500_000_00,
            "income_sources": [],
            "emis": [],
            "goals": [],
        },
    )
    assert snap.snapshot_json["name"] == "Rahul"
