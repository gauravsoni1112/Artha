"""
Prometheus HTTP metrics middleware for FastAPI.

Tracks per-route request count and latency using OTel instruments so they
appear alongside all other artha_* metrics at GET /metrics.

Usage (in api/main.py):
    from api.middleware import PrometheusMiddleware
    app.add_middleware(PrometheusMiddleware)
"""

from __future__ import annotations

import time

from opentelemetry import metrics
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_meter = metrics.get_meter("artha.http")

_http_requests_total = _meter.create_counter(
    "artha_http_requests_total",
    description="Total HTTP requests handled, labelled by method, route, and status code",
)

_http_request_duration = _meter.create_histogram(
    "artha_http_request_duration_seconds",
    description="HTTP request duration in seconds",
    unit="s",
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record request count and latency for every HTTP request.

    The /metrics endpoint is skipped to avoid inflating its own counters.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip the scrape endpoint itself — avoid self-referential noise.
        if request.url.path == "/metrics":
            return await call_next(request)

        t0 = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - t0

        attrs = {
            "method": request.method,
            "route": request.url.path,
            "status_code": str(response.status_code),
        }
        _http_requests_total.add(1, attrs)
        _http_request_duration.record(duration, attrs)

        return response
