"""
OTel metrics for domain agents (per-agent scope).

All meters use "artha.agent" scope. Call record_agent_run() at the end of
BaseAgent.run() and record_agent_error() in the except branch.

Usage:
    from services.agents._common.metrics import record_agent_run, record_agent_error

    record_agent_run(
        agent_id="cashflow_agent",
        duration_seconds=1.23,
        confidence=0.85,
        iterations=1,
    )
    record_agent_error("cashflow_agent")
"""

from __future__ import annotations

from opentelemetry import metrics

_meter = metrics.get_meter("artha.agent")

# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

_agent_run_latency = _meter.create_histogram(
    "artha_agent_run_duration_seconds",
    description="End-to-end latency of BaseAgent.run() per agent",
    unit="s",
)

_agent_confidence = _meter.create_histogram(
    "artha_agent_confidence",
    description="Final confidence score (0.0–1.0) returned by each agent run",
    unit="score",
)

_agent_reflection_iters = _meter.create_histogram(
    "artha_agent_reflection_iterations",
    description="Number of reflection iterations performed per agent run",
    unit="count",
)

_agent_errors_total = _meter.create_counter(
    "artha_agent_errors_total",
    description="Count of unhandled exceptions raised in BaseAgent.run()",
)


# ---------------------------------------------------------------------------
# Public recording functions
# ---------------------------------------------------------------------------


def record_agent_run(
    agent_id: str,
    duration_seconds: float,
    confidence: float,
    iterations: int,
) -> None:
    """Record a successful agent run — latency, confidence, and iteration count."""
    attrs = {"agent_id": agent_id}
    _agent_run_latency.record(duration_seconds, attrs)
    _agent_confidence.record(confidence, attrs)
    _agent_reflection_iters.record(iterations, attrs)


def record_agent_error(agent_id: str) -> None:
    """Increment the error counter for an agent that raised an unhandled exception."""
    _agent_errors_total.add(1, {"agent_id": agent_id})
