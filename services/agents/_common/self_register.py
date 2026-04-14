"""
Agent self-registration client.

Called once on FastAPI startup. POSTs an AgentRegistration payload to the
registry service. Retries with exponential backoff so agents can start
before the registry is ready (common in Docker Compose bring-up).

Required env vars (set per-agent in docker-compose.yml):
  AGENT_ID           e.g. cashflow_agent
  AGENT_ENDPOINT     e.g. http://cashflow_agent:8001
  REGISTRY_URL       e.g. http://registry:8000  (or api service host)
  AGENT_CAPABILITIES e.g. cashflow,spending,budget  (comma-separated)

Optional:
  AGENT_TIMEOUT_MS          default 10000
  AGENT_FALLBACK_STRATEGY   default cached_response
  AGENT_CACHE_TTL_HOURS     default 1.0
  AGENT_SCOPE               default individual
  AGENT_SCHEMA_VERSION      default 1.0
"""

from __future__ import annotations

import asyncio
import os

import httpx
import structlog

log = structlog.get_logger(__name__)

_MAX_RETRIES = 8
_BASE_DELAY = 1.0   # seconds; doubles each attempt, capped at 30s


async def self_register() -> None:
    """Register this agent with the registry. Called from FastAPI lifespan."""
    agent_id = _require_env("AGENT_ID")
    endpoint = _require_env("AGENT_ENDPOINT")
    registry_url = _require_env("REGISTRY_URL")
    raw_caps = _require_env("AGENT_CAPABILITIES")

    payload = {
        "agent_id": agent_id,
        "capabilities": [c.strip() for c in raw_caps.split(",") if c.strip()],
        "schema_version": os.getenv("AGENT_SCHEMA_VERSION", "1.0"),
        "endpoint": endpoint,
        "health_endpoint": f"{endpoint.rstrip('/')}/health",
        "timeout_ms": int(os.getenv("AGENT_TIMEOUT_MS", "10000")),
        "fallback_strategy": os.getenv("AGENT_FALLBACK_STRATEGY", "cached_response"),
        "cache_ttl_hours": float(os.getenv("AGENT_CACHE_TTL_HOURS", "1.0")),
        "scope": os.getenv("AGENT_SCOPE", "individual"),
    }

    register_url = f"{registry_url.rstrip('/')}/registry/agents"

    async with httpx.AsyncClient(timeout=10.0) as client:
        delay = _BASE_DELAY
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await client.put(register_url, json=payload)
                resp.raise_for_status()
                log.info(
                    "agent.registered",
                    agent_id=agent_id,
                    endpoint=endpoint,
                    capabilities=payload["capabilities"],
                )
                return
            except (httpx.HTTPError, httpx.ConnectError) as exc:
                if attempt == _MAX_RETRIES:
                    log.error(
                        "agent.registration_failed",
                        agent_id=agent_id,
                        attempts=attempt,
                        error=str(exc),
                    )
                    raise RuntimeError(
                        f"Agent {agent_id!r} failed to register after {_MAX_RETRIES} attempts"
                    ) from exc
                log.warning(
                    "agent.registration_retry",
                    agent_id=agent_id,
                    attempt=attempt,
                    delay_s=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)


def _require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Required env var {key!r} is not set")
    return val
