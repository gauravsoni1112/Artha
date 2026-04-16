"""Unit tests for the Critic agent."""

import uuid
from dataclasses import replace

import pytest

from libs.confidence.composition import CompositeResult
from libs.confidence.tier import FallbackTier
from libs.schemas.agent_envelope import AgentResponse, DataTier, RiskLevel
from services.orchestrator.critic import (
    INCONSISTENCY_PP,
    GAP_PENALTY_PP,
    KNOWN_SCHEMA_VERSIONS,
    MAX_CRITIC_PENALTY_PP,
    UNKNOWN_SCHEMA_PP,
    ConsistencyFlag,
    CriticResult,
    evaluate,
    _check_net_worth,
    _check_surplus,
    _check_time_horizon,
)
from services.orchestrator.dispatch import DispatchedResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _response(
    agent_id: str = "cashflow_agent",
    result: dict | None = None,
    confidence: float = 0.85,
    schema_version: str = "1.0",
) -> AgentResponse:
    return AgentResponse(
        agent_id=agent_id,
        schema_version=schema_version,
        trace_id=uuid.uuid4(),
        data_tier=DataTier.REALTIME,
        data_freshness_hours=0.0,
        result=result or {},
        confidence=confidence,
        risk_level=RiskLevel.LOW,
        reasoning="ok",
    )


def _result(
    agent_id: str,
    result_data: dict | None = None,
    tier: FallbackTier = FallbackTier.PRIMARY,
    schema_version: str = "1.0",
) -> DispatchedResult:
    return DispatchedResult(
        agent_id=agent_id,
        response=_response(agent_id, result_data, schema_version=schema_version),
        fallback_tier=tier,
    )


def _failure(agent_id: str) -> DispatchedResult:
    return DispatchedResult(
        agent_id=agent_id,
        response=None,
        fallback_tier=FallbackTier.FAILURE,
        error="unreachable",
    )


def _baseline(score: float = 80.0, gaps: list[str] | None = None) -> CompositeResult:
    return CompositeResult(score=score, gaps=gaps or [], warnings=[])


# ---------------------------------------------------------------------------
# No issues → score unchanged
# ---------------------------------------------------------------------------


def test_no_issues_score_unchanged():
    results = [
        _result("cashflow_agent", {"surplus_paise": 1_800_000}),
        _result("investment_agent", {"surplus_paise": 1_800_000}),
    ]
    critic_result = evaluate("test", results, _baseline(80.0))
    assert critic_result.final_confidence == 80.0
    assert critic_result.total_penalty == 0.0
    assert critic_result.consistency_flags == []


def test_score_never_raised():
    results = [_result("cashflow_agent", {})]
    # Even with perfect outputs, score stays at baseline
    critic_result = evaluate("test", results, _baseline(60.0))
    assert critic_result.final_confidence == 60.0


# ---------------------------------------------------------------------------
# Surplus cross-check
# ---------------------------------------------------------------------------


def test_surplus_mismatch_detected():
    results = [
        _result("cashflow_agent", {"surplus_paise": 1_800_000}),  # ₹18k
        _result("risk_agent",     {"surplus_paise": 1_200_000}),  # ₹12k — 33% diff
    ]
    flags = _check_surplus(results)
    assert len(flags) == 1
    assert flags[0].check_type == "surplus_mismatch"
    assert "cashflow_agent" in flags[0].agent_ids
    assert "risk_agent" in flags[0].agent_ids


def test_surplus_agreement_no_flag():
    results = [
        _result("cashflow_agent", {"surplus_paise": 1_800_000}),
        _result("risk_agent",     {"surplus_paise": 1_850_000}),  # 2.7% diff
    ]
    assert _check_surplus(results) == []


def test_surplus_single_agent_no_flag():
    results = [_result("cashflow_agent", {"surplus_paise": 1_800_000})]
    assert _check_surplus(results) == []


def test_surplus_near_zero_skipped():
    # Both agents report tiny surplus — skip to avoid noise
    results = [
        _result("cashflow_agent", {"surplus_paise": 5_000}),
        _result("risk_agent",     {"surplus_paise": 1_000}),
    ]
    assert _check_surplus(results) == []


def test_surplus_mismatch_applies_penalty():
    results = [
        _result("cashflow_agent", {"surplus_paise": 1_800_000}),
        _result("risk_agent",     {"surplus_paise": 1_200_000}),
    ]
    critic_result = evaluate("test", results, _baseline(80.0))
    assert critic_result.final_confidence == 80.0 - INCONSISTENCY_PP
    assert len(critic_result.consistency_flags) == 1


# ---------------------------------------------------------------------------
# Net worth cross-check
# ---------------------------------------------------------------------------


def test_net_worth_mismatch_detected():
    results = [
        _result("investment_agent", {"net_worth_paise": 50_000_000}),
        _result("risk_agent",       {"net_worth_paise": 30_000_000}),  # 40% diff
    ]
    flags = _check_net_worth(results)
    assert len(flags) == 1
    assert flags[0].check_type == "net_worth_mismatch"


def test_net_worth_agreement_no_flag():
    results = [
        _result("investment_agent", {"net_worth_paise": 50_000_000}),
        _result("risk_agent",       {"net_worth_paise": 51_000_000}),  # 2% diff
    ]
    assert _check_net_worth(results) == []


# ---------------------------------------------------------------------------
# Time horizon cross-check
# ---------------------------------------------------------------------------


def test_time_horizon_mismatch_detected():
    results = [
        _result("goal_agent", {"target_years": 30}),
        _result("risk_agent", {"time_horizon_years": 10}),  # 20yr delta
    ]
    flags = _check_time_horizon(results)
    assert len(flags) == 1
    assert flags[0].check_type == "time_horizon_mismatch"


def test_time_horizon_within_tolerance():
    results = [
        _result("goal_agent", {"target_years": 15}),
        _result("risk_agent", {"time_horizon_years": 12}),  # 3yr delta
    ]
    assert _check_time_horizon(results) == []


def test_time_horizon_missing_one_agent_skipped():
    results = [_result("goal_agent", {"target_years": 25})]
    assert _check_time_horizon(results) == []


# ---------------------------------------------------------------------------
# Multiple inconsistencies
# ---------------------------------------------------------------------------


def test_multiple_inconsistencies_cumulative_penalty():
    results = [
        _result("cashflow_agent",   {"surplus_paise": 1_800_000, "net_worth_paise": 50_000_000}),
        _result("investment_agent", {"surplus_paise": 1_200_000, "net_worth_paise": 30_000_000}),
    ]
    critic_result = evaluate("test", results, _baseline(80.0))
    # surplus_mismatch + net_worth_mismatch = 2 × 5 = 10 pp
    assert critic_result.total_penalty == INCONSISTENCY_PP * 2
    assert critic_result.final_confidence == 80.0 - INCONSISTENCY_PP * 2


# ---------------------------------------------------------------------------
# Gap penalty
# ---------------------------------------------------------------------------


def test_gap_in_baseline_lowers_confidence():
    results = [
        _result("cashflow_agent"),
        _failure("risk_agent"),
    ]
    baseline = _baseline(score=80.0, gaps=["risk_agent"])
    critic_result = evaluate("test", results, baseline)
    assert critic_result.total_penalty == GAP_PENALTY_PP
    assert critic_result.final_confidence == 80.0 - GAP_PENALTY_PP
    assert "risk_agent" in critic_result.gaps


def test_multiple_gaps_cumulative():
    results = [_result("cashflow_agent")]
    baseline = _baseline(score=70.0, gaps=["risk_agent", "tax_agent"])
    critic_result = evaluate("test", results, baseline)
    assert critic_result.total_penalty == GAP_PENALTY_PP * 2
    assert critic_result.final_confidence == 70.0 - GAP_PENALTY_PP * 2


# ---------------------------------------------------------------------------
# Schema version validation
# ---------------------------------------------------------------------------


def test_known_schema_no_warning():
    results = [_result("cashflow_agent", schema_version="1.0")]
    critic_result = evaluate("test", results, _baseline(80.0))
    assert critic_result.schema_warnings == []


def test_unknown_schema_adds_warning():
    results = [_result("cashflow_agent", schema_version="2.0")]
    critic_result = evaluate("test", results, _baseline(80.0))
    assert len(critic_result.schema_warnings) == 1
    assert "cashflow_agent" in critic_result.schema_warnings[0]
    assert "2.0" in critic_result.schema_warnings[0]


def test_unknown_schema_applies_penalty():
    results = [_result("cashflow_agent", schema_version="2.0")]
    critic_result = evaluate("test", results, _baseline(80.0))
    assert critic_result.total_penalty == UNKNOWN_SCHEMA_PP
    assert critic_result.final_confidence == 80.0 - UNKNOWN_SCHEMA_PP


def test_failure_tier_agent_schema_not_checked():
    # FAILURE agents have no response; schema check skips them
    results = [_failure("cashflow_agent")]
    baseline = _baseline(score=0.0, gaps=["cashflow_agent"])
    critic_result = evaluate("test", results, baseline)
    assert critic_result.schema_warnings == []


# ---------------------------------------------------------------------------
# Maximum penalty cap
# ---------------------------------------------------------------------------


def test_penalty_capped_at_max():
    # Trigger many penalties: 3 gaps (15) + 1 inconsistency (5) + 1 schema (3) = 23 pp
    # But let's construct something that would exceed 30 pp
    results = [
        _result("cashflow_agent", {"surplus_paise": 1_800_000}, schema_version="2.0"),
        _result("investment_agent", {"surplus_paise": 500_000}, schema_version="3.0"),
    ]
    # 2 gaps + surplus mismatch + 2 schema warnings
    baseline = _baseline(score=100.0, gaps=["tax_agent", "goal_agent", "risk_agent", "extra_agent", "more_agent", "even_more"])
    critic_result = evaluate("test", results, baseline)
    assert critic_result.total_penalty <= MAX_CRITIC_PENALTY_PP


def test_score_floored_at_zero():
    results = [
        _result("cashflow_agent", {"surplus_paise": 1_800_000}),
        _result("investment_agent", {"surplus_paise": 500_000}),
    ]
    # Start with very low baseline
    baseline = _baseline(score=2.0, gaps=["tax_agent", "goal_agent"])
    critic_result = evaluate("test", results, baseline)
    assert critic_result.final_confidence >= 0.0


# ---------------------------------------------------------------------------
# Downward-only invariant
# ---------------------------------------------------------------------------


def test_critic_never_raises_confidence():
    """Fuzz test: generate various result combos and assert monotone decrease."""
    for baseline_score in [0.0, 25.0, 50.0, 75.0, 100.0]:
        results = [_result("cashflow_agent", {})]
        critic_result = evaluate("anything", results, _baseline(baseline_score))
        assert critic_result.final_confidence <= baseline_score


# ---------------------------------------------------------------------------
# Warnings accumulated
# ---------------------------------------------------------------------------


def test_gap_warning_in_output():
    results = [_result("cashflow_agent")]
    baseline = _baseline(score=80.0, gaps=["risk_agent"])
    critic_result = evaluate("test", results, baseline)
    warning_text = " ".join(critic_result.warnings)
    assert "risk_agent" in warning_text
    assert "Missing data" in warning_text


def test_inconsistency_warning_in_output():
    results = [
        _result("cashflow_agent", {"surplus_paise": 1_800_000}),
        _result("risk_agent",     {"surplus_paise": 500_000}),
    ]
    critic_result = evaluate("test", results, _baseline(80.0))
    assert any("surplus_mismatch" in w for w in critic_result.warnings)


# ---------------------------------------------------------------------------
# Struct fields present
# ---------------------------------------------------------------------------


def test_critic_result_has_baseline_preserved():
    results = [_result("cashflow_agent")]
    baseline = _baseline(72.5)
    critic_result = evaluate("test", results, baseline)
    assert critic_result.baseline_confidence == 72.5
