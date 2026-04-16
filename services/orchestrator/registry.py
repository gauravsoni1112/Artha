"""
In-memory agent registry cache (Phase 5).

The Planner reads from this cache — never directly from the DB on each request.
A background APScheduler job calls refresh() every 60 seconds.

Usage:
    registry = AgentRegistryCache(session_factory)
    await registry.refresh()                        # initial load
    schedule_registry_refresh(scheduler, registry)  # keep it warm

    entry = registry.get_agent("cashflow_agent")
    available = registry.list_available()           # → list[RegisteredAgent]
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from libs.schemas.db_models import AgentRegistryEntry
from services.orchestrator.decompose import RegisteredAgent

log = structlog.get_logger(__name__)


class AgentRegistryCache:
    """
    Thread-safe in-memory snapshot of the agent_registry table.

    Only HEALTHY and DEGRADED agents are loaded; DOWN agents are excluded.
    list_available() returns only HEALTHY agents for dispatch planning.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory
        self._agents: dict[str, AgentRegistryEntry] = {}
        self._lock = asyncio.Lock()
        self._last_refreshed: datetime | None = None

    async def refresh(self) -> int:
        """
        Reload agent registry from the database.
        Returns the number of agents loaded.
        Called on startup and every 60 s by APScheduler.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentRegistryEntry).where(
                    AgentRegistryEntry.status != "DOWN"
                )
            )
            entries = list(result.scalars().all())

        async with self._lock:
            self._agents = {e.agent_id: e for e in entries}
            self._last_refreshed = datetime.now(timezone.utc)

        log.info("registry.refreshed", count=len(self._agents))
        return len(self._agents)

    def get_agent(self, agent_id: str) -> AgentRegistryEntry | None:
        return self._agents.get(agent_id)

    def list_available(self) -> list[RegisteredAgent]:
        """Return HEALTHY agents as RegisteredAgent projections for the decomposer."""
        return [
            RegisteredAgent(
                agent_id=entry.agent_id,
                capabilities=entry.capabilities,
            )
            for entry in self._agents.values()
            if entry.status == "HEALTHY"
        ]

    @property
    def last_refreshed(self) -> datetime | None:
        return self._last_refreshed

    @property
    def agent_count(self) -> int:
        return len(self._agents)


def schedule_registry_refresh(
    scheduler: AsyncIOScheduler,
    registry: AgentRegistryCache,
    interval_seconds: int = 60,
) -> None:
    """
    Register a recurring interval job to refresh the registry cache.
    Idempotent — replace_existing=True ensures only one job is registered
    even if called multiple times (e.g. during testing or hot-reload).
    """
    scheduler.add_job(
        registry.refresh,
        "interval",
        seconds=interval_seconds,
        id="registry_refresh",
        replace_existing=True,
    )
    log.info("registry.refresh_scheduled", interval_seconds=interval_seconds)
