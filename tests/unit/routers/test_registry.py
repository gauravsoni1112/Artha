"""
Unit tests for api/routers/registry.py.

We test the pure logic helpers and response-shaping; the DB insert/upsert
is exercised through mock sessions so no Postgres is needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.routers.registry import _to_response
from libs.schemas.db_models import AgentRegistryEntry


# ---------------------------------------------------------------------------
# _to_response helper
# ---------------------------------------------------------------------------


def _make_entry(**overrides) -> AgentRegistryEntry:
    now = datetime.now(timezone.utc)
    entry = AgentRegistryEntry()
    entry.agent_id = overrides.get("agent_id", "cashflow_agent")
    entry.endpoint = overrides.get("endpoint", "http://cashflow_agent:8001")
    entry.health_endpoint = overrides.get("health_endpoint", "http://cashflow_agent:8001/health")
    entry.capabilities = overrides.get("capabilities", ["cashflow", "spending"])
    entry.schema_version = overrides.get("schema_version", "1.0")
    entry.timeout_ms = overrides.get("timeout_ms", 10000)
    entry.fallback_strategy = overrides.get("fallback_strategy", "cached_response")
    entry.cache_ttl_hours = overrides.get("cache_ttl_hours", 1.0)
    entry.scope = overrides.get("scope", "individual")
    entry.status = overrides.get("status", "HEALTHY")
    entry.last_heartbeat = overrides.get("last_heartbeat", now)
    entry.registered_at = overrides.get("registered_at", now)
    entry.updated_at = overrides.get("updated_at", now)
    return entry


def test_to_response_basic():
    entry = _make_entry()
    resp = _to_response(entry)
    assert resp.agent_id == "cashflow_agent"
    assert resp.status == "HEALTHY"
    assert "cashflow" in resp.capabilities
    assert resp.cache_ttl_hours == 1.0


def test_to_response_cache_ttl_is_float():
    """cache_ttl_hours must always come back as float even if stored as Decimal."""
    from decimal import Decimal
    entry = _make_entry(cache_ttl_hours=Decimal("2.5"))
    resp = _to_response(entry)
    assert isinstance(resp.cache_ttl_hours, float)
    assert resp.cache_ttl_hours == pytest.approx(2.5)


def test_to_response_null_heartbeat():
    entry = _make_entry(last_heartbeat=None)
    resp = _to_response(entry)
    assert resp.last_heartbeat is None


# ---------------------------------------------------------------------------
# AgentRegistrationPayload validation
# ---------------------------------------------------------------------------


from api.routers.registry import AgentRegistrationPayload


def test_payload_defaults():
    p = AgentRegistrationPayload(
        agent_id="risk_agent",
        endpoint="http://risk_agent:8004",
        health_endpoint="http://risk_agent:8004/health",
        capabilities=["risk"],
    )
    assert p.schema_version == "1.0"
    assert p.timeout_ms == 10_000
    assert p.fallback_strategy == "cached_response"
    assert p.cache_ttl_hours == 1.0
    assert p.scope == "individual"


def test_payload_custom_values():
    p = AgentRegistrationPayload(
        agent_id="tax_agent",
        endpoint="http://tax_agent:8003",
        health_endpoint="http://tax_agent:8003/health",
        capabilities=["tax", "itr"],
        timeout_ms=20_000,
        scope="family",
    )
    assert p.timeout_ms == 20_000
    assert p.scope == "family"
    assert "itr" in p.capabilities


# ---------------------------------------------------------------------------
# GET /registry/agents/{agent_id} — 404 branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_agent_not_found():
    from api.routers.registry import get_agent

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_agent("nonexistent_agent", session=mock_session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_agent_found():
    from api.routers.registry import get_agent

    entry = _make_entry(agent_id="goal_agent")
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=entry)

    resp = await get_agent("goal_agent", session=mock_session)
    assert resp.agent_id == "goal_agent"


# ---------------------------------------------------------------------------
# DELETE /registry/agents/{agent_id} — 404 branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deregister_not_found():
    from api.routers.registry import deregister_agent

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await deregister_agent("nonexistent_agent", session=mock_session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_deregister_success():
    from api.routers.registry import deregister_agent

    entry = _make_entry(agent_id="cashflow_agent")
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=entry)
    mock_session.delete = AsyncMock()
    mock_session.commit = AsyncMock()

    await deregister_agent("cashflow_agent", session=mock_session)
    mock_session.delete.assert_called_once_with(entry)
    mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# list_agents — query filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_agents_returns_all():
    from api.routers.registry import list_agents

    entries = [_make_entry(agent_id="cashflow_agent"), _make_entry(agent_id="tax_agent")]
    mock_session = AsyncMock()
    mock_session.scalars = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=entries))
    )

    result = await list_agents(status=None, scope=None, session=mock_session)
    assert len(result) == 2
    agent_ids = {r.agent_id for r in result}
    assert "cashflow_agent" in agent_ids
    assert "tax_agent" in agent_ids
