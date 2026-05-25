"""
OTel metrics for confidence composition.

Scope: "artha.confidence"

Usage:
    from libs.confidence.metrics import record_composition

    record_composition(
        gap_count=1,
        tier_penalties=[("cashflow_agent", -10.0)],
        score=68.5,
    )
"""

from __future__ import annotations

from opentelemetry import metrics

_meter = metrics.get_meter("artha.confidence")

# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

_composition_gap_count = _meter.create_histogram(
    "artha_composition_gap_count",
    description="Number of FAILURE-tier agents excluded from each composition call",
    unit="count",
)

_composition_tier_penalty = _meter.create_histogram(
    "artha_composition_tier_penalty_pp",
    description="Per-agent tier penalty applied during composition (percentage points)",
    unit="pp",
)

_composition_score = _meter.create_histogram(
    "artha_composition_score",
    description="Final composite confidence score after tier adjustments (0–100 pp scale)",
    unit="score",
)


# ---------------------------------------------------------------------------
# Public recording functions
# ---------------------------------------------------------------------------


def record_composition(
    gap_count: int,
    tier_penalties: list[tuple[str, float]],
    score: float,
) -> None:
    """Record composition results.

    Args:
        gap_count:      Number of FAILURE-tier agents excluded.
        tier_penalties: List of (agent_id, penalty_pp) — 0 for PRIMARY, -10 for
                        SECONDARY, -25 for TERTIARY. Only non-zero penalties are
                        recorded (PRIMARY agents add no noise to this histogram).
        score:          Final composite score on the 0–100 pp scale.
    """
    _composition_gap_count.record(gap_count, {})
    for agent_id, penalty in tier_penalties:
        if penalty != 0.0:
            _composition_tier_penalty.record(abs(penalty), {"agent_id": agent_id})
    _composition_score.record(score, {})
