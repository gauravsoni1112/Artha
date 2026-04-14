"""
Unit tests for tools/spending_trend.py — mocked DB, no Docker required.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.tools.base import ToolResult
from services.agent.tools.spending_trend import run


def _patch_execute(session, rows):
    """rows: list of (year, month, total_paise, count) tuples"""
    result = MagicMock()
    result.all.return_value = rows
    session.execute = AsyncMock(return_value=result)


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.mark.asyncio
async def test_spending_trend_returns_tool_result(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [(2025, 1, 300_00, 3), (2025, 2, 450_00, 4)])

    result = await run(session=mock_session, owner_id=owner_id)

    assert isinstance(result, ToolResult)
    assert result.tool_name == "spending_trend"


@pytest.mark.asyncio
async def test_spending_trend_monthly_periods_formatted(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [
        (2025, 1, 30000, 2),
        (2025, 2, 40000, 3),
        (2025, 3, 35000, 2),
    ])

    result = await run(session=mock_session, owner_id=owner_id, months=3)
    periods = [m["period"] for m in result.data["monthly_trend"]]

    assert periods == ["2025-01", "2025-02", "2025-03"]


@pytest.mark.asyncio
async def test_spending_trend_mom_change_computed(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [
        (2025, 1, 100_00, 5),
        (2025, 2, 150_00, 6),
    ])

    result = await run(session=mock_session, owner_id=owner_id)
    trend = result.data["monthly_trend"]

    assert "mom_change_pct" not in trend[0]  # first month has no prior
    assert trend[1]["mom_change_pct"] == 50.0  # 50% increase


@pytest.mark.asyncio
async def test_spending_trend_mom_change_negative(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [
        (2025, 1, 200_00, 5),
        (2025, 2, 100_00, 3),
    ])

    result = await run(session=mock_session, owner_id=owner_id)
    assert result.data["monthly_trend"][1]["mom_change_pct"] == -50.0


@pytest.mark.asyncio
async def test_spending_trend_empty_returns_empty_list(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)
    assert result.data["monthly_trend"] == []


@pytest.mark.asyncio
async def test_spending_trend_category_filter_passed(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [(2025, 3, 50000, 4)])

    result = await run(session=mock_session, owner_id=owner_id, category="GROCERIES")
    assert result.data["category"] == "GROCERIES"
    assert result.query_params["category"] == "GROCERIES"


@pytest.mark.asyncio
async def test_spending_trend_no_category_shows_all(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)
    assert result.data["category"] == "ALL"


@pytest.mark.asyncio
async def test_spending_trend_to_llm_str_is_string(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [(2025, 1, 10000, 1)])

    result = await run(session=mock_session, owner_id=owner_id)
    assert isinstance(result.to_llm_str(), str)
    assert "spending_trend" in result.to_llm_str()
