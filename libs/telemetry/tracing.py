"""
OpenTelemetry tracing setup for Artha.

Call configure_tracing() once at application startup.
Then use start_span() as a context manager:

    from libs.telemetry.tracing import start_span

    with start_span("parse_document", {"doc_type": doc_type}):
        ...
"""

import os
from contextlib import contextmanager
from typing import Generator

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_tracer: trace.Tracer | None = None


def configure_tracing(service_name: str = "artha") -> None:
    """Initialise OTel tracing and metrics. Call once at startup."""
    global _tracer

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    resource = Resource.create({SERVICE_NAME: service_name})

    # ── Tracing ───────────────────────────────────────────────────────────────
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)

    # ── Metrics (Prometheus) ──────────────────────────────────────────────────
    # PrometheusMetricReader registers all OTel instruments into the default
    # prometheus_client registry, which is then served at GET /metrics.
    _prometheus_reader = PrometheusMetricReader()
    meter_provider = MeterProvider(resource=resource, metric_readers=[_prometheus_reader])
    metrics.set_meter_provider(meter_provider)


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        # Fallback: no-op tracer (useful in unit tests)
        _tracer = trace.get_tracer("artha")
    return _tracer


@contextmanager
def start_span(name: str, attributes: dict | None = None) -> Generator[trace.Span, None, None]:
    """Context manager that creates and closes an OTel span."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        yield span
