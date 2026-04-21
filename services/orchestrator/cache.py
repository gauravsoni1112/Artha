"""
Redis-backed agent response cache (Phase 5).

Stores the last successful AgentResponse per (agent_id, query, owner).
Used by the Planner dispatch layer to serve SECONDARY / TERTIARY fallback
responses when a live agent call fails.

Key format:  artha:agent:{agent_id}:{sha256(agent_id:query:owner_id)[:16]}
Value:       JSON {"response": {...}, "cached_at": ISO8601, "ttl_hours": N}
Redis TTL:   cache_ttl_hours × 2 (so stale data persists for TERTIARY fallback)

Tiers returned by CachedResponse.tier():
  SECONDARY — age ≤ cache_ttl_hours   (cache is fresh)
  TERTIARY  — age > cache_ttl_hours   (cache is stale, still usable with penalty)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import redis.asyncio as aioredis

from libs.confidence.tier import FallbackTier
from libs.schemas.agent_envelope import AgentRequest, AgentResponse

_KEY_PREFIX = "artha:agent"


def _cache_key(agent_id: str, request: AgentRequest) -> str:
    # Sort allowed_owner_ids so key is stable regardless of insertion order.
    # allowed_owner_ids is injected into context by the dispatch layer.
    raw_ids = request.context.get("allowed_owner_ids") or []
    scope_str = ",".join(sorted(str(oid) for oid in raw_ids))
    content = f"{agent_id}:{request.query}:{request.user_profile.owner_id}:{scope_str}"
    digest = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"{_KEY_PREFIX}:{agent_id}:{digest}"


@dataclass
class CachedResponse:
    response: AgentResponse
    cached_at: datetime
    ttl_hours: float

    def tier(self) -> FallbackTier:
        age_hours = (datetime.now(timezone.utc) - self.cached_at).total_seconds() / 3600
        return FallbackTier.SECONDARY if age_hours <= self.ttl_hours else FallbackTier.TERTIARY


class AgentResponseCache:
    """
    Async Redis cache for AgentResponse objects.

    Inject a redis.asyncio.Redis client.  For tests, pass a fakeredis or
    mock client.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def get(self, agent_id: str, request: AgentRequest) -> CachedResponse | None:
        """Return cached response or None on miss."""
        raw = await self._redis.get(_cache_key(agent_id, request))
        if raw is None:
            return None
        data = json.loads(raw)
        return CachedResponse(
            response=AgentResponse.model_validate(data["response"]),
            cached_at=datetime.fromisoformat(data["cached_at"]),
            ttl_hours=data["ttl_hours"],
        )

    async def set(
        self,
        agent_id: str,
        request: AgentRequest,
        response: AgentResponse,
        ttl_hours: float,
    ) -> None:
        """
        Cache a successful response.
        Redis key expires after 2× ttl_hours so stale data remains
        accessible for TERTIARY fallback.
        """
        key = _cache_key(agent_id, request)
        payload = {
            "response": response.model_dump(mode="json"),
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "ttl_hours": ttl_hours,
        }
        redis_ttl_seconds = max(1, int(ttl_hours * 2 * 3600))
        await self._redis.set(key, json.dumps(payload), ex=redis_ttl_seconds)

    async def invalidate(self, agent_id: str, request: AgentRequest) -> None:
        """Remove a cached entry (e.g. after a known data refresh)."""
        await self._redis.delete(_cache_key(agent_id, request))
