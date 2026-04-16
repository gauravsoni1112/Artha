"""Unit tests for AgentResponseCache."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from libs.confidence.tier import FallbackTier
from libs.schemas.agent_envelope import AgentRequest, AgentResponse, DataTier, RiskLevel
from libs.schemas.user_profile import UserProfile
from services.orchestrator.cache import AgentResponseCache, CachedResponse, _cache_key


def _profile() -> UserProfile:
    return UserProfile(owner_id=uuid.uuid4(), name="Rahul")


def _request(query: str = "test query", profile: UserProfile | None = None) -> AgentRequest:
    return AgentRequest(
        query=query,
        user_profile=profile or _profile(),
    )


def _response(agent_id: str = "cashflow_agent") -> AgentResponse:
    return AgentResponse(
        agent_id=agent_id,
        trace_id=uuid.uuid4(),
        data_tier=DataTier.REALTIME,
        data_freshness_hours=0.1,
        result={"surplus_paise": 1_800_000},
        confidence=0.85,
        risk_level=RiskLevel.LOW,
        reasoning="Surplus is positive",
    )


def _mock_redis() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# _cache_key
# ---------------------------------------------------------------------------


def test_cache_key_format():
    req = _request()
    key = _cache_key("cashflow_agent", req)
    assert key.startswith("artha:agent:cashflow_agent:")
    assert len(key.split(":")) == 4


def test_same_inputs_produce_same_key():
    profile = _profile()
    r1 = _request("how much did I spend?", profile)
    r2 = _request("how much did I spend?", profile)
    assert _cache_key("cashflow_agent", r1) == _cache_key("cashflow_agent", r2)


def test_different_queries_produce_different_keys():
    profile = _profile()
    r1 = _request("spending", profile)
    r2 = _request("portfolio", profile)
    assert _cache_key("cashflow_agent", r1) != _cache_key("cashflow_agent", r2)


def test_different_agent_ids_produce_different_keys():
    req = _request()
    assert _cache_key("cashflow_agent", req) != _cache_key("tax_agent", req)


# ---------------------------------------------------------------------------
# CachedResponse.tier()
# ---------------------------------------------------------------------------


def test_within_ttl_returns_secondary():
    cached = CachedResponse(
        response=_response(),
        cached_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        ttl_hours=1.0,
    )
    assert cached.tier() == FallbackTier.SECONDARY


def test_past_ttl_returns_tertiary():
    cached = CachedResponse(
        response=_response(),
        cached_at=datetime.now(timezone.utc) - timedelta(hours=2),
        ttl_hours=1.0,
    )
    assert cached.tier() == FallbackTier.TERTIARY


def test_just_under_ttl_boundary_is_secondary():
    # 59m55s old, TTL=1h → still SECONDARY
    cached = CachedResponse(
        response=_response(),
        cached_at=datetime.now(timezone.utc) - timedelta(minutes=59, seconds=55),
        ttl_hours=1.0,
    )
    assert cached.tier() == FallbackTier.SECONDARY


# ---------------------------------------------------------------------------
# AgentResponseCache.get()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_none_on_miss():
    redis = _mock_redis()
    redis.get = AsyncMock(return_value=None)
    cache = AgentResponseCache(redis)

    result = await cache.get("cashflow_agent", _request())
    assert result is None


@pytest.mark.asyncio
async def test_get_returns_cached_response():
    resp = _response()
    payload = {
        "response": resp.model_dump(mode="json"),
        "cached_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "ttl_hours": 1.0,
    }
    redis = _mock_redis()
    redis.get = AsyncMock(return_value=json.dumps(payload))
    cache = AgentResponseCache(redis)

    result = await cache.get("cashflow_agent", _request())
    assert result is not None
    assert result.response.agent_id == "cashflow_agent"
    assert result.ttl_hours == 1.0
    assert result.tier() == FallbackTier.SECONDARY


# ---------------------------------------------------------------------------
# AgentResponseCache.set()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_calls_redis_with_correct_ttl():
    redis = _mock_redis()
    redis.set = AsyncMock()
    cache = AgentResponseCache(redis)

    req = _request()
    resp = _response()
    await cache.set("cashflow_agent", req, resp, ttl_hours=1.0)

    redis.set.assert_called_once()
    # ex= is passed as a keyword argument
    assert redis.set.call_args.kwargs["ex"] == 7200  # 2 × 1h × 3600s


@pytest.mark.asyncio
async def test_set_then_get_round_trip():
    """Full round-trip using a simple dict as fake Redis storage."""
    store: dict = {}

    redis = _mock_redis()

    async def fake_set(key, value, ex=None):
        store[key] = value

    async def fake_get(key):
        return store.get(key)

    redis.set = fake_set
    redis.get = fake_get

    cache = AgentResponseCache(redis)
    req = _request(profile=_profile())
    resp = _response()

    await cache.set("cashflow_agent", req, resp, ttl_hours=2.0)
    result = await cache.get("cashflow_agent", req)

    assert result is not None
    assert result.response.agent_id == "cashflow_agent"
    assert result.ttl_hours == 2.0


# ---------------------------------------------------------------------------
# AgentResponseCache.invalidate()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_calls_redis_delete():
    redis = _mock_redis()
    redis.delete = AsyncMock()
    cache = AgentResponseCache(redis)

    req = _request()
    await cache.invalidate("cashflow_agent", req)

    redis.delete.assert_called_once_with(_cache_key("cashflow_agent", req))
