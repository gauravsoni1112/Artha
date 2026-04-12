"""
Golden-input tests for tools/net_worth.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.tools.net_worth import run
from services.agent.tools.base import ToolResult


def _patch_execute(session, rows):
    """rows: list of (asset_class, total_paise, count) tuples"""
    execute_result = MagicMock()
    execute_result.all.return_value = rows
    session.execute = AsyncMock(return_value=execute_result)
    return session


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.mark.asyncio
async def test_net_worth_returns_tool_result(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [("MUTUAL_FUND", 500000_00, 3)])

    result = await run(session=mock_session, owner_id=owner_id)

    assert isinstance(result, ToolResult)
    assert result.tool_name == "net_worth"


@pytest.mark.asyncio
async def test_net_worth_total_sums_all_classes(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [
        ("MUTUAL_FUND", 500000_00, 3),
        ("EQUITY", 200000_00, 5),
        ("GOLD", 50000_00, 1),
    ])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["total_net_worth_paise"] == 75000000


@pytest.mark.asyncio
async def test_net_worth_inr_format(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [("MUTUAL_FUND", 100000_00, 1)])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["total_net_worth_inr"] == "₹1,00,000.00"


@pytest.mark.asyncio
async def test_net_worth_empty_warns(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["total_net_worth_paise"] == 0
    assert len(result.warnings) > 0
    assert "No holdings" in result.warnings[0]


@pytest.mark.asyncio
async def test_net_worth_breakdown_sorted_desc(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [
        ("GOLD", 10000_00, 1),
        ("MUTUAL_FUND", 500000_00, 3),
        ("EQUITY", 200000_00, 2),
    ])

    result = await run(session=mock_session, owner_id=owner_id)

    values = [b["current_value_paise"] for b in result.data["asset_breakdown"]]
    assert values == sorted(values, reverse=True)


@pytest.mark.asyncio
async def test_net_worth_data_freshness_present(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_execute(mock_session, [])

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data_freshness is not None
