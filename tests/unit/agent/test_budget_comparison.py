"""
Unit tests for tools/budget_comparison.py — mocked DB, no Docker required.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.agent.tools.base import ToolResult
from services.agent.tools.budget_comparison import run


def _named_row(category, actual_paise):
    row = MagicMock()
    row.category = category
    row.actual_paise = actual_paise
    return row


def _goal_obj(category, target_paise):
    g = MagicMock()
    g.category = category
    g.target_amount_paise = target_paise
    g.is_active = True
    return g


@pytest.fixture
def mock_session():
    return AsyncMock()


def _setup_session(mock_session, actual_rows, goal_objects):
    """Configure mock_session to return actuals then goals in sequence."""
    exec_results = []

    # First execute call → actuals
    actual_exec = MagicMock()
    actual_exec.all.return_value = actual_rows
    exec_results.append(actual_exec)

    # Second execute call → goals (scalars)
    goal_exec = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = goal_objects
    goal_exec.scalars.return_value = scalars_mock
    exec_results.append(goal_exec)

    mock_session.execute = AsyncMock(side_effect=exec_results)


@pytest.mark.asyncio
async def test_budget_comparison_returns_tool_result(mock_session):
    owner_id = str(uuid.uuid4())
    _setup_session(mock_session, [_named_row("GROCERIES", 50000)], [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert isinstance(result, ToolResult)
    assert result.tool_name == "budget_comparison"


@pytest.mark.asyncio
async def test_budget_comparison_over_budget_detected(mock_session):
    owner_id = str(uuid.uuid4())
    _setup_session(
        mock_session,
        [_named_row("GROCERIES", 70000)],  # actual 700
        [_goal_obj("GROCERIES", 50000)],   # budget 500
    )

    result = await run(session=mock_session, owner_id=owner_id)
    row = next(r for r in result.data["comparison"] if r["category"] == "GROCERIES")

    assert row["over_budget"] is True
    assert row["variance_paise"] == 20000  # over by 200


@pytest.mark.asyncio
async def test_budget_comparison_under_budget(mock_session):
    owner_id = str(uuid.uuid4())
    _setup_session(
        mock_session,
        [_named_row("GROCERIES", 30000)],
        [_goal_obj("GROCERIES", 50000)],
    )

    result = await run(session=mock_session, owner_id=owner_id)
    row = next(r for r in result.data["comparison"] if r["category"] == "GROCERIES")

    assert row["over_budget"] is False
    assert row["variance_paise"] == -20000  # under by 200


@pytest.mark.asyncio
async def test_budget_comparison_no_goals_has_budgets_false(mock_session):
    owner_id = str(uuid.uuid4())
    _setup_session(mock_session, [_named_row("FOOD", 10000)], [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["has_budgets"] is False
    row = result.data["comparison"][0]
    assert row["budget_paise"] is None
    assert row["over_budget"] is None


@pytest.mark.asyncio
async def test_budget_comparison_category_in_goals_but_no_actual(mock_session):
    owner_id = str(uuid.uuid4())
    _setup_session(
        mock_session,
        [],  # no actuals
        [_goal_obj("TRAVEL", 100000)],
    )

    result = await run(session=mock_session, owner_id=owner_id)
    row = next(r for r in result.data["comparison"] if r["category"] == "TRAVEL")

    assert row["actual_paise"] == 0
    assert row["over_budget"] is False  # 0 actual < 1000 budget


@pytest.mark.asyncio
async def test_budget_comparison_totals_correct(mock_session):
    owner_id = str(uuid.uuid4())
    _setup_session(
        mock_session,
        [_named_row("FOOD", 30000), _named_row("TRANSPORT", 20000)],
        [],
    )

    result = await run(session=mock_session, owner_id=owner_id)
    assert result.data["total_actual_paise"] == 50000


@pytest.mark.asyncio
async def test_budget_comparison_to_llm_str_is_string(mock_session):
    owner_id = str(uuid.uuid4())
    _setup_session(mock_session, [], [])

    result = await run(session=mock_session, owner_id=owner_id)
    assert isinstance(result.to_llm_str(), str)
