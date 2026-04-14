"""
Unit tests for api/routers/agent_router.py.

Tests the routing helpers: _pick_agent (DB query), _forward_to_agent (httpx),
and the full route_query dispatch path.  All external calls are mocked.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from api.routers.agent_router import RouterQueryRequest, _pick_agent
from libs.schemas.db_models import AgentRegistryEntry
from libs.schemas.user_profile import UserProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(agent_id: str = "cashflow_agent", capabilities: list[str] | None = None) -> AgentRegistryEntry:
    now = datetime.now(timezone.utc)
    entry = AgentRegistryEntry()
    entry.agent_id = agent_id
    entry.endpoint = f"http://{agent_id}:8001"
    entry.health_endpoint = f"http://{agent_id}:8001/health"
    entry.capabilities = capabilities or ["cashflow", "spending"]
    entry.schema_version = "1.0"
    entry.timeout_ms = 10_000
    entry.fallback_strategy = "cached_response"
    entry.cache_ttl_hours = 1.0
    entry.scope = "individual"
    entry.status = "HEALTHY"
    entry.last_heartbeat = now
    entry.registered_at = now
    entry.updated_at = now
    return entry


def _make_user_profile() -> UserProfile:
    return UserProfile(
        owner_id=uuid.uuid4(),
        name="Test User",
        total_monthly_income_paise=100_000 * 100,
        risk_appetite="moderate",
    )


# ---------------------------------------------------------------------------
# RouterQueryRequest schema
# ---------------------------------------------------------------------------


def test_router_request_defaults():
    req = RouterQueryRequest(
        query="What is my cashflow?",
        capability="cashflow",
        user_profile=_make_user_profile(),
    )
    assert req.context == {}
    assert req.trace_id is not None


def test_router_request_custom_trace_id():
    tid = uuid.uuid4()
    req = RouterQueryRequest(
        query="Tax summary",
        capability="tax",
        user_profile=_make_user_profile(),
        trace_id=tid,
    )
    assert req.trace_id == tid


# ---------------------------------------------------------------------------
# _pick_agent — returns None when no match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pick_agent_no_match():
    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=None)

    result = await _pick_agent("unknown_capability", mock_session)
    assert result is None


@pytest.mark.asyncio
async def test_pick_agent_returns_entry():
    entry = _make_entry()
    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=entry)

    result = await _pick_agent("cashflow", mock_session)
    assert result is not None
    assert result.agent_id == "cashflow_agent"


# ---------------------------------------------------------------------------
# _forward_to_agent — httpx mocking
# ---------------------------------------------------------------------------


def _make_agent_response_json() -> dict:
    return {
        "agent_id": "cashflow_agent",
        "schema_version": "1.0",
        "trace_id": str(uuid.uuid4()),
        "data_tier": "CACHED",
        "data_freshness_hours": 0.5,
        "result": {"answer": "You spent ₹10,000 last month."},
        "confidence": 0.9,
        "risk_level": "LOW",
        "reasoning": "Based on last 30 days of transactions.",
        "warnings": [],
        "fallback_used": False,
        "fallback_reason": None,
    }


@pytest.mark.asyncio
async def test_forward_success():
    from api.routers.agent_router import _forward_to_agent
    from libs.schemas.agent_envelope import AgentRequest

    entry = _make_entry()
    request = AgentRequest(
        query="test",
        user_profile=_make_user_profile(),
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=_make_agent_response_json())

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("api.routers.agent_router.httpx.AsyncClient", return_value=mock_client):
        response = await _forward_to_agent(entry, request)

    assert response.agent_id == "cashflow_agent"
    assert response.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_forward_timeout_raises_504():
    from api.routers.agent_router import _forward_to_agent
    from libs.schemas.agent_envelope import AgentRequest

    entry = _make_entry()
    request = AgentRequest(query="test", user_profile=_make_user_profile())

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("api.routers.agent_router.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await _forward_to_agent(entry, request)

    assert exc_info.value.status_code == 504


@pytest.mark.asyncio
async def test_forward_http_error_raises_502():
    from api.routers.agent_router import _forward_to_agent
    from libs.schemas.agent_envelope import AgentRequest

    entry = _make_entry()
    request = AgentRequest(query="test", user_profile=_make_user_profile())

    error_response = MagicMock()
    error_response.status_code = 500
    error_response.text = "Internal Server Error"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=error_response)
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("api.routers.agent_router.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await _forward_to_agent(entry, request)

    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_forward_request_error_raises_502():
    from api.routers.agent_router import _forward_to_agent
    from libs.schemas.agent_envelope import AgentRequest

    entry = _make_entry()
    request = AgentRequest(query="test", user_profile=_make_user_profile())

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("api.routers.agent_router.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await _forward_to_agent(entry, request)

    assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# route_query — full dispatch path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_query_no_agent_raises_503():
    from api.routers.agent_router import route_query

    body = RouterQueryRequest(
        query="What is my risk profile?",
        capability="unknown",
        user_profile=_make_user_profile(),
    )

    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await route_query(body, session=mock_session)

    assert exc_info.value.status_code == 503
    assert "unknown" in exc_info.value.detail


@pytest.mark.asyncio
async def test_route_query_success():
    from api.routers.agent_router import route_query

    body = RouterQueryRequest(
        query="What is my cashflow this month?",
        capability="cashflow",
        user_profile=_make_user_profile(),
    )

    entry = _make_entry()

    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=entry)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=_make_agent_response_json())

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("api.routers.agent_router.httpx.AsyncClient", return_value=mock_client):
        result = await route_query(body, session=mock_session)

    assert result.routed_to == "cashflow_agent"
    assert result.response.agent_id == "cashflow_agent"
    assert result.agent_endpoint == entry.endpoint


@pytest.mark.asyncio
async def test_route_query_propagates_trace_id():
    from api.routers.agent_router import route_query

    trace = uuid.uuid4()
    body = RouterQueryRequest(
        query="check emergency fund",
        capability="risk",
        user_profile=_make_user_profile(),
        trace_id=trace,
    )

    entry = _make_entry(agent_id="risk_agent", capabilities=["risk"])
    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=entry)

    response_json = _make_agent_response_json()
    response_json["trace_id"] = str(trace)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=response_json)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    captured_payload: dict = {}

    async def capture_post(url, json=None, **kwargs):
        nonlocal captured_payload
        captured_payload = json or {}
        return mock_response

    mock_client.post = capture_post

    with patch("api.routers.agent_router.httpx.AsyncClient", return_value=mock_client):
        result = await route_query(body, session=mock_session)

    assert captured_payload.get("trace_id") == str(trace)
