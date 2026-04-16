"""
OTel metrics for the orchestrator layer (Phase 5).

All meters use the "artha.orchestrator" scope so they appear under a single
namespace in Prometheus / Grafana.

Usage:
    from services.orchestrator.metrics import record_recommendation, record_dispatch_tier

    record_recommendation(confidence=72.5, state="GENERATED", gap_count=1)
    record_dispatch_tier(agent_id="cashflow_agent", tier="PRIMARY")
"""

from __future__ import annotations

from opentelemetry import metrics

_meter = metrics.get_meter("artha.orchestrator")

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

# Total recommendations created, labelled by final state (always GENERATED here)
_recommendations_total = _meter.create_counter(
    "artha_recommendations_total",
    description="Total recommendations created by the orchestrator",
)

# Per-agent dispatch tier distribution — how often each tier is used
_dispatch_tier_total = _meter.create_counter(
    "artha_dispatch_tier_total",
    description="Count of agent dispatch calls by fallback tier",
)

# Recommendation state transitions (surfaced, accepted, rejected, …)
_recommendation_transitions_total = _meter.create_counter(
    "artha_recommendation_transitions_total",
    description="Count of recommendation state transitions",
)

# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------

# Final composite confidence per recommendation (0–100)
_confidence_histogram = _meter.create_histogram(
    "artha_recommendation_confidence",
    description="Final composite confidence scores (0–100)",
    unit="score",
)

# Critic penalty per recommendation
_critic_penalty_histogram = _meter.create_histogram(
    "artha_critic_penalty",
    description="Critic confidence penalty applied per recommendation",
    unit="score",
)

# ---------------------------------------------------------------------------
# Gauges (up/down-counters used as gauges per agent)
# ---------------------------------------------------------------------------

# Circuit breaker state encoded as int: CLOSED=0, OPEN=1, HALF_OPEN=2
_breaker_state_gauge = _meter.create_up_down_counter(
    "artha_breaker_state",
    description="Circuit breaker state per agent (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
)

_BREAKER_STATE_CODES = {"CLOSED": 0, "OPEN": 1, "HALF_OPEN": 2}


# ---------------------------------------------------------------------------
# Public recording functions
# ---------------------------------------------------------------------------


def record_recommendation(
    confidence: float,
    state: str,
    gap_count: int,
    critic_penalty: float,
) -> None:
    attrs = {"state": state, "has_gaps": str(gap_count > 0)}
    _recommendations_total.add(1, attrs)
    _confidence_histogram.record(confidence, attrs)
    _critic_penalty_histogram.record(critic_penalty, {})


def record_dispatch_tier(agent_id: str, tier: str) -> None:
    _dispatch_tier_total.add(1, {"agent_id": agent_id, "tier": tier})


def record_transition(from_state: str, to_state: str) -> None:
    _recommendation_transitions_total.add(
        1, {"from_state": from_state, "to_state": to_state}
    )


def record_breaker_state(agent_id: str, state: str) -> None:
    code = _BREAKER_STATE_CODES.get(state, 0)
    _breaker_state_gauge.add(code, {"agent_id": agent_id})
