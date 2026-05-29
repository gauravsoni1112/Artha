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
# Pipeline stage latency (Commit 2)
# ---------------------------------------------------------------------------

_pipeline_stage_latency = _meter.create_histogram(
    "artha_pipeline_stage_duration_seconds",
    description=(
        "Wall-clock latency of each orchestrator pipeline stage. "
        "stage label: scope_resolve | snapshot | decompose | dispatch | "
        "compose | critic | synthesize | audit_write | e2e"
    ),
    unit="s",
)

# ---------------------------------------------------------------------------
# Breaker transitions (Commit 4)
# ---------------------------------------------------------------------------

_breaker_transitions_total = _meter.create_counter(
    "artha_breaker_transitions_total",
    description="Count of circuit breaker state transitions per agent",
)

# ---------------------------------------------------------------------------
# Decompose path metrics (Commit 5)
# ---------------------------------------------------------------------------

_decompose_path_total = _meter.create_counter(
    "artha_decompose_path_total",
    description="Count of decompose calls by routing path (rule_based or llm_fallback)",
)

_decompose_cycle_detected_total = _meter.create_counter(
    "artha_decompose_cycle_detected_total",
    description="Count of dependency graph cycles detected and rejected by Kahn's algorithm",
)

_decompose_agent_count = _meter.create_histogram(
    "artha_decompose_agent_count",
    description="Number of agents selected per decompose call",
    unit="count",
)

# ---------------------------------------------------------------------------
# Critic per-check flag counters (Commit 7)
# ---------------------------------------------------------------------------

_critic_check_flagged_total = _meter.create_counter(
    "artha_critic_check_flagged_total",
    description="Count of times each critic consistency check flagged an issue",
)

# ---------------------------------------------------------------------------
# Agent HTTP call latency (dispatch → domain agent) (Commit 8)
# ---------------------------------------------------------------------------

_agent_http_call_latency = _meter.create_histogram(
    "artha_agent_http_call_duration_seconds",
    description="Latency of outbound HTTP calls from the dispatch layer to domain agents",
    unit="s",
)

# ---------------------------------------------------------------------------
# Cache hit / miss counters (Commit 8)
# ---------------------------------------------------------------------------

_cache_hits_total = _meter.create_counter(
    "artha_cache_hits_total",
    description="Count of agent response cache hits (SECONDARY + TERTIARY fallbacks served)",
)

_cache_misses_total = _meter.create_counter(
    "artha_cache_misses_total",
    description="Count of agent response cache misses (no cached entry available)",
)


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


def record_pipeline_stage(stage: str, duration_seconds: float) -> None:
    """Record wall-clock latency for a named pipeline stage."""
    _pipeline_stage_latency.record(duration_seconds, {"stage": stage})


def record_breaker_transition(agent_id: str, from_state: str, to_state: str) -> None:
    """Record a circuit breaker state transition."""
    _breaker_transitions_total.add(
        1, {"agent_id": agent_id, "from_state": from_state, "to_state": to_state}
    )


def record_decompose_path(path: str) -> None:
    """Record which decompose path was taken. path: 'rule_based' or 'llm_fallback'."""
    _decompose_path_total.add(1, {"path": path})


def record_decompose_cycle() -> None:
    """Record a cycle detected (and rejected) in the agent dependency graph."""
    _decompose_cycle_detected_total.add(1, {})


def record_decompose_agent_count(count: int, path: str) -> None:
    """Record the number of agents selected in a single decompose call."""
    _decompose_agent_count.record(count, {"path": path})


def record_agent_http_call(agent_id: str, duration_seconds: float) -> None:
    """Record the latency of one outbound HTTP call to a domain agent's /run endpoint."""
    _agent_http_call_latency.record(duration_seconds, {"agent_id": agent_id})


def record_cache_hit(agent_id: str, tier: str) -> None:
    """Record a cache hit — a SECONDARY or TERTIARY fallback response was served."""
    _cache_hits_total.add(1, {"agent_id": agent_id, "tier": tier})


def record_cache_miss(agent_id: str) -> None:
    """Record a cache miss — no usable cached response was found for this agent."""
    _cache_misses_total.add(1, {"agent_id": agent_id})


def record_critic_flag(check_type: str) -> None:
    """Record a critic consistency check that fired a flag.

    check_type: 'surplus_mismatch' | 'net_worth_mismatch' | 'time_horizon_mismatch'
    """
    _critic_check_flagged_total.add(1, {"check_type": check_type})
