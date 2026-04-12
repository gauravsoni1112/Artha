"""
Golden-input tests for tools/portfolio_value.py.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.tools.portfolio_value import run
from services.agent.tools.base import ToolResult


def _make_holding(
    instrument_name: str,
    asset_class: str,
    current_value_paise: int,
    purchase_price_paise: int | None = None,
    units: float | None = 100.0,
    nav_paise: int | None = None,
):
    h = MagicMock()
    h.id = uuid.uuid4()
    h.instrument_name = instrument_name
    h.asset_class = asset_class
    h.isin = "INF123"
    h.units = Decimal(str(units)) if units is not None else None
    h.nav_paise = nav_paise
    h.current_value_paise = current_value_paise
    h.purchase_price_paise = purchase_price_paise
    h.valuation_date = date(2024, 6, 30)
    return h


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
async def test_portfolio_value_returns_tool_result(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [
        _make_holding("HDFC Mid Cap", "MUTUAL_FUND", 100000_00, purchase_price_paise=80000_00),
    ])

    result = await run(session=mock_session, owner_id=owner_id)

    assert isinstance(result, ToolResult)
    assert result.tool_name == "portfolio_value"


@pytest.mark.asyncio
async def test_portfolio_value_gain_loss_computed(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [
        _make_holding("HDFC Mid Cap", "MUTUAL_FUND", 120000_00, purchase_price_paise=100000_00),
    ])

    result = await run(session=mock_session, owner_id=owner_id)

    instrument = result.data["instruments"][0]
    assert instrument["gain_loss_paise"] == 20000_00
    assert instrument["gain_loss_pct"] == 20.0


@pytest.mark.asyncio
async def test_portfolio_value_no_purchase_price_gain_is_none(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [
        _make_holding("Axis Bluechip", "MUTUAL_FUND", 50000_00, purchase_price_paise=None),
    ])

    result = await run(session=mock_session, owner_id=owner_id)

    instrument = result.data["instruments"][0]
    assert instrument["gain_loss_paise"] is None
    assert instrument["gain_loss_pct"] is None


@pytest.mark.asyncio
async def test_portfolio_value_totals(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [
        _make_holding("Fund A", "MUTUAL_FUND", 100000_00, purchase_price_paise=80000_00),
        _make_holding("Fund B", "MUTUAL_FUND", 50000_00, purchase_price_paise=40000_00),
    ])

    result = await run(session=mock_session, owner_id=owner_id)

    totals = result.data["totals"]
    assert totals["total_current_value_paise"] == 15000000
    assert totals["total_invested_paise"] == 12000000
    assert totals["total_gain_loss_paise"] == 3000000


@pytest.mark.asyncio
async def test_portfolio_value_empty_warns(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["instrument_count"] == 0
    assert len(result.warnings) > 0


@pytest.mark.asyncio
async def test_portfolio_value_data_freshness_present(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data_freshness is not None
