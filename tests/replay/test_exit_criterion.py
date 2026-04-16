"""
Phase 5 exit criterion — end-to-end pipeline test.

Spec requirement:
  "Should I increase SIP by ₹10k?" runs the full example flow from the spec
  and produces an auditable recommendation.

Coverage:
  - Decompose:   query routes to cashflow + investment + goal agents
  - Dispatch:    all three return PRIMARY-tier fixture responses
  - Compose:     baseline confidence = average of (0.88 + 0.82 + 0.79) × 100 = 83%
  - Critic:      no inconsistencies, no gaps → zero penalty → final == baseline
  - Audit write: recommendation header + GENERATED event created in DB
  - Replay:      FIXTURE mode produces identical result to direct pipeline call

These tests run without Docker, live agents, or a database connection.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from libs.confidence.composition import compose
from libs.confidence.tier import FallbackTier
from libs.schemas.agent_envelope import AgentResponse
from libs.schemas.db_models import Recommendation, RecommendationEvent, UserProfileSnapshot
from libs.schemas.enums import RecommendationState
from libs.schemas.user_profile import UserProfile
from services.orchestrator.audit import create_recommendation, create_snapshot
from services.orchestrator.critic import evaluate as critic_evaluate
from services.orchestrator.decompose import RegisteredAgent, decompose
from services.orchestrator.scope import ScopeContext
from tests.replay.harness import (
    ReplayMode,
    load_scenario,
    replay,
    scenario_from_audit_row,
    _build_confidence_inputs,
)

# ---------------------------------------------------------------------------
# Shared constants / helpers
# ---------------------------------------------------------------------------

_QUERY = "Should I increase SIP by ₹10k?"

_ALL_AGENTS = [
    RegisteredAgent("cashflow_agent",   ["cashflow", "spending_trend", "budget_comparison"]),
    RegisteredAgent("investment_agent", ["portfolio_value", "net_worth", "asset_allocation", "xirr"]),
    RegisteredAgent("tax_agent",        ["tax_summary", "capital_gains", "80c_tracker"]),
    RegisteredAgent("goal_agent",       ["goal_progress", "goal_feasibility"]),
    RegisteredAgent("risk_agent",       ["emergency_fund_months", "asset_concentration", "debt_to_income"]),
]

_SCOPE = ScopeContext(allowed_owner_ids=[uuid.uuid4()], is_family_scope=False)
_PROFILE = UserProfile(owner_id=uuid.uuid4(), name="Rahul", age=35)


def _mock_session(snapshot_id: uuid.UUID | None = None, rec_id: uuid.UUID | None = None):
    snap_id = snapshot_id or uuid.uuid4()
    recommendation_id = rec_id or uuid.uuid4()

    added: list = []

    async def fake_flush():
        for obj in added:
            if isinstance(obj, UserProfileSnapshot) and not obj.id:
                obj.id = snap_id
                obj.profile_id = uuid.uuid4()
            elif isinstance(obj, Recommendation) and not obj.id:
                obj.id = recommendation_id
            elif isinstance(obj, RecommendationEvent) and not obj.id:
                obj.id = uuid.uuid4()

    session = AsyncMock()
    session.add = MagicMock(side_effect=added.append)
    session.flush = fake_flush
    session.commit = AsyncMock()
    return session, added


# ---------------------------------------------------------------------------
# 1. Decompose — correct agents selected
# ---------------------------------------------------------------------------


def test_sip_query_decomposes_to_three_agents():
    plan = decompose(_QUERY, _SCOPE, _ALL_AGENTS)
    agent_ids = set(plan.agent_ids())
    assert "cashflow_agent" in agent_ids, "cashflow needed for surplus check"
    assert "investment_agent" in agent_ids, "investment needed for SIP data"
    assert "goal_agent" in agent_ids, "goal needed for impact assessment"


def test_sip_query_plan_is_fully_parallel():
    plan = decompose(_QUERY, _SCOPE, _ALL_AGENTS)
    assert len(plan.parallel_steps()) == len(plan.steps)
    assert plan.sequential_steps() == []


def test_sip_query_plan_preserves_query():
    plan = decompose(_QUERY, _SCOPE, _ALL_AGENTS)
    assert plan.original_query == _QUERY


# ---------------------------------------------------------------------------
# 2. Fixture loading
# ---------------------------------------------------------------------------


def test_load_scenario_returns_three_agents():
    scenario = load_scenario("sip_increase")
    assert scenario.scenario_id == "sip_increase_10k"
    assert scenario.query == _QUERY
    agent_ids = {r.agent_id for r in scenario.fixture_results}
    assert agent_ids == {"cashflow_agent", "investment_agent", "goal_agent"}


def test_fixture_results_are_primary_tier():
    scenario = load_scenario("sip_increase")
    for r in scenario.fixture_results:
        assert r.fallback_tier == FallbackTier.PRIMARY


def test_fixture_responses_are_valid_envelopes():
    scenario = load_scenario("sip_increase")
    for r in scenario.fixture_results:
        assert r.response is not None
        assert isinstance(r.response, AgentResponse)
        assert 0.0 <= r.response.confidence <= 1.0
        assert r.response.schema_version == "1.0"


# ---------------------------------------------------------------------------
# 3. Confidence composition — numeric assertions
# ---------------------------------------------------------------------------


def test_baseline_confidence_is_correct():
    scenario = load_scenario("sip_increase")
    inputs = _build_confidence_inputs(scenario.fixture_results)
    baseline = compose(inputs)

    # (88 + 82 + 79) / 3 = 83%
    expected = (88.0 + 82.0 + 79.0) / 3
    assert baseline.score == pytest.approx(expected, rel=1e-3)
    assert baseline.gaps == []
    assert baseline.warnings == []


def test_no_tier_penalties_on_primary_fixture():
    scenario = load_scenario("sip_increase")
    inputs = _build_confidence_inputs(scenario.fixture_results)
    baseline = compose(inputs)
    # All PRIMARY → no warnings
    assert len(baseline.warnings) == 0


# ---------------------------------------------------------------------------
# 4. Critic evaluation — zero penalty on clean fixture
# ---------------------------------------------------------------------------


def test_critic_no_penalty_on_clean_fixture():
    scenario = load_scenario("sip_increase")
    inputs = _build_confidence_inputs(scenario.fixture_results)
    baseline = compose(inputs)
    critic_result = critic_evaluate(_QUERY, scenario.fixture_results, baseline)

    assert critic_result.total_penalty == 0.0
    assert critic_result.final_confidence == pytest.approx(baseline.score, rel=1e-3)
    assert critic_result.consistency_flags == []
    assert critic_result.schema_warnings == []
    assert critic_result.gaps == []


def test_critic_confidence_bounded():
    scenario = load_scenario("sip_increase")
    inputs = _build_confidence_inputs(scenario.fixture_results)
    baseline = compose(inputs)
    critic_result = critic_evaluate(_QUERY, scenario.fixture_results, baseline)

    assert 0.0 <= critic_result.final_confidence <= 100.0


def test_critic_baseline_preserved_in_result():
    scenario = load_scenario("sip_increase")
    inputs = _build_confidence_inputs(scenario.fixture_results)
    baseline = compose(inputs)
    critic_result = critic_evaluate(_QUERY, scenario.fixture_results, baseline)

    assert critic_result.baseline_confidence == baseline.score


# ---------------------------------------------------------------------------
# 5. Audit write — recommendation + GENERATED event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_write_creates_recommendation_and_event():
    scenario = load_scenario("sip_increase")
    inputs = _build_confidence_inputs(scenario.fixture_results)
    baseline = compose(inputs)
    critic_result = critic_evaluate(_QUERY, scenario.fixture_results, baseline)

    plan = decompose(_QUERY, _SCOPE, _ALL_AGENTS)
    session, added = _mock_session()

    profile_id = uuid.uuid4()
    snap = await create_snapshot(session, profile_id, _PROFILE)

    rec = await create_recommendation(
        session,
        owner_id=_PROFILE.owner_id,
        snapshot_id=snap.id,
        query=_QUERY,
        plan=plan,
        dispatched_results=scenario.fixture_results,
        critic_result=critic_result,
    )

    # Header written
    assert isinstance(rec, Recommendation)
    assert rec.query == _QUERY
    assert rec.current_state == RecommendationState.GENERATED.value
    assert rec.composite_confidence == pytest.approx(critic_result.final_confidence, rel=1e-3)

    # GENERATED event written
    events = [o for o in added if isinstance(o, RecommendationEvent)]
    assert len(events) == 1
    assert events[0].event_type == RecommendationState.GENERATED.value
    assert events[0].actor_user_id is None  # system-generated


@pytest.mark.asyncio
async def test_audit_stores_all_three_agent_outputs():
    scenario = load_scenario("sip_increase")
    inputs = _build_confidence_inputs(scenario.fixture_results)
    baseline = compose(inputs)
    critic_result = critic_evaluate(_QUERY, scenario.fixture_results, baseline)
    plan = decompose(_QUERY, _SCOPE, _ALL_AGENTS)

    session, added = _mock_session()
    snap = await create_snapshot(session, uuid.uuid4(), _PROFILE)
    rec = await create_recommendation(
        session, _PROFILE.owner_id, snap.id, _QUERY,
        plan, scenario.fixture_results, critic_result,
    )

    stored_agents = {e["agent_id"] for e in rec.agent_outputs_json}
    assert stored_agents == {"cashflow_agent", "investment_agent", "goal_agent"}


@pytest.mark.asyncio
async def test_audit_plan_json_is_reproducible():
    plan = decompose(_QUERY, _SCOPE, _ALL_AGENTS)
    restored = type(plan).from_dict(plan.to_dict())
    assert restored.original_query == plan.original_query
    assert set(restored.agent_ids()) == set(plan.agent_ids())


# ---------------------------------------------------------------------------
# 6. Replay harness — FIXTURE mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_fixture_mode_full_pipeline():
    scenario = load_scenario("sip_increase")
    result = await replay(
        scenario,
        ReplayMode.FIXTURE,
        scope=_SCOPE,
        user_profile=_PROFILE,
        available_agents=_ALL_AGENTS,
    )

    # Plan correct
    assert "cashflow_agent" in result.plan.agent_ids()
    assert "investment_agent" in result.plan.agent_ids()
    assert "goal_agent" in result.plan.agent_ids()

    # All PRIMARY tier
    tiers = {r.fallback_tier for r in result.dispatched_results}
    assert tiers == {FallbackTier.PRIMARY}

    # Confidence
    assert 0.0 < result.critic_result.final_confidence <= 100.0
    assert result.critic_result.total_penalty == 0.0

    # No diffs in FIXTURE mode
    assert result.diffs == []


@pytest.mark.asyncio
async def test_replay_fixture_is_deterministic():
    """Running fixture replay twice produces identical scores."""
    scenario = load_scenario("sip_increase")

    result_a = await replay(scenario, ReplayMode.FIXTURE, _SCOPE, _PROFILE, _ALL_AGENTS)
    result_b = await replay(scenario, ReplayMode.FIXTURE, _SCOPE, _PROFILE, _ALL_AGENTS)

    assert result_a.critic_result.final_confidence == result_b.critic_result.final_confidence
    assert result_a.critic_result.total_penalty == result_b.critic_result.total_penalty
    assert result_a.plan.agent_ids() == result_b.plan.agent_ids()


# ---------------------------------------------------------------------------
# 7. scenario_from_audit_row — round-trip through audit log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_from_audit_row_round_trip():
    """Seeding from audit log and replaying produces the same confidence."""
    scenario = load_scenario("sip_increase")

    # Simulate what audit.py stores in agent_outputs_json
    from services.orchestrator.audit import _serialise_results
    stored_json = _serialise_results(scenario.fixture_results)

    # Reconstruct scenario from stored data
    restored = scenario_from_audit_row(
        query=scenario.query,
        agent_outputs_json=stored_json,
        scenario_id="round_trip",
    )

    result_orig = await replay(scenario, ReplayMode.FIXTURE, _SCOPE, _PROFILE, _ALL_AGENTS)
    result_restored = await replay(restored, ReplayMode.FIXTURE, _SCOPE, _PROFILE, _ALL_AGENTS)

    assert result_orig.critic_result.final_confidence == pytest.approx(
        result_restored.critic_result.final_confidence, rel=1e-3
    )


# ---------------------------------------------------------------------------
# 8. Contract tests — schema version compatibility
# ---------------------------------------------------------------------------


def test_known_schema_version_parses():
    """AgentResponse with schema_version=1.0 is parseable and triggers no critic warning."""
    scenario = load_scenario("sip_increase")
    for r in scenario.fixture_results:
        assert r.response.schema_version == "1.0"

    inputs = _build_confidence_inputs(scenario.fixture_results)
    baseline = compose(inputs)
    critic_result = critic_evaluate(_QUERY, scenario.fixture_results, baseline)
    assert critic_result.schema_warnings == []


def test_unknown_schema_version_still_parses():
    """
    AgentResponse with an unknown schema_version should still parse
    (extra='ignore' on the envelope) but the Critic flags it.
    """
    scenario = load_scenario("sip_increase")
    # Inject one response with unknown schema version
    from copy import deepcopy
    old_resp = scenario.fixture_results[0].response
    patched_data = old_resp.model_dump(mode="json")
    patched_data["schema_version"] = "99.0"
    new_resp = AgentResponse.model_validate(patched_data)

    patched_results = [
        scenario.fixture_results[0].__class__(
            agent_id=scenario.fixture_results[0].agent_id,
            response=new_resp,
            fallback_tier=scenario.fixture_results[0].fallback_tier,
        ),
        *scenario.fixture_results[1:],
    ]

    inputs = _build_confidence_inputs(patched_results)
    baseline = compose(inputs)
    critic_result = critic_evaluate(_QUERY, patched_results, baseline)

    assert len(critic_result.schema_warnings) == 1
    assert "99.0" in critic_result.schema_warnings[0]
    # Penalty applied
    assert critic_result.total_penalty > 0
    assert critic_result.final_confidence < baseline.score


def test_both_schema_versions_parseable_independently():
    """Old (1.0) and new (unknown) versions both parse without raising."""
    from libs.schemas.agent_envelope import AgentResponse
    base = {
        "agent_id": "cashflow_agent",
        "trace_id": str(uuid.uuid4()),
        "data_tier": "REALTIME",
        "data_freshness_hours": 0.1,
        "result": {},
        "confidence": 0.80,
        "risk_level": "LOW",
        "reasoning": "test",
    }
    for version in ("1.0", "2.0", "3.5"):
        resp = AgentResponse.model_validate({**base, "schema_version": version})
        assert resp.schema_version == version
