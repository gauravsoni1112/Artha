"""
Per-agent circuit breaker (Phase 5).

State machine per agent:
  CLOSED    — normal operation; failures increment counter
  OPEN      — fail fast; no calls made; returns FAILURE tier
  HALF_OPEN — one probe allowed; success → CLOSED, failure → OPEN

States are tracked in a BreakerStore. InMemoryBreakerStore is the default;
swap to a Redis-backed implementation for multi-instance deployments without
changing any call sites.

Usage:
    store = InMemoryBreakerStore()
    if store.is_call_permitted("cashflow_agent"):
        try:
            result = await call_agent(...)
            store.record_success("cashflow_agent")
        except Exception:
            store.record_failure("cashflow_agent")
    else:
        # circuit open — return FAILURE tier
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol

from services.orchestrator.metrics import record_breaker_transition


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------


class BreakerState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BreakerConfig:
    failure_threshold: int = 5             # consecutive failures to trip OPEN
    open_duration_seconds: float = 30.0    # time to stay OPEN before probing
    half_open_probe_count: int = 1         # consecutive successes needed to re-CLOSE


# ---------------------------------------------------------------------------
# Protocol — swap implementation without changing call sites
# ---------------------------------------------------------------------------


class BreakerStore(Protocol):
    def get_state(self, agent_id: str) -> BreakerState:
        """Return the current breaker state for this agent."""
        ...

    def is_call_permitted(self, agent_id: str) -> bool:
        """
        True if a call to this agent should proceed.
        Transitions OPEN → HALF_OPEN when open_duration has elapsed.
        """
        ...

    def record_success(self, agent_id: str) -> None:
        """Record a successful agent call. May transition HALF_OPEN → CLOSED."""
        ...

    def record_failure(self, agent_id: str) -> None:
        """Record a failed agent call. May transition CLOSED/HALF_OPEN → OPEN."""
        ...

    def reset(self, agent_id: str) -> None:
        """Force-reset to CLOSED (e.g. after a manual health check)."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


@dataclass
class _AgentBreakerState:
    state: BreakerState = BreakerState.CLOSED
    failure_count: int = 0
    half_open_successes: int = 0
    opened_at: datetime | None = None


class InMemoryBreakerStore:
    """
    Thread-safe in-memory circuit breaker store.

    All state is local to this process. For multi-instance deployments,
    replace with a Redis-backed store that implements the same BreakerStore
    protocol.
    """

    def __init__(self, config: BreakerConfig | None = None) -> None:
        self._config = config or BreakerConfig()
        self._agents: dict[str, _AgentBreakerState] = {}
        self._lock = threading.Lock()

    def _get_or_create(self, agent_id: str) -> _AgentBreakerState:
        if agent_id not in self._agents:
            self._agents[agent_id] = _AgentBreakerState()
        return self._agents[agent_id]

    def get_state(self, agent_id: str) -> BreakerState:
        with self._lock:
            return self._get_or_create(agent_id).state

    def is_call_permitted(self, agent_id: str) -> bool:
        """
        Returns True if a call should proceed.

        Side effect: transitions OPEN → HALF_OPEN if open_duration has elapsed.
        """
        with self._lock:
            entry = self._get_or_create(agent_id)

            if entry.state == BreakerState.CLOSED:
                return True

            if entry.state == BreakerState.OPEN:
                if entry.opened_at is None:
                    return False
                elapsed = (datetime.now(timezone.utc) - entry.opened_at).total_seconds()
                if elapsed >= self._config.open_duration_seconds:
                    entry.state = BreakerState.HALF_OPEN
                    entry.half_open_successes = 0
                    record_breaker_transition(agent_id, "OPEN", "HALF_OPEN")
                    return True  # allow the probe
                return False

            # HALF_OPEN — only one probe at a time; deny further until resolved
            return entry.half_open_successes == 0

    def record_success(self, agent_id: str) -> None:
        with self._lock:
            entry = self._get_or_create(agent_id)

            if entry.state == BreakerState.HALF_OPEN:
                entry.half_open_successes += 1
                if entry.half_open_successes >= self._config.half_open_probe_count:
                    entry.state = BreakerState.CLOSED
                    entry.failure_count = 0
                    entry.opened_at = None
                    entry.half_open_successes = 0
                    record_breaker_transition(agent_id, "HALF_OPEN", "CLOSED")
            elif entry.state == BreakerState.CLOSED:
                entry.failure_count = 0  # reset on any success

    def record_failure(self, agent_id: str) -> None:
        with self._lock:
            entry = self._get_or_create(agent_id)

            if entry.state == BreakerState.HALF_OPEN:
                # Probe failed — go back to OPEN
                entry.state = BreakerState.OPEN
                entry.opened_at = datetime.now(timezone.utc)
                entry.half_open_successes = 0
                record_breaker_transition(agent_id, "HALF_OPEN", "OPEN")
                return

            if entry.state == BreakerState.CLOSED:
                entry.failure_count += 1
                if entry.failure_count >= self._config.failure_threshold:
                    entry.state = BreakerState.OPEN
                    entry.opened_at = datetime.now(timezone.utc)
                    record_breaker_transition(agent_id, "CLOSED", "OPEN")

    def reset(self, agent_id: str) -> None:
        with self._lock:
            self._agents[agent_id] = _AgentBreakerState()
