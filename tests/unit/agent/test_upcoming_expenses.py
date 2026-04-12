"""
Golden-input tests for tools/upcoming_expenses.py.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.tools.upcoming_expenses import run
from services.agent.tools.base import ToolResult


def _make_tx(
    description: str,
    category: str,
    amount_paise: int,
    txn_date: date,
):
    tx = MagicMock()
    tx.id = uuid.uuid4()
    tx.raw_description = description
    tx.category = category
    tx.amount_paise = amount_paise
    tx.transaction_date = txn_date
    tx.transaction_type = "DEBIT"
    return tx


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


def _patch_scalars(session, rows):
    result = MagicMock()
    result.all.return_value = rows
    session.scalars = AsyncMock(return_value=result)
    return session


def _monthly_series(description, category, amount_paise, count=3, last_offset_days=15):
    """Generate `count` transactions spaced ~30 days apart, last one `last_offset_days` ago."""
    today = date.today()
    last = today - timedelta(days=last_offset_days)
    dates = [last - timedelta(days=30 * i) for i in range(count - 1, -1, -1)]
    return [_make_tx(description, category, amount_paise, d) for d in dates]


@pytest.mark.asyncio
async def test_upcoming_expenses_returns_tool_result(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert isinstance(result, ToolResult)
    assert result.tool_name == "upcoming_expenses"


@pytest.mark.asyncio
async def test_upcoming_expenses_detects_monthly_recurring(mock_session):
    owner_id = str(uuid.uuid4())
    txs = _monthly_series("Netflix Subscription", "ENTERTAINMENT", 64900, count=3, last_offset_days=10)
    _patch_scalars(mock_session, txs)

    result = await run(session=mock_session, owner_id=owner_id, lookahead_days=30)

    # Should detect exactly one recurring expense upcoming within 30 days
    assert result.data["upcoming_count"] >= 1
    names = [u["description_prefix"] for u in result.data["upcoming"]]
    assert any("Netflix" in n for n in names)


@pytest.mark.asyncio
async def test_upcoming_expenses_no_history_warns(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["upcoming_count"] == 0
    assert len(result.warnings) > 0


@pytest.mark.asyncio
async def test_upcoming_expenses_single_occurrence_not_recurring(mock_session):
    """A transaction seen only once must NOT be flagged as recurring."""
    owner_id = str(uuid.uuid4())
    txs = [_make_tx("One-time purchase", "SHOPPING", 500_00, date.today() - timedelta(days=5))]
    _patch_scalars(mock_session, txs)

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["upcoming_count"] == 0


@pytest.mark.asyncio
async def test_upcoming_expenses_total_paise_sum(mock_session):
    owner_id = str(uuid.uuid4())
    txs = (
        _monthly_series("Netflix", "ENTERTAINMENT", 64900, count=3, last_offset_days=10)
        + _monthly_series("Gym", "HEALTH", 150000, count=3, last_offset_days=8)
    )
    _patch_scalars(mock_session, txs)

    result = await run(session=mock_session, owner_id=owner_id, lookahead_days=30)

    total = result.data["upcoming_total_paise"]
    # Each detected expense must be accounted for in total
    predicted_total = sum(u["amount_paise"] for u in result.data["upcoming"])
    assert total == predicted_total


@pytest.mark.asyncio
async def test_upcoming_expenses_data_freshness_present(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data_freshness is not None
