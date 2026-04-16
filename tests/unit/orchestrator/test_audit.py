"""Unit tests for the recommendation audit writer."""

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from libs.confidence.composition import CompositeResult
from libs.confidence.tier import FallbackTier
from libs.schemas.agent_envelope import AgentResponse, DataTier, RiskLevel
from libs.schemas.db_models import Recommendation, RecommendationEvent, UserProfileSnapshot
from libs.schemas.enums import RecommendationState
from libs.schemas.user_profile import UserProfile
from services.orchestrator.audit import (
    InvalidTransitionError,
    _serialise_critic,
    _serialise_results,
    create_recommendation,
    create_snapshot,
    transition_state,
)
from services.orchestrator.critic import CriticResult, ConsistencyFlag
from services.orchestrator.dispatch import DispatchedResult
from services.orchestrator.plan import AgentCall, Plan


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _profile() -> UserProfile:
    return UserProfile(owner_id=uuid.uuid4(), name="Rahul", age=35)


def _plan(query: str = "Should I increase SIP?") -> Plan:
    return Plan(
        original_query=query,
        steps=[AgentCall("cashflow_agent", [uuid.uuid4()])],
    )


def _agent_response(agent_id: str = "cashflow_agent") -> AgentResponse:
    return AgentResponse(
        agent_id=agent_id,
        trace_id=uuid.uuid4(),
        data_tier=DataTier.REALTIME,
        data_freshness_hours=0.0,
        result={"surplus_paise": 1_800_000},
        confidence=0.85,
        risk_level=RiskLevel.LOW,
        reasoning="positive surplus",
    )


def _dispatched(agent_id: str = "cashflow_agent", tier: FallbackTier = FallbackTier.PRIMARY) -> DispatchedResult:
    return DispatchedResult(
        agent_id=agent_id,
        response=_agent_response(agent_id),
        fallback_tier=tier,
    )


def _failure_result(agent_id: str) -> DispatchedResult:
    return DispatchedResult(
        agent_id=agent_id,
        response=None,
        fallback_tier=FallbackTier.FAILURE,
        error="timeout",
    )


def _critic(score: float = 72.5, gaps: list[str] | None = None) -> CriticResult:
    return CriticResult(
        final_confidence=score,
        baseline_confidence=score + 5.0,
        total_penalty=5.0,
        consistency_flags=[],
        schema_warnings=[],
        gaps=gaps or [],
        warnings=[],
    )


def _mock_session() -> AsyncMock:
    session = AsyncMock(spec=["add", "flush", "get", "execute"])
    session.add = MagicMock()
    session.flush = AsyncMock()

    # session.get returns a Recommendation with given current_state
    async def fake_get(model, pk):
        if model is Recommendation:
            rec = Recommendation()
            rec.id = pk
            rec.current_state = RecommendationState.GENERATED.value
            return rec
        return None

    session.get = fake_get
    return session


# ---------------------------------------------------------------------------
# _serialise_results
# ---------------------------------------------------------------------------


def test_serialise_results_includes_response():
    results = [_dispatched("cashflow_agent", FallbackTier.PRIMARY)]
    out = _serialise_results(results)
    assert len(out) == 1
    assert out[0]["agent_id"] == "cashflow_agent"
    assert out[0]["fallback_tier"] == "PRIMARY"
    assert out[0]["response"] is not None
    assert out[0]["error"] is None


def test_serialise_results_failure_has_null_response():
    results = [_failure_result("risk_agent")]
    out = _serialise_results(results)
    assert out[0]["response"] is None
    assert out[0]["error"] == "timeout"


def test_serialise_results_all_json_serialisable():
    import json
    results = [
        _dispatched("cashflow_agent", FallbackTier.PRIMARY),
        _dispatched("investment_agent", FallbackTier.SECONDARY),
        _failure_result("risk_agent"),
    ]
    # Must not raise
    json.dumps(_serialise_results(results))


# ---------------------------------------------------------------------------
# _serialise_critic
# ---------------------------------------------------------------------------


def test_serialise_critic_keys_present():
    c = _critic()
    d = _serialise_critic(c)
    assert "final_confidence" in d
    assert "baseline_confidence" in d
    assert "total_penalty" in d
    assert "consistency_flags" in d
    assert "gaps" in d
    assert "warnings" in d


def test_serialise_critic_with_flags():
    import json
    c = CriticResult(
        final_confidence=65.0,
        baseline_confidence=75.0,
        total_penalty=10.0,
        consistency_flags=[
            ConsistencyFlag("surplus_mismatch", ["a", "b"], "desc", 5.0)
        ],
        schema_warnings=[],
        gaps=["risk_agent"],
        warnings=["missing data"],
    )
    d = _serialise_critic(c)
    json.dumps(d)  # must be serialisable
    assert len(d["consistency_flags"]) == 1


# ---------------------------------------------------------------------------
# create_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_snapshot_adds_to_session():
    session = _mock_session()
    profile = _profile()
    snap = await create_snapshot(session, uuid.uuid4(), profile)

    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert isinstance(added, UserProfileSnapshot)
    assert added.snapshot_json["name"] == "Rahul"


@pytest.mark.asyncio
async def test_create_snapshot_flushes():
    session = _mock_session()
    await create_snapshot(session, uuid.uuid4(), _profile())
    session.flush.assert_called()


@pytest.mark.asyncio
async def test_create_snapshot_json_roundtrips_profile():
    session = _mock_session()
    profile = _profile()
    snap = await create_snapshot(session, uuid.uuid4(), profile)
    restored = UserProfile.model_validate(snap.snapshot_json)
    assert restored.name == profile.name
    assert restored.owner_id == profile.owner_id


# ---------------------------------------------------------------------------
# create_recommendation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_recommendation_adds_header_and_event():
    session = _mock_session()
    calls_made = []
    session.add = MagicMock(side_effect=lambda obj: calls_made.append(type(obj).__name__))

    await create_recommendation(
        session,
        owner_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        query="Should I increase SIP?",
        plan=_plan(),
        dispatched_results=[_dispatched()],
        critic_result=_critic(),
    )

    assert "Recommendation" in calls_made
    assert "RecommendationEvent" in calls_made


@pytest.mark.asyncio
async def test_create_recommendation_initial_state_is_generated():
    session = _mock_session()
    added_objects = []
    session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    await create_recommendation(
        session,
        owner_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        query="test",
        plan=_plan(),
        dispatched_results=[_dispatched()],
        critic_result=_critic(),
    )

    rec = next(o for o in added_objects if isinstance(o, Recommendation))
    assert rec.current_state == RecommendationState.GENERATED.value


@pytest.mark.asyncio
async def test_create_recommendation_generated_event_no_actor():
    session = _mock_session()
    added_objects = []
    session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    await create_recommendation(
        session,
        owner_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        query="test",
        plan=_plan(),
        dispatched_results=[_dispatched()],
        critic_result=_critic(),
    )

    event = next(o for o in added_objects if isinstance(o, RecommendationEvent))
    assert event.event_type == RecommendationState.GENERATED.value
    assert event.actor_user_id is None


@pytest.mark.asyncio
async def test_create_recommendation_stores_confidence():
    session = _mock_session()
    added_objects = []
    session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    await create_recommendation(
        session,
        owner_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        query="test",
        plan=_plan(),
        dispatched_results=[_dispatched()],
        critic_result=_critic(score=67.5),
    )

    rec = next(o for o in added_objects if isinstance(o, Recommendation))
    assert rec.composite_confidence == 67.5


@pytest.mark.asyncio
async def test_create_recommendation_agent_outputs_include_all_tiers():
    session = _mock_session()
    added_objects = []
    session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    results = [
        _dispatched("cashflow_agent", FallbackTier.PRIMARY),
        _dispatched("investment_agent", FallbackTier.SECONDARY),
        _failure_result("risk_agent"),
    ]
    await create_recommendation(
        session,
        owner_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        query="test",
        plan=_plan(),
        dispatched_results=results,
        critic_result=_critic(),
    )

    rec = next(o for o in added_objects if isinstance(o, Recommendation))
    tiers = {e["agent_id"]: e["fallback_tier"] for e in rec.agent_outputs_json}
    assert tiers["cashflow_agent"] == "PRIMARY"
    assert tiers["investment_agent"] == "SECONDARY"
    assert tiers["risk_agent"] == "FAILURE"


# ---------------------------------------------------------------------------
# transition_state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_transition_appends_event():
    session = _mock_session()
    added_objects = []
    session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    actor = uuid.uuid4()
    rec_id = uuid.uuid4()
    await transition_state(session, rec_id, RecommendationState.SURFACED, actor)

    events = [o for o in added_objects if isinstance(o, RecommendationEvent)]
    assert len(events) == 1
    assert events[0].event_type == RecommendationState.SURFACED.value
    assert events[0].actor_user_id == actor


@pytest.mark.asyncio
async def test_invalid_transition_raises():
    session = _mock_session()
    # GENERATED → ACCEPTED is invalid (must go through SURFACED first)
    with pytest.raises(InvalidTransitionError) as exc_info:
        await transition_state(
            session, uuid.uuid4(), RecommendationState.ACCEPTED, uuid.uuid4()
        )
    assert exc_info.value.from_state == RecommendationState.GENERATED
    assert exc_info.value.to_state == RecommendationState.ACCEPTED


@pytest.mark.asyncio
async def test_transition_updates_current_state():
    """The recommendation's current_state field is updated (denormalised cache)."""
    session = _mock_session()

    rec_id = uuid.uuid4()
    captured_rec: list[Recommendation] = []

    async def fake_get(model, pk):
        rec = Recommendation()
        rec.id = pk
        rec.current_state = RecommendationState.GENERATED.value
        captured_rec.append(rec)
        return rec

    session.get = fake_get

    await transition_state(
        session, rec_id, RecommendationState.SURFACED, uuid.uuid4()
    )

    assert captured_rec[0].current_state == RecommendationState.SURFACED.value


@pytest.mark.asyncio
async def test_transition_with_payload():
    session = _mock_session()
    added_objects = []
    session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    payload = {"reason": "Reviewed and approved", "modified_amount": 15000_00}
    await transition_state(
        session, uuid.uuid4(), RecommendationState.SURFACED, uuid.uuid4(), payload
    )

    event = next(o for o in added_objects if isinstance(o, RecommendationEvent))
    assert event.payload == payload


@pytest.mark.asyncio
async def test_transition_recommendation_not_found_raises():
    session = _mock_session()
    session.get = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await transition_state(
            session, uuid.uuid4(), RecommendationState.SURFACED, uuid.uuid4()
        )


@pytest.mark.asyncio
async def test_full_lifecycle_state_machine():
    """Walk through the full happy path: generated → surfaced → accepted → outcome_pending → confirmed."""
    states_seen: list[str] = []
    actor = uuid.uuid4()
    current_state = RecommendationState.GENERATED.value

    async def fake_get(model, pk):
        rec = Recommendation()
        rec.id = pk
        rec.current_state = current_state
        return rec

    session = _mock_session()
    session.get = fake_get
    session.add = MagicMock()

    rec_id = uuid.uuid4()

    for to_state in [
        RecommendationState.SURFACED,
        RecommendationState.ACCEPTED,
        RecommendationState.OUTCOME_PENDING,
        RecommendationState.OUTCOME_CONFIRMED,
    ]:
        await transition_state(session, rec_id, to_state, actor)
        current_state = to_state.value  # advance mock state
        states_seen.append(to_state.value)

    assert states_seen == [
        "SURFACED", "ACCEPTED", "OUTCOME_PENDING", "OUTCOME_CONFIRMED"
    ]


@pytest.mark.asyncio
async def test_rejected_is_terminal():
    current_state = RecommendationState.SURFACED.value

    async def fake_get(model, pk):
        rec = Recommendation()
        rec.id = pk
        rec.current_state = current_state
        return rec

    session = _mock_session()
    session.get = fake_get

    # Move to REJECTED
    await transition_state(session, uuid.uuid4(), RecommendationState.REJECTED, uuid.uuid4())

    # Now try any further transition — should fail
    current_state = RecommendationState.REJECTED.value
    with pytest.raises(InvalidTransitionError):
        await transition_state(session, uuid.uuid4(), RecommendationState.SURFACED, uuid.uuid4())
