"""
Golden-input tests for tools/tax_summary.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.tools.tax_summary import run
from services.agent.tools.base import ToolResult


def _make_tax_row(
    fiscal_year: str = "2024-25",
    gross_income_paise: int | None = 100000_00,
    taxable_income_paise: int | None = 80000_00,
    tax_paid_paise: int | None = 5000_00,
    tds_paise: int | None = 3000_00,
    itr_filed: bool = True,
):
    t = MagicMock()
    t.fiscal_year = fiscal_year
    t.gross_income_paise = gross_income_paise
    t.taxable_income_paise = taxable_income_paise
    t.tax_paid_paise = tax_paid_paise
    t.tds_paise = tds_paise
    t.itr_filed = itr_filed
    return t


@pytest.fixture
def mock_session():
    return AsyncMock()


def _patch_scalars(session, rows):
    result = MagicMock()
    result.all.return_value = rows
    session.scalars = AsyncMock(return_value=result)
    return session


def _patch_execute(session, rows):
    result = MagicMock()
    result.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_tax_summary_returns_tool_result(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [_make_tax_row()])

    result = await run(session=mock_session, owner_id=owner_id)

    assert isinstance(result, ToolResult)
    assert result.tool_name == "tax_summary"


@pytest.mark.asyncio
async def test_tax_summary_itr_record_present(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [_make_tax_row("2024-25", itr_filed=True)])

    result = await run(session=mock_session, owner_id=owner_id)

    summaries = result.data["fiscal_years"]
    assert len(summaries) == 1
    assert summaries[0]["fiscal_year"] == "2024-25"
    assert summaries[0]["itr_filed"] is True
    assert summaries[0]["source"] == "itr_record"
    assert len(result.warnings) == 0


@pytest.mark.asyncio
async def test_tax_summary_fallback_to_salary_credits(mock_session):
    owner_id = str(uuid.uuid4())
    # No ITR records
    _patch_scalars(mock_session, [])
    # Salary credits as fallback
    _patch_execute(mock_session, [("2024-25", 100000_00)])

    result = await run(session=mock_session, owner_id=owner_id)

    summaries = result.data["fiscal_years"]
    assert len(summaries) == 1
    assert summaries[0]["source"] == "estimated_from_salary_credits"
    assert summaries[0]["itr_filed"] is False
    assert len(result.warnings) > 0
    assert "estimated" in result.warnings[0].lower()


@pytest.mark.asyncio
async def test_tax_summary_no_data_warns(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])
    _patch_execute(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["fiscal_years"] == []
    assert len(result.warnings) > 0


@pytest.mark.asyncio
async def test_tax_summary_inr_formatting(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [_make_tax_row(gross_income_paise=100000_00)])  # ₹1,00,000

    result = await run(session=mock_session, owner_id=owner_id)

    s = result.data["fiscal_years"][0]
    assert s["gross_income_inr"] == "₹1,00,000.00"


@pytest.mark.asyncio
async def test_tax_summary_data_freshness_present(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])
    _patch_execute(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data_freshness is not None
