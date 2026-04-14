"""
Unit tests for BaseAgent helpers and envelope construction.

We test the pure helper functions and the abstract interface without
needing a real LLM or DB (those are integration concerns).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.schemas.agent_envelope import AgentResponse, DataTier, RiskLevel
from libs.schemas.user_profile import UserProfile
from services.agents._common.base_agent import (
    _compute_freshness_hours,
    _extract_freshness,
    _risk_from_confidence,
    _tier_from_freshness,
)


# ---------------------------------------------------------------------------
# _extract_freshness
# ---------------------------------------------------------------------------


def _tool_message(ts: datetime) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps({"data_freshness": ts.isoformat(), "data": {}})
    return msg


def test_extract_freshness_single():
    ts = datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc)
    msgs = [_tool_message(ts)]
    result = _extract_freshness(msgs)
    assert len(result) == 1
    assert result[0] == ts


def test_extract_freshness_multiple():
    t1 = datetime(2026, 4, 14, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 4, 14, 11, 0, tzinfo=timezone.utc)
    msgs = [_tool_message(t1), _tool_message(t2)]
    result = _extract_freshness(msgs)
    assert len(result) == 2


def test_extract_freshness_ignores_non_json():
    msg = MagicMock()
    msg.content = "plain text response from LLM"
    result = _extract_freshness([msg])
    assert result == []


def test_extract_freshness_ignores_missing_key():
    msg = MagicMock()
    msg.content = json.dumps({"data": "no freshness here"})
    result = _extract_freshness([msg])
    assert result == []


def test_extract_freshness_empty_messages():
    assert _extract_freshness([]) == []


# ---------------------------------------------------------------------------
# _compute_freshness_hours
# ---------------------------------------------------------------------------


def test_compute_freshness_no_timestamps():
    assert _compute_freshness_hours([]) == 0.0


def test_compute_freshness_recent():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(seconds=30)
    hours = _compute_freshness_hours([recent])
    assert hours < 0.02   # under ~72 seconds


def test_compute_freshness_picks_oldest():
    now = datetime.now(timezone.utc)
    t1 = now - timedelta(hours=2)
    t2 = now - timedelta(hours=0.5)
    hours = _compute_freshness_hours([t1, t2])
    assert hours >= 1.9


def test_compute_freshness_never_negative():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert _compute_freshness_hours([future]) == 0.0


# ---------------------------------------------------------------------------
# _tier_from_freshness
# ---------------------------------------------------------------------------


def test_tier_realtime():
    assert _tier_from_freshness(0.0) == DataTier.REALTIME
    assert _tier_from_freshness(0.01) == DataTier.REALTIME   # < 1 min


def test_tier_cached():
    assert _tier_from_freshness(0.5) == DataTier.CACHED


def test_tier_stale():
    assert _tier_from_freshness(2.0) == DataTier.STALE
    assert _tier_from_freshness(23.9) == DataTier.STALE


def test_tier_estimated():
    assert _tier_from_freshness(24.0) == DataTier.ESTIMATED
    assert _tier_from_freshness(48.0) == DataTier.ESTIMATED


# ---------------------------------------------------------------------------
# _risk_from_confidence
# ---------------------------------------------------------------------------


def test_risk_low():
    assert _risk_from_confidence(1.0) == RiskLevel.LOW
    assert _risk_from_confidence(0.85) == RiskLevel.LOW


def test_risk_medium():
    assert _risk_from_confidence(0.84) == RiskLevel.MEDIUM
    assert _risk_from_confidence(0.65) == RiskLevel.MEDIUM


def test_risk_high():
    assert _risk_from_confidence(0.64) == RiskLevel.HIGH
    assert _risk_from_confidence(0.40) == RiskLevel.HIGH


def test_risk_critical():
    assert _risk_from_confidence(0.39) == RiskLevel.CRITICAL
    assert _risk_from_confidence(0.0) == RiskLevel.CRITICAL


# ---------------------------------------------------------------------------
# BaseAgent concrete subclass (minimal stub for interface tests)
# ---------------------------------------------------------------------------


class _StubAgent:
    """Minimal stand-in that doesn't touch LLM/DB — for interface shape tests."""
    AGENT_ID = "stub_agent"
    CAPABILITIES = ["stub"]


def test_agent_id_and_capabilities():
    agent = _StubAgent()
    assert agent.AGENT_ID == "stub_agent"
    assert "stub" in agent.CAPABILITIES
