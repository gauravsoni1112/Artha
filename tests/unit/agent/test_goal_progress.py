"""
Unit tests for tools/goal_progress.py — mocked DB, no Docker required.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.tools.base import ToolResult
from services.agent.tools.goal_progress import run


def _goal(
    name: str,
    target_paise: int,
    current_paise: int,
    category: str | None = None,
    target_date: date | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    g = MagicMock()
    g.goal_name = name
    g.target_amount_paise = target_paise
    g.current_amount_paise = current_paise
    g.category = category
    g.target_date = target_date
    g.is_active = True
    g.created_at = created_at or datetime(2024, 1, 1, tzinfo=timezone.utc)
    return g


def _setup_session(mock_session, goals):
    exec_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = goals
    exec_result.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=exec_result)


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.mark.asyncio
async def test_goal_progress_returns_tool_result(mock_session):
    _setup_session(mock_session, [_goal("Emergency Fund", 500_000_00, 200_000_00)])
    result = await run(session=mock_session, owner_id=str(uuid.uuid4()))
    assert isinstance(result, ToolResult)
    assert result.tool_name == "goal_progress"


@pytest.mark.asyncio
async def test_goal_progress_pct_complete_computed(mock_session):
    _setup_session(mock_session, [_goal("Car Fund", 1_000_000, 250_000)])
    result = await run(session=mock_session, owner_id=str(uuid.uuid4()))
    g = result.data["goals"][0]
    assert g["pct_complete"] == 25.0


@pytest.mark.asyncio
async def test_goal_progress_100pct_complete(mock_session):
    _setup_session(mock_session, [_goal("Vacation", 100_000, 100_000)])
    result = await run(session=mock_session, owner_id=str(uuid.uuid4()))
    assert result.data["goals"][0]["pct_complete"] == 100.0


@pytest.mark.asyncio
async def test_goal_progress_remaining_paise_clamped_to_zero(mock_session):
    # current > target (overfunded)
    _setup_session(mock_session, [_goal("Overfunded", 100_000, 120_000)])
    result = await run(session=mock_session, owner_id=str(uuid.uuid4()))
    assert result.data["goals"][0]["remaining_paise"] == 0


@pytest.mark.asyncio
async def test_goal_progress_days_remaining_set_when_target_date_given(mock_session):
    future_date = date(2027, 1, 1)
    _setup_session(mock_session, [_goal("House", 50_000_000, 1_000_000, target_date=future_date)])
    result = await run(session=mock_session, owner_id=str(uuid.uuid4()))
    g = result.data["goals"][0]
    assert g["target_date"] == "2027-01-01"
    assert g["days_remaining"] is not None
    assert g["days_remaining"] > 0


@pytest.mark.asyncio
async def test_goal_progress_no_target_date_days_remaining_none(mock_session):
    _setup_session(mock_session, [_goal("Open Goal", 100_000, 50_000)])
    result = await run(session=mock_session, owner_id=str(uuid.uuid4()))
    g = result.data["goals"][0]
    assert g["days_remaining"] is None
    assert g["on_track"] is None


@pytest.mark.asyncio
async def test_goal_progress_empty_goals_list(mock_session):
    _setup_session(mock_session, [])
    result = await run(session=mock_session, owner_id=str(uuid.uuid4()))
    assert result.data["goals"] == []
    assert result.data["total_goals"] == 0


@pytest.mark.asyncio
async def test_goal_progress_multiple_goals(mock_session):
    _setup_session(mock_session, [
        _goal("Goal A", 100_000, 50_000),
        _goal("Goal B", 200_000, 200_000),
        _goal("Goal C", 300_000, 0),
    ])
    result = await run(session=mock_session, owner_id=str(uuid.uuid4()))
    assert result.data["total_goals"] == 3


@pytest.mark.asyncio
async def test_goal_progress_to_llm_str_is_string(mock_session):
    _setup_session(mock_session, [_goal("Test Goal", 10_000, 5_000)])
    result = await run(session=mock_session, owner_id=str(uuid.uuid4()))
    assert isinstance(result.to_llm_str(), str)
    assert "goal_progress" in result.to_llm_str()
