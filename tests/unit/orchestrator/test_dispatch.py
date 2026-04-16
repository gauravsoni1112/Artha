"""Unit tests for Planner dispatch layer."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.confidence.tier import FallbackTier
from libs.schemas.agent_envelope import AgentResponse, DataTier, RiskLevel
from libs.schemas.user_profile import UserProfile
from services.orchestrator.breaker import BreakerConfig, BreakerState, InMemoryBreakerStore
from services.orchestrator.cache import AgentResponseCache, CachedResponse
from services.orchestrator.dispatch import DispatchedResult, _dispatch_one, dispatch_plan
from services.orchestrator.plan import AgentCall, Plan
from services.orchestrator.registry import AgentRegistryCache


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _profile() -> UserProfile:
    return UserProfile(owner_id=uuid.uuid4(), name="Test User")


def _response(agent_id: str = "cashflow_agent", confidence: float = 0.85) -> AgentResponse:
    return AgentResponse(
        agent_id=agent_id,
        trace_id=uuid.uuid4(),
        data_tier=DataTier.REALTIME,
        data_freshness_hours=0.0,
        result={"value": 42},
        confidence=confidence,
        risk_level=RiskLevel.LOW,
        reasoning="ok",
    )


def _registry_with(agent_id: str = "cashflow_agent", endpoint: str = "http://cashflow:8001") -> AgentRegistryCache:
    from libs.schemas.db_models import AgentRegistryEntry
    entry = AgentRegistryEntry()
    entry.agent_id = agent_id
    entry.endpoint = endpoint
    entry.timeout_ms = 5000
    entry.cache_ttl_hours = 1.0
    entry.status = "HEALTHY"
    entry.capabilities = [agent_id]

    registry = MagicMock(spec=AgentRegistryCache)
    registry.get_agent.return_value = entry
    return registry


def _empty_registry() -> AgentRegistryCache:
    registry = MagicMock(spec=AgentRegistryCache)
    registry.get_agent.return_value = None
    return registry


def _breaker() -> InMemoryBreakerStore:
    return InMemoryBreakerStore(BreakerConfig(failure_threshold=3))


def _cache_miss() -> AgentResponseCache:
    cache = MagicMock(spec=AgentResponseCache)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


def _cache_hit(response: AgentResponse, within_ttl: bool = True) -> AgentResponseCache:
    cache = MagicMock(spec=AgentResponseCache)
    age = timedelta(minutes=5) if within_ttl else timedelta(hours=3)
    cached = CachedResponse(
        response=response,
        cached_at=datetime.now(timezone.utc) - age,
        ttl_hours=1.0,
    )
    cache.get = AsyncMock(return_value=cached)
    cache.set = AsyncMock()
    return cache


def _call(agent_id: str = "cashflow_agent") -> AgentCall:
    return AgentCall(agent_id=agent_id, allowed_owner_ids=[uuid.uuid4()])


# ---------------------------------------------------------------------------
# _dispatch_one — live success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_success_returns_primary_tier():
    resp = _response()
    with patch(
        "services.orchestrator.dispatch._call_agent_http",
        new=AsyncMock(return_value=resp),
    ):
        result = await _dispatch_one(
            _call(), "query", _profile(), uuid.uuid4(),
            _registry_with(), _breaker(), _cache_miss(),
        )

    assert result.fallback_tier == FallbackTier.PRIMARY
    assert result.response is not None
    assert result.error is None


@pytest.mark.asyncio
async def test_live_success_caches_response():
    resp = _response()
    cache = _cache_miss()
    with patch(
        "services.orchestrator.dispatch._call_agent_http",
        new=AsyncMock(return_value=resp),
    ):
        await _dispatch_one(
            _call(), "query", _profile(), uuid.uuid4(),
            _registry_with(), _breaker(), cache,
        )

    cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_live_success_records_breaker_success():
    resp = _response()
    breaker = _breaker()
    with patch(
        "services.orchestrator.dispatch._call_agent_http",
        new=AsyncMock(return_value=resp),
    ):
        await _dispatch_one(
            _call(), "query", _profile(), uuid.uuid4(),
            _registry_with(), breaker, _cache_miss(),
        )

    assert breaker.get_state("cashflow_agent") == BreakerState.CLOSED


# ---------------------------------------------------------------------------
# _dispatch_one — live failure + cache fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_failure_cache_hit_secondary():
    resp = _response()
    cache = _cache_hit(resp, within_ttl=True)
    with patch(
        "services.orchestrator.dispatch._call_agent_http",
        new=AsyncMock(side_effect=Exception("timeout")),
    ):
        result = await _dispatch_one(
            _call(), "query", _profile(), uuid.uuid4(),
            _registry_with(), _breaker(), cache,
        )

    assert result.fallback_tier == FallbackTier.SECONDARY
    assert result.response is not None


@pytest.mark.asyncio
async def test_live_failure_stale_cache_tertiary():
    resp = _response()
    cache = _cache_hit(resp, within_ttl=False)
    with patch(
        "services.orchestrator.dispatch._call_agent_http",
        new=AsyncMock(side_effect=Exception("connection refused")),
    ):
        result = await _dispatch_one(
            _call(), "query", _profile(), uuid.uuid4(),
            _registry_with(), _breaker(), cache,
        )

    assert result.fallback_tier == FallbackTier.TERTIARY
    assert result.response is not None


@pytest.mark.asyncio
async def test_live_failure_no_cache_returns_failure():
    with patch(
        "services.orchestrator.dispatch._call_agent_http",
        new=AsyncMock(side_effect=Exception("unreachable")),
    ):
        result = await _dispatch_one(
            _call(), "query", _profile(), uuid.uuid4(),
            _registry_with(), _breaker(), _cache_miss(),
        )

    assert result.fallback_tier == FallbackTier.FAILURE
    assert result.response is None
    assert "unreachable" in result.error


@pytest.mark.asyncio
async def test_live_failure_records_breaker_failure():
    breaker = _breaker()
    with patch(
        "services.orchestrator.dispatch._call_agent_http",
        new=AsyncMock(side_effect=Exception("timeout")),
    ):
        await _dispatch_one(
            _call(), "query", _profile(), uuid.uuid4(),
            _registry_with(), breaker, _cache_miss(),
        )

    # One failure, threshold=3 → still CLOSED but failure_count=1
    assert breaker.get_state("cashflow_agent") == BreakerState.CLOSED


# ---------------------------------------------------------------------------
# _dispatch_one — breaker open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breaker_open_returns_failure_immediately():
    breaker = InMemoryBreakerStore(BreakerConfig(failure_threshold=1))
    breaker.record_failure("cashflow_agent")  # trip open
    assert breaker.get_state("cashflow_agent") == BreakerState.OPEN

    with patch("services.orchestrator.dispatch._call_agent_http") as mock_call:
        result = await _dispatch_one(
            _call(), "query", _profile(), uuid.uuid4(),
            _registry_with(), breaker, _cache_miss(),
        )
        mock_call.assert_not_called()  # no HTTP call made

    assert result.fallback_tier == FallbackTier.FAILURE
    assert "circuit breaker" in result.error


# ---------------------------------------------------------------------------
# _dispatch_one — agent not in registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_not_in_registry_returns_failure():
    result = await _dispatch_one(
        _call(), "query", _profile(), uuid.uuid4(),
        _empty_registry(), _breaker(), _cache_miss(),
    )

    assert result.fallback_tier == FallbackTier.FAILURE
    assert "registry" in result.error


# ---------------------------------------------------------------------------
# dispatch_plan — full plan execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_plan_all_parallel():
    resp_cashflow = _response("cashflow_agent")
    resp_investment = _response("investment_agent")

    call_counts: dict[str, int] = {}

    async def fake_http(endpoint, request, timeout_ms):
        agent_id = endpoint.split("//")[1].split(":")[0] + "_agent"
        call_counts[agent_id] = call_counts.get(agent_id, 0) + 1
        if "cashflow" in endpoint:
            return resp_cashflow
        return resp_investment

    registry = MagicMock(spec=AgentRegistryCache)

    def get_agent(agent_id):
        from libs.schemas.db_models import AgentRegistryEntry
        e = AgentRegistryEntry()
        e.agent_id = agent_id
        e.endpoint = f"http://{agent_id.replace('_agent', '')}:8001"
        e.timeout_ms = 5000
        e.cache_ttl_hours = 1.0
        return e

    registry.get_agent.side_effect = get_agent

    plan = Plan(
        original_query="Should I increase SIP?",
        steps=[
            AgentCall("cashflow_agent", [uuid.uuid4()]),
            AgentCall("investment_agent", [uuid.uuid4()]),
        ],
    )

    with patch("services.orchestrator.dispatch._call_agent_http", new=AsyncMock(side_effect=fake_http)):
        results = await dispatch_plan(plan, _profile(), registry, _breaker(), _cache_miss())

    assert len(results) == 2
    agent_ids = {r.agent_id for r in results}
    assert agent_ids == {"cashflow_agent", "investment_agent"}
    assert all(r.fallback_tier == FallbackTier.PRIMARY for r in results)


@pytest.mark.asyncio
async def test_dispatch_plan_empty_steps():
    plan = Plan(original_query="test", steps=[])
    results = await dispatch_plan(
        plan, _profile(), _empty_registry(), _breaker(), _cache_miss()
    )
    assert results == []


@pytest.mark.asyncio
async def test_dispatch_plan_partial_failure():
    """One agent succeeds, one fails with no cache → mixed tiers."""
    def get_agent(agent_id):
        from libs.schemas.db_models import AgentRegistryEntry
        e = AgentRegistryEntry()
        e.agent_id = agent_id
        e.endpoint = f"http://{agent_id}:8001"
        e.timeout_ms = 5000
        e.cache_ttl_hours = 1.0
        return e

    registry = MagicMock(spec=AgentRegistryCache)
    registry.get_agent.side_effect = get_agent

    async def fake_http(endpoint, request, timeout_ms):
        if "cashflow" in endpoint:
            return _response("cashflow_agent")
        raise Exception("tax agent down")

    plan = Plan(
        original_query="spending and tax",
        steps=[
            AgentCall("cashflow_agent", [uuid.uuid4()]),
            AgentCall("tax_agent", [uuid.uuid4()]),
        ],
    )

    with patch("services.orchestrator.dispatch._call_agent_http", new=AsyncMock(side_effect=fake_http)):
        results = await dispatch_plan(plan, _profile(), registry, _breaker(), _cache_miss())

    tier_map = {r.agent_id: r.fallback_tier for r in results}
    assert tier_map["cashflow_agent"] == FallbackTier.PRIMARY
    assert tier_map["tax_agent"] == FallbackTier.FAILURE
