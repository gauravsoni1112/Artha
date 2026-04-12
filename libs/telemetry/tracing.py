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

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_tracer: trace.Tracer | None = None


def configure_tracing(service_name: str = "artha") -> None:
    """Initialise OTel tracing. Call once at startup."""
    global _tracer

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    resource = Resource.create({SERVICE_NAME: service_name})

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)


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
