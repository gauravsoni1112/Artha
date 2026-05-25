"""
Unit tests for agent-level metrics emission.

Verifies services/agents/_common/metrics.py, services/agent/metrics.py, and
libs/confidence/metrics.py using the shared session-scoped unit_metrics_reader
from tests/unit/conftest.py.
"""

from __future__ import annotations

import importlib

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


# ---------------------------------------------------------------------------
# Module-level fixtures — reload each metrics module once per test run
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def agent_m(unit_metrics_reader: InMemoryMetricReader):
    import services.agents._common.metrics as m
    importlib.reload(m)
    return unit_metrics_reader, m


@pytest.fixture(scope="module")
def runtime_m(unit_metrics_reader: InMemoryMetricReader):
    import services.agent.metrics as m
    importlib.reload(m)
    return unit_metrics_reader, m


@pytest.fixture(scope="module")
def confidence_m(unit_metrics_reader: InMemoryMetricReader):
    import libs.confidence.metrics as m
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
    reader.get_metrics_data()


# ---------------------------------------------------------------------------
# services/agents/_common/metrics.py
# ---------------------------------------------------------------------------


def test_record_agent_run_all_instruments(agent_m):
    reader, m = agent_m
    flush(reader)

    m.record_agent_run(
        agent_id="cashflow_agent",
        duration_seconds=1.23,
        confidence=0.85,
        iterations=1,
    )
    data = reader.get_metrics_data()
    assert _find(data, "artha_agent_run_duration_seconds") is not None
    assert _find(data, "artha_agent_confidence") is not None
    assert _find(data, "artha_agent_reflection_iterations") is not None


def test_record_agent_run_uses_agent_id_label(agent_m):
    reader, m = agent_m
    flush(reader)

    m.record_agent_run("cashflow_agent", 0.5, 0.9, 0)
    m.record_agent_run("investment_agent", 0.8, 0.7, 1)

    data = reader.get_metrics_data()
    hist = _find(data, "artha_agent_run_duration_seconds")
    assert hist is not None
    assert len(hist.data.data_points) == 2


def test_record_agent_error_aggregation(agent_m):
    reader, m = agent_m
    flush(reader)

    m.record_agent_error("cashflow_agent")
    m.record_agent_error("cashflow_agent")

    data = reader.get_metrics_data()
    metric = _find(data, "artha_agent_errors_total")
    assert metric is not None
    assert _total(metric) == 2.0


def test_record_agent_error_per_agent(agent_m):
    reader, m = agent_m
    flush(reader)

    m.record_agent_error("cashflow_agent")
    m.record_agent_error("investment_agent")

    data = reader.get_metrics_data()
    metric = _find(data, "artha_agent_errors_total")
    assert _total(metric) == 2.0
    assert len(metric.data.data_points) == 2


# ---------------------------------------------------------------------------
# services/agent/metrics.py — grounding
# ---------------------------------------------------------------------------


def test_record_grounding_check_passed(runtime_m):
    reader, m = runtime_m
    flush(reader)

    m.record_grounding_check(passed=True)

    data = reader.get_metrics_data()
    metric = _find(data, "artha_grounding_checks_total")
    assert metric is not None
    assert _total(metric) == 1.0


def test_record_grounding_check_failed_with_count(runtime_m):
    reader, m = runtime_m
    flush(reader)

    m.record_grounding_check(passed=False, ungrounded_count=3)

    data = reader.get_metrics_data()
    counter = _find(data, "artha_grounding_checks_total")
    assert _total(counter) == 1.0

    hist = _find(data, "artha_grounding_ungrounded_amount_count")
    assert hist is not None
    assert sum(dp.count for dp in hist.data.data_points) == 1


def test_record_grounding_check_failed_no_histogram_when_zero(runtime_m):
    """ungrounded_count=0 should not add a data point to the histogram."""
    reader, m = runtime_m
    flush(reader)

    m.record_grounding_check(passed=False, ungrounded_count=0)

    data = reader.get_metrics_data()
    hist = _find(data, "artha_grounding_ungrounded_amount_count")
    assert hist is None or sum(dp.count for dp in hist.data.data_points) == 0


# ---------------------------------------------------------------------------
# services/agent/metrics.py — reflection
# ---------------------------------------------------------------------------


def test_record_reflection_result_iterations(runtime_m):
    reader, m = runtime_m
    flush(reader)

    m.record_reflection_result(iterations=2, hit_max=False)

    data = reader.get_metrics_data()
    hist = _find(data, "artha_reflection_iterations_total")
    assert hist is not None
    assert sum(dp.count for dp in hist.data.data_points) == 1


def test_record_reflection_result_hit_max(runtime_m):
    reader, m = runtime_m
    flush(reader)

    m.record_reflection_result(iterations=3, hit_max=True)

    data = reader.get_metrics_data()
    counter = _find(data, "artha_reflection_max_iterations_hit_total")
    assert counter is not None
    assert _total(counter) == 1.0


def test_record_reflection_result_no_hit_max_counter_when_false(runtime_m):
    reader, m = runtime_m
    flush(reader)

    m.record_reflection_result(iterations=1, hit_max=False)

    data = reader.get_metrics_data()
    counter = _find(data, "artha_reflection_max_iterations_hit_total")
    assert counter is None or _total(counter) == 0.0


# ---------------------------------------------------------------------------
# libs/confidence/metrics.py
# ---------------------------------------------------------------------------


def test_record_composition_gap_count(confidence_m):
    reader, m = confidence_m
    flush(reader)

    m.record_composition(gap_count=2, tier_penalties=[], score=55.0)

    data = reader.get_metrics_data()
    hist = _find(data, "artha_composition_gap_count")
    assert hist is not None
    assert sum(dp.count for dp in hist.data.data_points) == 1


def test_record_composition_tier_penalty_histogram(confidence_m):
    reader, m = confidence_m
    flush(reader)

    m.record_composition(
        gap_count=0,
        tier_penalties=[("cashflow_agent", -10.0), ("investment_agent", -25.0)],
        score=65.0,
    )

    data = reader.get_metrics_data()
    hist = _find(data, "artha_composition_tier_penalty_pp")
    assert hist is not None
    assert sum(dp.count for dp in hist.data.data_points) == 2


def test_record_composition_primary_penalty_not_recorded(confidence_m):
    """PRIMARY agents have 0.0 penalty — should not produce a histogram data point."""
    reader, m = confidence_m
    flush(reader)

    m.record_composition(
        gap_count=0,
        tier_penalties=[("cashflow_agent", 0.0)],
        score=80.0,
    )

    data = reader.get_metrics_data()
    hist = _find(data, "artha_composition_tier_penalty_pp")
    assert hist is None or sum(dp.count for dp in hist.data.data_points) == 0


def test_record_composition_score_histogram(confidence_m):
    reader, m = confidence_m
    flush(reader)

    m.record_composition(gap_count=0, tier_penalties=[], score=78.5)

    data = reader.get_metrics_data()
    hist = _find(data, "artha_composition_score")
    assert hist is not None
    assert sum(dp.count for dp in hist.data.data_points) == 1
