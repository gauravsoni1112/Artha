"""
Unit tests for orchestrator metrics emission.

Uses the shared unit_metrics_reader session fixture (defined in tests/unit/conftest.py).
Each test flushes residual delta before asserting to stay isolated from prior tests.
"""

from __future__ import annotations

import importlib

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


# ---------------------------------------------------------------------------
# Module-level fixture — reload metrics module once against the session reader
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def otel_reader(unit_metrics_reader: InMemoryMetricReader):
    """Rebind services.orchestrator.metrics to the session provider."""
    import services.orchestrator.metrics as m
    importlib.reload(m)
    return unit_metrics_reader, m


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find(data, name: str):
    if data is None:
        return None
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == name:
                    return metric
    return None


def _total(metric) -> float:
    return sum(dp.value for dp in metric.data.data_points)


def flush(reader: InMemoryMetricReader) -> None:
    """Discard accumulated delta so next get_metrics_data() is test-local."""
    reader.get_metrics_data()


# ---------------------------------------------------------------------------
# record_recommendation
# ---------------------------------------------------------------------------


def test_record_recommendation_increments_counter(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_recommendation(confidence=72.5, state="GENERATED", gap_count=0, critic_penalty=0.0)

    data = reader.get_metrics_data()
    metric = _find(data, "artha_recommendations_total")
    assert metric is not None
    assert _total(metric) == 1.0


def test_record_recommendation_records_confidence_histogram(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_recommendation(confidence=72.5, state="GENERATED", gap_count=0, critic_penalty=5.0)

    data = reader.get_metrics_data()
    hist = _find(data, "artha_recommendation_confidence")
    assert hist is not None
    assert sum(dp.count for dp in hist.data.data_points) == 1


def test_record_recommendation_records_critic_penalty(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_recommendation(confidence=60.0, state="GENERATED", gap_count=2, critic_penalty=15.0)

    data = reader.get_metrics_data()
    hist = _find(data, "artha_critic_penalty")
    assert hist is not None
    assert sum(dp.count for dp in hist.data.data_points) == 1


# ---------------------------------------------------------------------------
# record_dispatch_tier
# ---------------------------------------------------------------------------


def test_record_dispatch_tier_aggregation(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_dispatch_tier(agent_id="cashflow_agent", tier="PRIMARY")
    m.record_dispatch_tier(agent_id="cashflow_agent", tier="PRIMARY")

    data = reader.get_metrics_data()
    metric = _find(data, "artha_dispatch_tier_total")
    assert metric is not None
    assert _total(metric) == 2.0


def test_record_dispatch_tier_different_tiers(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_dispatch_tier("cashflow_agent", "PRIMARY")
    m.record_dispatch_tier("cashflow_agent", "SECONDARY")
    m.record_dispatch_tier("investment_agent", "FAILURE")

    data = reader.get_metrics_data()
    metric = _find(data, "artha_dispatch_tier_total")
    assert _total(metric) == 3.0


# ---------------------------------------------------------------------------
# record_pipeline_stage
# ---------------------------------------------------------------------------


def test_record_pipeline_stage_histogram(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_pipeline_stage("decompose", 0.042)
    m.record_pipeline_stage("dispatch", 1.23)

    data = reader.get_metrics_data()
    hist = _find(data, "artha_pipeline_stage_duration_seconds")
    assert hist is not None
    assert sum(dp.count for dp in hist.data.data_points) == 2


def test_record_pipeline_stage_all_stages(otel_reader):
    reader, m = otel_reader
    flush(reader)

    stages = [
        "scope_resolve", "snapshot", "decompose", "dispatch",
        "compose", "critic", "synthesize", "audit_write", "e2e",
    ]
    for stage in stages:
        m.record_pipeline_stage(stage, 0.1)

    data = reader.get_metrics_data()
    hist = _find(data, "artha_pipeline_stage_duration_seconds")
    assert hist is not None
    assert sum(dp.count for dp in hist.data.data_points) == len(stages)


# ---------------------------------------------------------------------------
# record_breaker_transition
# ---------------------------------------------------------------------------


def test_record_breaker_transition_increments(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_breaker_transition("cashflow_agent", "CLOSED", "OPEN")

    data = reader.get_metrics_data()
    metric = _find(data, "artha_breaker_transitions_total")
    assert metric is not None
    assert _total(metric) == 1.0


def test_record_breaker_transition_multiple(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_breaker_transition("cashflow_agent", "CLOSED", "OPEN")
    m.record_breaker_transition("cashflow_agent", "OPEN", "HALF_OPEN")
    m.record_breaker_transition("cashflow_agent", "HALF_OPEN", "CLOSED")

    data = reader.get_metrics_data()
    metric = _find(data, "artha_breaker_transitions_total")
    assert _total(metric) == 3.0


# ---------------------------------------------------------------------------
# record_decompose_path / cycle / agent_count
# ---------------------------------------------------------------------------


def test_record_decompose_path_rule_based(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_decompose_path("rule_based")
    m.record_decompose_path("rule_based")

    data = reader.get_metrics_data()
    metric = _find(data, "artha_decompose_path_total")
    assert metric is not None
    assert _total(metric) == 2.0


def test_record_decompose_cycle(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_decompose_cycle()

    data = reader.get_metrics_data()
    metric = _find(data, "artha_decompose_cycle_detected_total")
    assert metric is not None
    assert _total(metric) == 1.0


def test_record_decompose_agent_count(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_decompose_agent_count(3, "rule_based")
    m.record_decompose_agent_count(5, "llm_fallback")

    data = reader.get_metrics_data()
    hist = _find(data, "artha_decompose_agent_count")
    assert hist is not None
    assert sum(dp.count for dp in hist.data.data_points) == 2


# ---------------------------------------------------------------------------
# record_critic_flag
# ---------------------------------------------------------------------------


def test_record_critic_flag_multi(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_critic_flag("surplus_mismatch")
    m.record_critic_flag("surplus_mismatch")
    m.record_critic_flag("time_horizon_mismatch")

    data = reader.get_metrics_data()
    metric = _find(data, "artha_critic_check_flagged_total")
    assert metric is not None
    assert _total(metric) == 3.0


def test_record_critic_flag_separate_check_types(otel_reader):
    reader, m = otel_reader
    flush(reader)

    for check in ["surplus_mismatch", "net_worth_mismatch", "time_horizon_mismatch"]:
        m.record_critic_flag(check)

    data = reader.get_metrics_data()
    metric = _find(data, "artha_critic_check_flagged_total")
    assert len(metric.data.data_points) == 3


# ---------------------------------------------------------------------------
# record_transition (recommendation state)
# ---------------------------------------------------------------------------


def test_record_transition_increments(otel_reader):
    reader, m = otel_reader
    flush(reader)

    m.record_transition("GENERATED", "SURFACED")
    m.record_transition("SURFACED", "ACCEPTED")

    data = reader.get_metrics_data()
    metric = _find(data, "artha_recommendation_transitions_total")
    assert metric is not None
    assert _total(metric) == 2.0
