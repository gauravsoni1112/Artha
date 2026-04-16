"""Unit tests for the per-agent circuit breaker (Phase 5)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services.orchestrator.breaker import (
    BreakerConfig,
    BreakerState,
    InMemoryBreakerStore,
)


def _store(
    failure_threshold: int = 3,
    open_duration_seconds: float = 30.0,
    half_open_probe_count: int = 1,
) -> InMemoryBreakerStore:
    return InMemoryBreakerStore(
        BreakerConfig(
            failure_threshold=failure_threshold,
            open_duration_seconds=open_duration_seconds,
            half_open_probe_count=half_open_probe_count,
        )
    )


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


def test_new_agent_starts_closed():
    store = _store()
    assert store.get_state("cashflow") == BreakerState.CLOSED


def test_call_permitted_when_closed():
    assert _store().is_call_permitted("cashflow")


# ---------------------------------------------------------------------------
# CLOSED → OPEN on threshold
# ---------------------------------------------------------------------------


def test_single_failure_stays_closed():
    store = _store(failure_threshold=3)
    store.record_failure("cashflow")
    assert store.get_state("cashflow") == BreakerState.CLOSED


def test_failures_below_threshold_stay_closed():
    store = _store(failure_threshold=3)
    store.record_failure("cashflow")
    store.record_failure("cashflow")
    assert store.get_state("cashflow") == BreakerState.CLOSED


def test_failures_at_threshold_open_breaker():
    store = _store(failure_threshold=3)
    for _ in range(3):
        store.record_failure("cashflow")
    assert store.get_state("cashflow") == BreakerState.OPEN


def test_call_not_permitted_when_open():
    store = _store(failure_threshold=1)
    store.record_failure("cashflow")
    assert not store.is_call_permitted("cashflow")


# ---------------------------------------------------------------------------
# Success resets failure counter in CLOSED
# ---------------------------------------------------------------------------


def test_success_resets_failure_count():
    store = _store(failure_threshold=3)
    store.record_failure("cashflow")
    store.record_failure("cashflow")
    store.record_success("cashflow")  # reset
    store.record_failure("cashflow")
    store.record_failure("cashflow")
    # Only 2 failures since last success — still closed
    assert store.get_state("cashflow") == BreakerState.CLOSED


# ---------------------------------------------------------------------------
# OPEN → HALF_OPEN after open_duration
# ---------------------------------------------------------------------------


def test_open_transitions_to_half_open_after_duration():
    store = _store(failure_threshold=1, open_duration_seconds=10.0)
    store.record_failure("cashflow")
    assert store.get_state("cashflow") == BreakerState.OPEN

    future = datetime.now(timezone.utc) + timedelta(seconds=11)
    with patch("services.orchestrator.breaker.datetime") as mock_dt:
        mock_dt.now.return_value = future
        permitted = store.is_call_permitted("cashflow")

    assert permitted
    assert store.get_state("cashflow") == BreakerState.HALF_OPEN


def test_open_stays_open_before_duration():
    store = _store(failure_threshold=1, open_duration_seconds=30.0)
    store.record_failure("cashflow")

    future = datetime.now(timezone.utc) + timedelta(seconds=10)
    with patch("services.orchestrator.breaker.datetime") as mock_dt:
        mock_dt.now.return_value = future
        permitted = store.is_call_permitted("cashflow")

    assert not permitted
    assert store.get_state("cashflow") == BreakerState.OPEN


# ---------------------------------------------------------------------------
# HALF_OPEN → CLOSED on probe success
# ---------------------------------------------------------------------------


def _open_then_half_open(store: InMemoryBreakerStore, agent_id: str) -> None:
    """Helper: trip the breaker open, then advance time past open_duration."""
    store.record_failure(agent_id)
    future = datetime.now(timezone.utc) + timedelta(seconds=31)
    with patch("services.orchestrator.breaker.datetime") as mock_dt:
        mock_dt.now.return_value = future
        store.is_call_permitted(agent_id)  # triggers OPEN → HALF_OPEN


def test_half_open_success_closes_breaker():
    store = _store(failure_threshold=1, open_duration_seconds=30.0, half_open_probe_count=1)
    _open_then_half_open(store, "cashflow")
    assert store.get_state("cashflow") == BreakerState.HALF_OPEN

    store.record_success("cashflow")
    assert store.get_state("cashflow") == BreakerState.CLOSED


def test_half_open_failure_reopens():
    store = _store(failure_threshold=1, open_duration_seconds=30.0)
    _open_then_half_open(store, "cashflow")

    store.record_failure("cashflow")
    assert store.get_state("cashflow") == BreakerState.OPEN


def test_half_open_probe_count_respected():
    store = _store(failure_threshold=1, open_duration_seconds=30.0, half_open_probe_count=2)
    _open_then_half_open(store, "cashflow")

    store.record_success("cashflow")
    assert store.get_state("cashflow") == BreakerState.HALF_OPEN  # still needs 1 more

    store.record_success("cashflow")
    assert store.get_state("cashflow") == BreakerState.CLOSED


# ---------------------------------------------------------------------------
# Isolation between agents
# ---------------------------------------------------------------------------


def test_breaker_states_isolated_per_agent():
    store = _store(failure_threshold=1)
    store.record_failure("cashflow")
    assert store.get_state("cashflow") == BreakerState.OPEN
    assert store.get_state("investment") == BreakerState.CLOSED


def test_reset_force_closes():
    store = _store(failure_threshold=1)
    store.record_failure("cashflow")
    assert store.get_state("cashflow") == BreakerState.OPEN

    store.reset("cashflow")
    assert store.get_state("cashflow") == BreakerState.CLOSED
    assert store.is_call_permitted("cashflow")


# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------


def test_default_config_used_when_none_provided():
    store = InMemoryBreakerStore()
    # Default failure_threshold is 5
    for _ in range(4):
        store.record_failure("tax")
    assert store.get_state("tax") == BreakerState.CLOSED

    store.record_failure("tax")
    assert store.get_state("tax") == BreakerState.OPEN
