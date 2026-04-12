"""
Golden-input tests for tools/transaction_query.py.

All DB interactions are mocked — no Docker required.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.agent.tools.transaction_query import run
from services.agent.tools.base import ToolResult


def _make_tx(
    amount_paise: int,
    txn_type: str,
    category: str | None = "GROCERIES",
    description: str = "BigBasket",
    txn_date: date = date(2024, 6, 15),
):
    tx = MagicMock()
    tx.id = uuid.uuid4()
    tx.transaction_date = txn_date
    tx.raw_description = description
    tx.category = category
    tx.transaction_type = txn_type
    tx.amount_paise = amount_paise
    tx.fiscal_year = "2024-25"
    tx.account_id = uuid.uuid4()
    return tx


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


def _patch_scalars(session, rows):
    scalars_result = MagicMock()
    scalars_result.all.return_value = rows
    session.scalars = AsyncMock(return_value=scalars_result)
    return session


@pytest.mark.asyncio
async def test_transaction_query_returns_tool_result(mock_session):
    owner_id = str(uuid.uuid4())
    rows = [_make_tx(25000, "DEBIT"), _make_tx(10000000, "CREDIT", category="SALARY", description="Salary")]
    _patch_scalars(mock_session, rows)

    result = await run(session=mock_session, owner_id=owner_id)

    assert isinstance(result, ToolResult)
    assert result.tool_name == "transaction_query"


@pytest.mark.asyncio
async def test_transaction_query_data_freshness_present(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert isinstance(result.data_freshness, datetime)
    assert result.data_freshness.tzinfo is not None  # timezone-aware


@pytest.mark.asyncio
async def test_transaction_query_summary_totals(mock_session):
    owner_id = str(uuid.uuid4())
    rows = [
        _make_tx(500_00, "DEBIT"),   # ₹500
        _make_tx(250_00, "DEBIT"),   # ₹250
        _make_tx(100000_00, "CREDIT", category="SALARY"),  # ₹1,00,000
    ]
    _patch_scalars(mock_session, rows)

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["summary"]["total_debit_paise"] == 75000
    assert result.data["summary"]["total_credit_paise"] == 10000000
    assert result.data["summary"]["net_paise"] == 10000000 - 75000


@pytest.mark.asyncio
async def test_transaction_query_inr_formatting(mock_session):
    owner_id = str(uuid.uuid4())
    rows = [_make_tx(100000_00, "CREDIT", category="SALARY")]  # ₹1,00,000
    _patch_scalars(mock_session, rows)

    result = await run(session=mock_session, owner_id=owner_id)

    tx = result.data["transactions"][0]
    assert tx["amount_inr"] == "₹1,00,000.00"


@pytest.mark.asyncio
async def test_transaction_query_empty_returns_zero_summary(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["count"] == 0
    assert result.data["summary"]["total_debit_paise"] == 0
    assert result.data["summary"]["total_credit_paise"] == 0


@pytest.mark.asyncio
async def test_transaction_query_query_params_echoed(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])

    result = await run(
        session=mock_session,
        owner_id=owner_id,
        start_date="2024-06-01",
        end_date="2024-06-30",
        category="GROCERIES",
    )

    assert result.query_params["start_date"] == "2024-06-01"
    assert result.query_params["category"] == "GROCERIES"


@pytest.mark.asyncio
async def test_transaction_query_to_llm_str_is_valid_json(mock_session):
    import json
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)
    payload = json.loads(result.to_llm_str())

    assert "data_freshness" in payload
    assert "data" in payload
    assert "tool_name" in payload
