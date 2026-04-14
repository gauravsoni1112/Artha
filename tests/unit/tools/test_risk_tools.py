"""
Unit tests for the 4 Phase 4 risk tools.

emergency_fund_months, asset_concentration, debt_to_income use async DB queries —
we mock the AsyncSession. insurance_coverage_gap is pure heuristic logic so we
can test it end-to-end without a mock DB.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# insurance_coverage_gap — pure heuristic, no DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insurance_gap_no_income():
    from services.agent.tools.insurance_coverage_gap import run

    result = await run(
        session=AsyncMock(),
        owner_id=str(uuid.uuid4()),
        annual_income_paise=0,
    )
    assert result.tool_name == "insurance_coverage_gap"
    assert any("zero" in w.lower() or "not provided" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_insurance_gap_life_cover_calculated():
    from services.agent.tools.insurance_coverage_gap import run

    annual = 1_200_000 * 100  # ₹12L/yr in paise
    result = await run(
        session=AsyncMock(),
        owner_id=str(uuid.uuid4()),
        annual_income_paise=annual,
        existing_life_cover_paise=0,
    )
    # Recommended = 10× annual
    assert result.data["life_cover"]["recommended_paise"] == annual * 10
    assert result.data["life_cover"]["gap_paise"] == annual * 10
    assert not result.data["life_cover"]["is_adequate"]


@pytest.mark.asyncio
async def test_insurance_gap_adequate_cover():
    from services.agent.tools.insurance_coverage_gap import run

    annual = 500_000 * 100   # ₹5L
    existing_life = annual * 12  # more than 10×

    result = await run(
        session=AsyncMock(),
        owner_id=str(uuid.uuid4()),
        annual_income_paise=annual,
        existing_life_cover_paise=existing_life,
        existing_health_cover_paise=500_000 * 100,  # ₹5L minimum
    )
    assert result.data["life_cover"]["is_adequate"]


@pytest.mark.asyncio
async def test_insurance_gap_family_health_floor():
    from services.agent.tools.insurance_coverage_gap import run

    result = await run(
        session=AsyncMock(),
        owner_id=str(uuid.uuid4()),
        annual_income_paise=400_000 * 100,  # ₹4L
        is_family_scope=True,
        existing_health_cover_paise=0,
    )
    # Family floor is ₹10L = 1_000_000 * 100 paise
    assert result.data["health_cover"]["recommended_paise"] >= 1_000_000 * 100


@pytest.mark.asyncio
async def test_insurance_gap_individual_health_floor():
    from services.agent.tools.insurance_coverage_gap import run

    result = await run(
        session=AsyncMock(),
        owner_id=str(uuid.uuid4()),
        annual_income_paise=200_000 * 100,  # ₹2L — income-based would be ₹20k, below floor
        is_family_scope=False,
    )
    # Individual floor is ₹5L = 500_000 * 100 paise
    assert result.data["health_cover"]["recommended_paise"] >= 500_000 * 100


# ---------------------------------------------------------------------------
# asset_concentration — mock session returning grouped rows
# ---------------------------------------------------------------------------


def _mock_row(asset_class: str, total_paise: int):
    row = MagicMock()
    row.asset_class = asset_class
    row.total_paise = total_paise
    return row


@pytest.mark.asyncio
async def test_asset_concentration_no_holdings():
    from services.agent.tools.asset_concentration import run

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    result = await run(session=mock_session, owner_id=str(uuid.uuid4()))
    assert result.data["is_concentrated"] is False
    assert len(result.warnings) == 1


@pytest.mark.asyncio
async def test_asset_concentration_flags_over_threshold():
    from services.agent.tools.asset_concentration import run

    rows = [
        _mock_row("EQUITY", 8_000_000 * 100),   # 80 %
        _mock_row("MUTUAL_FUND", 2_000_000 * 100),  # 20 %
    ]
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=rows)))

    result = await run(
        session=mock_session,
        owner_id=str(uuid.uuid4()),
        concentration_threshold_pct=40.0,
    )
    assert result.data["is_concentrated"] is True
    assert "EQUITY" in result.data["concentrated_classes"]
    assert len(result.warnings) > 0


@pytest.mark.asyncio
async def test_asset_concentration_within_threshold():
    from services.agent.tools.asset_concentration import run

    rows = [
        _mock_row("EQUITY", 3_000_000 * 100),       # 30 %
        _mock_row("MUTUAL_FUND", 4_000_000 * 100),  # 40 %
        _mock_row("GOLD", 3_000_000 * 100),          # 30 %
    ]
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=rows)))

    result = await run(
        session=mock_session,
        owner_id=str(uuid.uuid4()),
        concentration_threshold_pct=50.0,
    )
    assert result.data["is_concentrated"] is False
    assert result.warnings == []


@pytest.mark.asyncio
async def test_asset_concentration_pct_sums_to_100():
    from services.agent.tools.asset_concentration import run

    rows = [
        _mock_row("EQUITY", 6_000_000 * 100),
        _mock_row("DEBT", 4_000_000 * 100),
    ]
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=rows)))

    result = await run(session=mock_session, owner_id=str(uuid.uuid4()))
    total_pct = sum(entry["concentration_pct"] for entry in result.data["breakdown"])
    assert abs(total_pct - 100.0) < 0.01


# ---------------------------------------------------------------------------
# debt_to_income — mock session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dti_healthy():
    from services.agent.tools.debt_to_income import run

    mock_session = AsyncMock()
    # debt = ₹15k/mo × 3 months = ₹45k; income = ₹100k/mo × 3 = ₹300k
    mock_session.scalar = AsyncMock(side_effect=[45_000 * 100, 300_000 * 100])

    result = await run(session=mock_session, owner_id=str(uuid.uuid4()), months=3)
    assert result.data["assessment"] == "healthy"
    assert result.data["dti_pct"] == pytest.approx(15.0)


@pytest.mark.asyncio
async def test_dti_critical():
    from services.agent.tools.debt_to_income import run

    mock_session = AsyncMock()
    # debt = ₹60k/mo × 3 = ₹180k; income = ₹100k/mo × 3 = ₹300k → DTI 60%
    mock_session.scalar = AsyncMock(side_effect=[180_000 * 100, 300_000 * 100])

    result = await run(session=mock_session, owner_id=str(uuid.uuid4()), months=3)
    assert result.data["assessment"] == "critical"
    assert result.data["dti_pct"] > 50


@pytest.mark.asyncio
async def test_dti_no_income():
    from services.agent.tools.debt_to_income import run

    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(side_effect=[10_000 * 100, 0])

    result = await run(session=mock_session, owner_id=str(uuid.uuid4()), months=3)
    assert result.data["assessment"] == "insufficient_data"
    assert result.data["dti_pct"] is None


# ---------------------------------------------------------------------------
# emergency_fund_months — mock session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emergency_fund_healthy():
    from services.agent.tools.emergency_fund_months import run

    mock_session = AsyncMock()
    # liquid balance: net CREDIT - DEBIT on savings accounts
    # We'll mock scalars for liquid account ids, then balance query, then expense query
    mock_session.scalars = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=[uuid.uuid4()]))
    )

    # balance rows: CREDIT 900k, DEBIT 300k → net 600k paise = ₹6k balance
    balance_rows = [
        MagicMock(transaction_type="CREDIT", total=600_000 * 100),
        MagicMock(transaction_type="DEBIT", total=300_000 * 100),
    ]

    # We need to patch the inner execute and scalar calls precisely.
    # Use side_effect sequence: first execute = balance, second scalar = expenses
    balance_result = MagicMock()
    balance_result.all = MagicMock(return_value=[(r.transaction_type, r.total) for r in balance_rows])

    mock_session.execute = AsyncMock(return_value=balance_result)
    # avg monthly expense = 30k paise × 3 months = 90k total
    mock_session.scalar = AsyncMock(return_value=90_000 * 100)

    result = await run(session=mock_session, owner_id=str(uuid.uuid4()), expense_months=3)
    # liquid = 600k - 300k = 300k paise; expense/mo = 90k/3 = 30k; months = 300k/30k = 10
    assert result.data["assessment"] == "healthy"
    assert result.data["months_covered"] is not None


@pytest.mark.asyncio
async def test_emergency_fund_no_liquid_accounts():
    from services.agent.tools.emergency_fund_months import run

    mock_session = AsyncMock()
    # No liquid accounts
    mock_session.scalars = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=[]))
    )
    mock_session.scalar = AsyncMock(return_value=90_000 * 100)

    result = await run(session=mock_session, owner_id=str(uuid.uuid4()), expense_months=3)
    # liquid balance = 0 → critical
    assert result.data["assessment"] == "critical"
    assert result.data["liquid_balance_paise"] == 0
