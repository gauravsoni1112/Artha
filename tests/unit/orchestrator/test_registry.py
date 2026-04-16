"""Unit tests for AgentRegistryCache."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.schemas.db_models import AgentRegistryEntry
from services.orchestrator.registry import AgentRegistryCache


def _entry(agent_id: str, status: str = "HEALTHY", capabilities: list | None = None) -> AgentRegistryEntry:
    e = AgentRegistryEntry()
    e.agent_id = agent_id
    e.status = status
    e.capabilities = capabilities or [agent_id.replace("_agent", "")]
    e.endpoint = f"http://{agent_id}:8001"
    e.health_endpoint = f"http://{agent_id}:8001/health"
    e.timeout_ms = 10000
    e.cache_ttl_hours = 1.0
    e.fallback_strategy = "cached_response"
    e.scope = "individual"
    return e


def _make_registry(entries: list[AgentRegistryEntry]) -> AgentRegistryCache:
    """Build a registry with a mock session factory returning the given entries."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = entries

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session

    return AgentRegistryCache(session_factory=mock_factory)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


def test_starts_empty():
    registry = _make_registry([])
    assert registry.agent_count == 0
    assert registry.list_available() == []
    assert registry.get_agent("cashflow_agent") is None
    assert registry.last_refreshed is None


# ---------------------------------------------------------------------------
# refresh()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_loads_healthy_agents():
    entries = [
        _entry("cashflow_agent"),
        _entry("investment_agent"),
    ]
    registry = _make_registry(entries)
    count = await registry.refresh()

    assert count == 2
    assert registry.agent_count == 2
    assert registry.last_refreshed is not None


@pytest.mark.asyncio
async def test_refresh_sets_last_refreshed_timestamp():
    registry = _make_registry([_entry("cashflow_agent")])
    before = datetime.now(timezone.utc)
    await registry.refresh()
    after = datetime.now(timezone.utc)
    assert before <= registry.last_refreshed <= after


@pytest.mark.asyncio
async def test_refresh_replaces_previous_snapshot():
    first_entries = [_entry("cashflow_agent")]
    second_entries = [_entry("investment_agent")]

    mock_result_1 = MagicMock()
    mock_result_1.scalars.return_value.all.return_value = first_entries
    mock_result_2 = MagicMock()
    mock_result_2.scalars.return_value.all.return_value = second_entries

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[mock_result_1, mock_result_2])
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=mock_session)

    registry = AgentRegistryCache(session_factory=factory)
    await registry.refresh()
    assert registry.get_agent("cashflow_agent") is not None
    assert registry.get_agent("investment_agent") is None

    await registry.refresh()
    assert registry.get_agent("cashflow_agent") is None
    assert registry.get_agent("investment_agent") is not None


# ---------------------------------------------------------------------------
# list_available / get_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_available_excludes_degraded():
    entries = [
        _entry("cashflow_agent", status="HEALTHY"),
        _entry("tax_agent", status="DEGRADED"),
    ]
    registry = _make_registry(entries)
    await registry.refresh()

    available_ids = {a.agent_id for a in registry.list_available()}
    assert available_ids == {"cashflow_agent"}


@pytest.mark.asyncio
async def test_get_agent_returns_entry():
    e = _entry("cashflow_agent")
    registry = _make_registry([e])
    await registry.refresh()

    fetched = registry.get_agent("cashflow_agent")
    assert fetched is not None
    assert fetched.agent_id == "cashflow_agent"
    assert fetched.endpoint == "http://cashflow_agent:8001"


@pytest.mark.asyncio
async def test_get_agent_unknown_returns_none():
    registry = _make_registry([_entry("cashflow_agent")])
    await registry.refresh()
    assert registry.get_agent("unknown_agent") is None


@pytest.mark.asyncio
async def test_list_available_capabilities_preserved():
    e = _entry("cashflow_agent", capabilities=["cashflow", "spending_trend"])
    registry = _make_registry([e])
    await registry.refresh()

    available = registry.list_available()
    assert len(available) == 1
    assert available[0].capabilities == ["cashflow", "spending_trend"]
