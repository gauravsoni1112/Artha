"""
Unit test configuration — shared OTel metrics infrastructure.

The OTel global MeterProvider can only be set ONCE per process.
This conftest creates a single session-scoped InMemoryMetricReader with DELTA
temporality so all unit test modules share the same reader/provider.

DELTA temporality means each call to reader.get_metrics_data() returns only
the increments since the previous call — tests flush residual state by calling
reader.get_metrics_data() at the start of each test before their assertion.

Usage in test modules:
    def test_something(unit_metrics_reader):
        import importlib
        import services.orchestrator.metrics as m
        importlib.reload(m)           # rebind _meter to the session provider

        unit_metrics_reader.get_metrics_data()   # flush residual delta
        m.record_something(...)
        data = unit_metrics_reader.get_metrics_data()
        assert ...
"""

from __future__ import annotations

import pytest
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics._internal.instrument import (
    Counter,
    Histogram,
    UpDownCounter,
)
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader


@pytest.fixture(scope="session")
def unit_metrics_reader() -> InMemoryMetricReader:
    """
    Single InMemoryMetricReader bound to the global OTel MeterProvider.

    Set up once for the entire test session. All metrics modules that call
    importlib.reload() after this fixture fires will have their _meter bound
    to this provider and their data collected by this reader.
    """
    reader = InMemoryMetricReader(
        preferred_temporality={
            Counter: AggregationTemporality.DELTA,
            Histogram: AggregationTemporality.DELTA,
            UpDownCounter: AggregationTemporality.DELTA,
        }
    )
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return reader
