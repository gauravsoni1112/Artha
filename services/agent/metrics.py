"""
OTel metrics for agent runtime modules: grounding and reflection.

Scope: "artha.agent.runtime"

Usage:
    from services.agent.metrics import record_grounding_check, record_reflection_result

    record_grounding_check(passed=True)
    record_grounding_check(passed=False, ungrounded_count=3)
    record_reflection_result(iterations=2, hit_max=False)
"""

from __future__ import annotations

from opentelemetry import metrics

_meter = metrics.get_meter("artha.agent.runtime")

# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

_grounding_checks_total = _meter.create_counter(
    "artha_grounding_checks_total",
    description="Count of grounding checks by outcome (passed or failed)",
)

_grounding_ungrounded_count = _meter.create_histogram(
    "artha_grounding_ungrounded_amount_count",
    description="Number of ungrounded ₹ amounts per failed grounding check",
    unit="count",
)

_reflection_iterations = _meter.create_histogram(
    "artha_reflection_iterations_total",
    description="Number of reflection iterations taken per agent execution",
    unit="count",
)

_reflection_max_hit_total = _meter.create_counter(
    "artha_reflection_max_iterations_hit_total",
    description=(
        "Count of agent executions that hit MAX_REFLECT_ITERATIONS "
        "without reaching the confidence threshold"
    ),
)

_llm_call_latency = _meter.create_histogram(
    "artha_llm_call_duration_seconds",
    description="Latency of individual LLM API calls inside agent execution",
    unit="s",
)

_langfuse_export_errors_total = _meter.create_counter(
    "artha_langfuse_export_errors_total",
    description="Count of errors while exporting spans/traces/scores to Langfuse",
)


# ---------------------------------------------------------------------------
# Public recording functions
# ---------------------------------------------------------------------------


def record_grounding_check(passed: bool, ungrounded_count: int = 0) -> None:
    """Record the result of a grounding check on an agent's answer."""
    outcome = "passed" if passed else "failed"
    _grounding_checks_total.add(1, {"outcome": outcome})
    if not passed and ungrounded_count > 0:
        _grounding_ungrounded_count.record(ungrounded_count, {})


def record_llm_call(agent_id: str, model: str, duration_seconds: float) -> None:
    """Record the wall-clock latency of a single LLM API call."""
    _llm_call_latency.record(duration_seconds, {"agent_id": agent_id, "model": model})


def record_langfuse_export_error(operation: str) -> None:
    """Increment the Langfuse export error counter for the named operation."""
    _langfuse_export_errors_total.add(1, {"operation": operation})


def record_reflection_result(iterations: int, hit_max: bool) -> None:
    """Record how many iterations were performed and whether the cap was hit."""
    _reflection_iterations.record(iterations, {})
    if hit_max:
        _reflection_max_hit_total.add(1, {})
