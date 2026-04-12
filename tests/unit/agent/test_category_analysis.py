"""
Golden-input tests for tools/category_analysis.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.tools.category_analysis import run
from services.agent.tools.base import ToolResult


def _patch_execute(session, rows):
    """rows: list of (category, txn_type, total_paise, count) tuples"""
    execute_result = MagicMock()
    execute_result.all.return_value = rows
    session.execute = AsyncMock(return_value=execute_result)
    return session


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.mark.asyncio
async def test_category_analysis_returns_tool_result(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [
        ("GROCERIES", "DEBIT", 500_00, 3),
        ("SALARY", "CREDIT", 100000_00, 1),
    ])

    result = await run(session=mock_session, owner_id=owner_id)

    assert isinstance(result, ToolResult)
    assert result.tool_name == "category_analysis"


@pytest.mark.asyncio
async def test_category_analysis_spend_breakdown_sorted_desc(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [
        ("GROCERIES", "DEBIT", 250_00, 2),
        ("DINING", "DEBIT", 500_00, 3),
        ("UTILITIES", "DEBIT", 100_00, 1),
    ])

    result = await run(session=mock_session, owner_id=owner_id)

    breakdown = result.data["spend_breakdown"]
    amounts = [b["amount_paise"] for b in breakdown]
    assert amounts == sorted(amounts, reverse=True)


@pytest.mark.asyncio
async def test_category_analysis_percentages_sum_100(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [
        ("GROCERIES", "DEBIT", 500_00, 2),
        ("DINING", "DEBIT", 500_00, 2),
    ])

    result = await run(session=mock_session, owner_id=owner_id)

    total_pct = sum(b["pct_of_spend"] for b in result.data["spend_breakdown"])
    assert abs(total_pct - 100.0) < 0.01


@pytest.mark.asyncio
async def test_category_analysis_savings_computed(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [
        ("SALARY", "CREDIT", 100000_00, 1),
        ("GROCERIES", "DEBIT", 20000_00, 5),
    ])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["total_income_paise"] == 10000000
    assert result.data["total_spend_paise"] == 2000000
    assert result.data["savings_paise"] == 8000000


@pytest.mark.asyncio
async def test_category_analysis_null_category_bucketed_as_uncategorized(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [
        (None, "DEBIT", 300_00, 4),
    ])

    result = await run(session=mock_session, owner_id=owner_id)

    cats = [b["category"] for b in result.data["spend_breakdown"]]
    assert "UNCATEGORIZED" in cats


@pytest.mark.asyncio
async def test_category_analysis_data_freshness_present(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data_freshness is not None
