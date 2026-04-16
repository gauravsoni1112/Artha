"""Unit tests for Phase 5 confidence composition and fallback tiers."""

import pytest

from libs.confidence import (
    AgentConfidenceInput,
    FallbackTier,
    TIER_PENALTY,
    compose,
)


# ---------------------------------------------------------------------------
# FallbackTier / TIER_PENALTY
# ---------------------------------------------------------------------------


def test_tier_penalty_primary_is_zero():
    assert TIER_PENALTY[FallbackTier.PRIMARY] == 0.0


def test_tier_penalty_secondary():
    assert TIER_PENALTY[FallbackTier.SECONDARY] == -10.0


def test_tier_penalty_tertiary():
    assert TIER_PENALTY[FallbackTier.TERTIARY] == -25.0


def test_tier_penalty_failure_zero():
    # FAILURE agents are excluded; no penalty applied to score
    assert TIER_PENALTY[FallbackTier.FAILURE] == 0.0


def test_all_tiers_have_penalties():
    assert set(TIER_PENALTY.keys()) == set(FallbackTier)


# ---------------------------------------------------------------------------
# compose() — happy paths
# ---------------------------------------------------------------------------


def test_single_primary_agent():
    result = compose([AgentConfidenceInput("cashflow", 0.8, FallbackTier.PRIMARY)])
    assert result.score == 80.0
    assert result.gaps == []
    assert result.warnings == []


def test_single_secondary_agent_penalised():
    result = compose([AgentConfidenceInput("cashflow", 0.8, FallbackTier.SECONDARY)])
    assert result.score == 70.0  # 80 - 10
    assert "cashflow" in result.warnings[0]
    assert "−10 pp" in result.warnings[0]


def test_single_tertiary_agent_penalised():
    result = compose([AgentConfidenceInput("tax", 0.9, FallbackTier.TERTIARY)])
    assert result.score == 65.0  # 90 - 25
    assert "−25 pp" in result.warnings[0]


def test_average_across_multiple_primary_agents():
    inputs = [
        AgentConfidenceInput("cashflow", 0.8, FallbackTier.PRIMARY),
        AgentConfidenceInput("investment", 0.6, FallbackTier.PRIMARY),
        AgentConfidenceInput("goal", 1.0, FallbackTier.PRIMARY),
    ]
    result = compose(inputs)
    assert result.score == pytest.approx((80 + 60 + 100) / 3, rel=1e-3)
    assert result.gaps == []
    assert result.warnings == []


def test_failure_agent_excluded_from_score():
    inputs = [
        AgentConfidenceInput("cashflow", 0.8, FallbackTier.PRIMARY),
        AgentConfidenceInput("risk", 0.0, FallbackTier.FAILURE),
    ]
    result = compose(inputs)
    assert result.score == 80.0          # risk excluded
    assert "risk" in result.gaps
    assert result.gaps == ["risk"]


def test_mixed_tiers_averaging():
    inputs = [
        AgentConfidenceInput("cashflow", 0.8, FallbackTier.PRIMARY),    # 80
        AgentConfidenceInput("investment", 0.9, FallbackTier.SECONDARY), # 90 - 10 = 80
        AgentConfidenceInput("tax", 0.8, FallbackTier.TERTIARY),         # 80 - 25 = 55
    ]
    result = compose(inputs)
    assert result.score == pytest.approx((80 + 80 + 55) / 3, rel=1e-3)
    assert len(result.warnings) == 2  # secondary + tertiary


# ---------------------------------------------------------------------------
# compose() — edge cases
# ---------------------------------------------------------------------------


def test_penalty_cannot_drive_score_below_zero():
    # base 0.1 (10%) - 25 tertiary penalty = capped at 0
    result = compose([AgentConfidenceInput("tax", 0.1, FallbackTier.TERTIARY)])
    assert result.score == 0.0


def test_all_agents_failure():
    inputs = [
        AgentConfidenceInput("cashflow", 0.8, FallbackTier.FAILURE),
        AgentConfidenceInput("risk", 0.5, FallbackTier.FAILURE),
    ]
    result = compose(inputs)
    assert result.score == 0.0
    assert set(result.gaps) == {"cashflow", "risk"}
    assert "All agents failed" in result.warnings[0]


def test_empty_inputs():
    result = compose([])
    assert result.score == 0.0
    assert "No agent inputs" in result.warnings[0]


def test_score_rounded_to_two_decimal_places():
    inputs = [
        AgentConfidenceInput("a", 0.7, FallbackTier.PRIMARY),  # 70.0
        AgentConfidenceInput("b", 0.8, FallbackTier.PRIMARY),  # 80.0
        AgentConfidenceInput("c", 0.9, FallbackTier.PRIMARY),  # 90.0
    ]
    result = compose(inputs)
    assert result.score == round((70 + 80 + 90) / 3, 2)


def test_full_confidence_primary_stays_at_100():
    result = compose([AgentConfidenceInput("cashflow", 1.0, FallbackTier.PRIMARY)])
    assert result.score == 100.0
