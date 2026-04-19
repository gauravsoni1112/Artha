"""
Unit tests for services/agent/tools/calculate.py.

All four tools are pure math — no DB session needed. Session is passed as None.
"""

from __future__ import annotations

import pytest

from services.agent.tools.calculate import (
    run_convert,
    run_percentage,
    run_growth,
    run_compound_interest,
)
from services.agent.tools.base import ToolResult


# ── convert_amount ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_convert_rupee_to_paise():
    result = await run_convert(None, amount=1.0, from_unit="rupee", to_unit="paise")
    assert isinstance(result, ToolResult)
    assert result.data["result_paise"] == 100


@pytest.mark.asyncio
async def test_convert_lakh_to_paise():
    result = await run_convert(None, amount=1.0, from_unit="lakh", to_unit="paise")
    assert result.data["result_paise"] == 10_000_000  # 1L = ₹1,00,000 = 1,00,00,000 paise


@pytest.mark.asyncio
async def test_convert_crore_to_paise():
    result = await run_convert(None, amount=1.0, from_unit="crore", to_unit="paise")
    assert result.data["result_paise"] == 1_000_000_000


@pytest.mark.asyncio
async def test_convert_paise_to_rupee():
    result = await run_convert(None, amount=10000.0, from_unit="paise", to_unit="rupee")
    assert result.data["result_value"] == pytest.approx(100.0)
    assert result.data["result_unit"] == "rupee"


@pytest.mark.asyncio
async def test_convert_paise_to_lakh():
    result = await run_convert(None, amount=10_000_000.0, from_unit="paise", to_unit="lakh")
    assert result.data["result_value"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_convert_rupee_to_lakh():
    # 5,00,000 rupees → 5 lakh
    result = await run_convert(None, amount=500_000.0, from_unit="rupee", to_unit="lakh")
    assert result.data["result_value"] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_convert_inr_format_populated():
    result = await run_convert(None, amount=1.0, from_unit="lakh", to_unit="paise")
    assert result.data["result_inr"] == "₹1,00,000.00"


@pytest.mark.asyncio
async def test_convert_invalid_from_unit_returns_warning():
    result = await run_convert(None, amount=1.0, from_unit="dollar", to_unit="paise")
    assert len(result.warnings) > 0
    assert "dollar" in result.warnings[0]
    assert result.data == {}


@pytest.mark.asyncio
async def test_convert_invalid_to_unit_returns_warning():
    result = await run_convert(None, amount=1.0, from_unit="rupee", to_unit="usd")
    assert len(result.warnings) > 0
    assert result.data == {}


@pytest.mark.asyncio
async def test_convert_case_insensitive():
    result = await run_convert(None, amount=1.0, from_unit="LAKH", to_unit="PAISE")
    assert result.data["result_paise"] == 10_000_000


@pytest.mark.asyncio
async def test_convert_fractional_lakh():
    # 2.5 lakh rupees → 25,00,000 paise
    result = await run_convert(None, amount=2.5, from_unit="lakh", to_unit="paise")
    assert result.data["result_paise"] == 25_000_000


@pytest.mark.asyncio
async def test_convert_query_params_recorded():
    result = await run_convert(None, amount=3.0, from_unit="lakh", to_unit="rupee")
    assert result.query_params["from_unit"] == "lakh"
    assert result.query_params["to_unit"] == "rupee"


# ── calculate_percentage ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_percentage_basic():
    # 10% of ₹1,000 (100000 paise) = ₹100 (10000 paise)
    result = await run_percentage(None, base_paise=100_000, percent=10.0)
    assert result.data["result_paise"] == 10_000


@pytest.mark.asyncio
async def test_percentage_15_of_two_lakh():
    # 15% of ₹2,00,000 (20_000_000 paise) = ₹30,000 (3_000_000 paise)
    result = await run_percentage(None, base_paise=20_000_000, percent=15.0)
    assert result.data["result_paise"] == 3_000_000


@pytest.mark.asyncio
async def test_percentage_fractional():
    # 0.5% of 1_000_000 paise = 5000 paise
    result = await run_percentage(None, base_paise=1_000_000, percent=0.5)
    assert result.data["result_paise"] == 5_000


@pytest.mark.asyncio
async def test_percentage_100_percent():
    result = await run_percentage(None, base_paise=50_000, percent=100.0)
    assert result.data["result_paise"] == 50_000


@pytest.mark.asyncio
async def test_percentage_description_present():
    result = await run_percentage(None, base_paise=100_000, percent=10.0)
    assert "10.0%" in result.data["description"]
    assert "₹" in result.data["description"]


@pytest.mark.asyncio
async def test_percentage_result_inr_format():
    result = await run_percentage(None, base_paise=20_000_000, percent=15.0)
    assert result.data["result_inr"] == "₹30,000.00"


@pytest.mark.asyncio
async def test_percentage_rounding():
    # 33.33% of 100 paise ≈ 33 paise (ROUND_HALF_UP)
    result = await run_percentage(None, base_paise=100, percent=33.33)
    assert result.data["result_paise"] == 33


@pytest.mark.asyncio
async def test_percentage_returns_tool_result():
    result = await run_percentage(None, base_paise=1_000_000, percent=5.0)
    assert isinstance(result, ToolResult)
    assert result.tool_name == "calculate_percentage"


# ── calculate_growth ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_growth_positive():
    result = await run_growth(None, from_paise=100_000, to_paise=120_000)
    assert result.data["direction"] == "up"
    assert result.data["absolute_change_paise"] == 20_000
    assert result.data["percent_change"] == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_growth_negative():
    result = await run_growth(None, from_paise=100_000, to_paise=80_000)
    assert result.data["direction"] == "down"
    assert result.data["absolute_change_paise"] == -20_000
    assert result.data["percent_change"] == pytest.approx(-20.0)


@pytest.mark.asyncio
async def test_growth_flat():
    result = await run_growth(None, from_paise=100_000, to_paise=100_000)
    assert result.data["direction"] == "flat"
    assert result.data["percent_change"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_growth_zero_base_warns():
    result = await run_growth(None, from_paise=0, to_paise=100_000)
    assert result.data["percent_change"] is None
    assert len(result.warnings) > 0
    assert "zero" in result.warnings[0]


@pytest.mark.asyncio
async def test_growth_inr_format():
    result = await run_growth(None, from_paise=10_000_000, to_paise=12_000_000)
    assert result.data["from_inr"] == "₹1,00,000.00"
    assert result.data["to_inr"] == "₹1,20,000.00"


@pytest.mark.asyncio
async def test_growth_absolute_change_inr_is_absolute_value():
    # Even for negative growth, absolute_change_inr should be positive
    result = await run_growth(None, from_paise=100_000, to_paise=50_000)
    assert result.data["absolute_change_paise"] == -50_000
    assert result.data["absolute_change_inr"] == "₹500.00"


@pytest.mark.asyncio
async def test_growth_returns_tool_result():
    result = await run_growth(None, from_paise=1_000_000, to_paise=1_100_000)
    assert isinstance(result, ToolResult)
    assert result.tool_name == "calculate_growth"


@pytest.mark.asyncio
async def test_growth_percent_rounded_to_two_decimals():
    # 1/3 growth ≈ 33.33%
    result = await run_growth(None, from_paise=300_000, to_paise=400_000)
    assert result.data["percent_change"] == pytest.approx(33.33)


# ── calculate_compound_interest ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compound_interest_basic():
    # ₹1,00,000 at 10% annual for 1 year (monthly compounding)
    result = await run_compound_interest(
        None, principal_paise=10_000_000, annual_rate_pct=10.0, years=1.0, compounding_frequency=12
    )
    assert isinstance(result, ToolResult)
    assert result.data["maturity_paise"] > 10_000_000
    assert result.data["interest_earned_paise"] > 0


@pytest.mark.asyncio
async def test_compound_interest_zero_rate():
    result = await run_compound_interest(
        None, principal_paise=10_000_000, annual_rate_pct=0.0, years=5.0, compounding_frequency=12
    )
    assert result.data["maturity_paise"] == 10_000_000
    assert result.data["interest_earned_paise"] == 0


@pytest.mark.asyncio
async def test_compound_interest_annual_compounding():
    # ₹1,000 at 10% annual, 1 year, compounded once → ₹1,100
    result = await run_compound_interest(
        None, principal_paise=100_000, annual_rate_pct=10.0, years=1.0, compounding_frequency=1
    )
    assert result.data["maturity_paise"] == 110_000


@pytest.mark.asyncio
async def test_compound_interest_ear_greater_than_nominal_when_intra_year():
    # Monthly compounding EAR > nominal annual rate
    result = await run_compound_interest(
        None, principal_paise=10_000_000, annual_rate_pct=12.0, years=1.0, compounding_frequency=12
    )
    assert result.data["effective_annual_rate_pct"] > 12.0


@pytest.mark.asyncio
async def test_compound_interest_inr_format_present():
    result = await run_compound_interest(
        None, principal_paise=10_000_000, annual_rate_pct=7.0, years=3.0, compounding_frequency=4
    )
    assert result.data["principal_inr"] == "₹1,00,000.00"
    assert "₹" in result.data["maturity_inr"]


@pytest.mark.asyncio
async def test_compound_interest_invalid_frequency_warns():
    result = await run_compound_interest(
        None, principal_paise=10_000_000, annual_rate_pct=7.0, years=1.0, compounding_frequency=0
    )
    assert len(result.warnings) > 0
    assert result.data == {}


@pytest.mark.asyncio
async def test_compound_interest_invalid_years_warns():
    result = await run_compound_interest(
        None, principal_paise=10_000_000, annual_rate_pct=7.0, years=0.0, compounding_frequency=12
    )
    assert len(result.warnings) > 0
    assert result.data == {}


@pytest.mark.asyncio
async def test_compound_interest_negative_rate_warns():
    result = await run_compound_interest(
        None, principal_paise=10_000_000, annual_rate_pct=-5.0, years=1.0, compounding_frequency=12
    )
    assert len(result.warnings) > 0
    assert result.data == {}


@pytest.mark.asyncio
async def test_compound_interest_query_params_recorded():
    result = await run_compound_interest(
        None, principal_paise=5_000_000, annual_rate_pct=8.5, years=2.0, compounding_frequency=12
    )
    assert result.query_params["annual_rate_pct"] == 8.5
    assert result.query_params["years"] == 2.0


@pytest.mark.asyncio
async def test_compound_interest_maturity_equals_principal_plus_interest():
    result = await run_compound_interest(
        None, principal_paise=10_000_000, annual_rate_pct=6.0, years=2.0, compounding_frequency=12
    )
    assert (
        result.data["maturity_paise"]
        == 10_000_000 + result.data["interest_earned_paise"]
    )
