"""
Planner dispatch layer (Phase 5).

dispatch_plan() executes a Plan against live domain agents.

Per-step flow:
  1. Breaker check — if OPEN, return FAILURE immediately (no network call).
  2. Registry lookup — find endpoint + timeout for the agent.
  3. Live HTTP call to {endpoint}/run (httpx, timeout from registry).
     - Success → PRIMARY tier; record_success; cache response.
     - Failure → record_failure; try cache fallback.
  4. Cache fallback:
     - SECONDARY if within agent's cache_ttl_hours
     - TERTIARY  if stale (past TTL but Redis key still present)
     - FAILURE   if no cached entry exists

Parallel steps (depends_on=[]) are gathered concurrently.
Sequential steps (depends_on set) run after all parallel steps complete.

The caller (Planner / audit writer) receives list[DispatchedResult] and passes
them to compose() (confidence) and the Critic before writing to the audit log.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field

import httpx
import structlog

from libs.confidence.tier import FallbackTier
from libs.schemas.agent_envelope import AgentRequest, AgentResponse
from libs.schemas.user_profile import UserProfile
from services.orchestrator.breaker import BreakerStore, InMemoryBreakerStore
from services.orchestrator.cache import AgentResponseCache
from services.orchestrator.plan import AgentCall, Plan
from services.orchestrator.registry import AgentRegistryCache

log = structlog.get_logger(__name__)

_AGENT_SECRET: str = os.getenv("ARTHA_AGENT_SECRET", "dev-agent-secret-change-me")

# Module-level AsyncClient — reuses TCP connections across all agent dispatches
# in a single orchestrator request instead of opening a new connection per call.
# Timeout is set per-request via httpx.Timeout, so this client has no global timeout.
_http_client: httpx.AsyncClient = httpx.AsyncClient(timeout=None)


@dataclass
class DispatchedResult:
    """Outcome of dispatching one AgentCall."""

    agent_id: str
    response: AgentResponse | None      # None iff fallback_tier is FAILURE
    fallback_tier: FallbackTier
    error: str | None = None            # set on FAILURE for debugging


async def _call_agent_http(
    endpoint: str,
    request: AgentRequest,
    timeout_ms: int,
) -> AgentResponse:
    """Make a single HTTP call to an agent's /run endpoint.

    Uses the module-level AsyncClient to reuse TCP connections across calls.
    """
    resp = await _http_client.post(
        f"{endpoint}/run",
        json=request.model_dump(mode="json"),
        headers={"X-Artha-Agent-Secret": _AGENT_SECRET},
        timeout=httpx.Timeout(timeout_ms / 1000.0),
    )
    resp.raise_for_status()
    return AgentResponse.model_validate(resp.json())


async def _dispatch_one(
    call: AgentCall,
    query: str,
    user_profile: UserProfile,
    trace_id: uuid.UUID,
    registry: AgentRegistryCache,
    breaker_store: BreakerStore,
    response_cache: AgentResponseCache,
) -> DispatchedResult:
    agent_id = call.agent_id

    # 1. Breaker check
    if not breaker_store.is_call_permitted(agent_id):
        log.warning("dispatch.breaker_open", agent_id=agent_id)
        return DispatchedResult(
            agent_id=agent_id,
            response=None,
            fallback_tier=FallbackTier.FAILURE,
            error="circuit breaker open",
        )

    # 2. Registry lookup
    entry = registry.get_agent(agent_id)
    if entry is None:
        log.warning("dispatch.agent_not_in_registry", agent_id=agent_id)
        return DispatchedResult(
            agent_id=agent_id,
            response=None,
            fallback_tier=FallbackTier.FAILURE,
            error="agent not found in registry",
        )

    # Build request envelope — inject scope via context
    agent_request = AgentRequest(
        query=query,
        context={
            **call.context,
            "allowed_owner_ids": [str(oid) for oid in call.allowed_owner_ids],
        },
        user_profile=user_profile,
        trace_id=trace_id,
    )

    # 3. Live call
    try:
        response = await _call_agent_http(
            entry.endpoint, agent_request, entry.timeout_ms
        )
        breaker_store.record_success(agent_id)
        await response_cache.set(
            agent_id, agent_request, response, float(entry.cache_ttl_hours)
        )
        log.info("dispatch.live_success", agent_id=agent_id, confidence=response.confidence)
        return DispatchedResult(
            agent_id=agent_id,
            response=response,
            fallback_tier=FallbackTier.PRIMARY,
        )

    except Exception as exc:
        breaker_store.record_failure(agent_id)
        log.warning("dispatch.live_failure", agent_id=agent_id, error=str(exc))

        # 4. Cache fallback
        cached = await response_cache.get(agent_id, agent_request)
        if cached is not None:
            tier = cached.tier()
            log.info("dispatch.cache_fallback", agent_id=agent_id, tier=tier)
            return DispatchedResult(
                agent_id=agent_id,
                response=cached.response,
                fallback_tier=tier,
            )

        return DispatchedResult(
            agent_id=agent_id,
            response=None,
            fallback_tier=FallbackTier.FAILURE,
            error=str(exc),
        )


async def dispatch_plan(
    plan: Plan,
    user_profile: UserProfile,
    registry: AgentRegistryCache,
    breaker_store: BreakerStore,
    response_cache: AgentResponseCache,
    trace_id: uuid.UUID | None = None,
) -> list[DispatchedResult]:
    """
    Execute all steps in the Plan and return one DispatchedResult per step.

    Parallel steps (depends_on=[]) are gathered concurrently via asyncio.gather.
    Sequential steps run after all parallel steps have completed.

    Result order mirrors plan.steps order.
    """
    trace_id = trace_id or uuid.uuid4()

    parallel_calls = plan.parallel_steps()
    sequential_calls = plan.sequential_steps()

    results: list[DispatchedResult] = []

    # Parallel
    if parallel_calls:
        parallel_results = await asyncio.gather(
            *[
                _dispatch_one(
                    call, plan.original_query, user_profile,
                    trace_id, registry, breaker_store, response_cache,
                )
                for call in parallel_calls
            ]
        )
        results.extend(parallel_results)

    # Sequential (ordered by depends_on — Phase 5 has no sequential steps,
    # but the infrastructure is wired for Phase 6+)
    for call in sequential_calls:
        result = await _dispatch_one(
            call, plan.original_query, user_profile,
            trace_id, registry, breaker_store, response_cache,
        )
        results.append(result)

    log.info(
        "dispatch.plan_complete",
        plan_id=str(plan.plan_id),
        total=len(results),
        primary=sum(1 for r in results if r.fallback_tier == FallbackTier.PRIMARY),
        failure=sum(1 for r in results if r.fallback_tier == FallbackTier.FAILURE),
    )
    return results
