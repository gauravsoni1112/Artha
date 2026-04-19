"""
calculate — pure-math tools so the LLM never does arithmetic itself.

Four operations registered as separate tools:
  convert_amount             — unit conversion: paise / rupee / lakh / crore
  calculate_percentage       — X% of a paise amount
  calculate_growth           — absolute and relative change between two paise values
  calculate_compound_interest — lump-sum compound interest / FD projection

All money inputs and outputs use paise (int). The LLM must call these tools
for every financial calculation instead of computing inline.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.money import format_inr
from services.agent.tools.base import ToolResult

# Paise value of each human-readable denomination
_PAISE_PER: dict[str, Decimal] = {
    "paise": Decimal("1"),
    "rupee": Decimal("100"),
    "lakh":  Decimal("10000000"),    # 1 lakh rupee  = 1,00,000 × 100 paise
    "crore": Decimal("1000000000"),  # 1 crore rupee = 1,00,00,000 × 100 paise
}

_VALID_UNITS = frozenset(_PAISE_PER.keys())


async def run_convert(
    session: AsyncSession | None,
    amount: float,
    from_unit: str,
    to_unit: str,
) -> ToolResult:
    """
    Convert an INR amount between denominations (paise / rupee / lakh / crore).
    Always returns result_paise (int) so downstream tools can use it directly.
    """
    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()
    warnings: list[str] = []

    if from_unit not in _VALID_UNITS:
        return ToolResult(
            tool_name="convert_amount",
            data={},
            warnings=[f"Unknown from_unit '{from_unit}'. Valid: {sorted(_VALID_UNITS)}"],
        )
    if to_unit not in _VALID_UNITS:
        return ToolResult(
            tool_name="convert_amount",
            data={},
            warnings=[f"Unknown to_unit '{to_unit}'. Valid: {sorted(_VALID_UNITS)}"],
        )

    amount_d = Decimal(str(amount))
    paise_exact = (amount_d * _PAISE_PER[from_unit]).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    paise_int = int(paise_exact)

    if to_unit == "paise":
        result_value = float(paise_int)
        result_display = f"{paise_int} paise"
    else:
        result_d = Decimal(paise_int) / _PAISE_PER[to_unit]
        result_value = float(result_d.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))
        result_display = f"{result_value} {to_unit}"

    if paise_int < 0:
        warnings.append("Negative amount; verify sign is intentional.")

    return ToolResult(
        tool_name="convert_amount",
        query_params={"amount": amount, "from_unit": from_unit, "to_unit": to_unit},
        data={
            "result_paise": paise_int,
            "result_inr": format_inr(paise_int),
            "result_value": result_value,
            "result_unit": to_unit,
            "result_display": result_display,
        },
        warnings=warnings,
    )


async def run_percentage(
    session: AsyncSession | None,
    base_paise: int,
    percent: float,
) -> ToolResult:
    """
    Compute *percent*% of *base_paise*. Result rounded to nearest paise.
    Example: 15% of ₹2,00,000 (20000000 paise) → 3000000 paise (₹30,000).
    """
    result_paise = int(
        (Decimal(str(base_paise)) * Decimal(str(percent)) / Decimal("100"))
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    return ToolResult(
        tool_name="calculate_percentage",
        query_params={"base_paise": base_paise, "percent": percent},
        data={
            "result_paise": result_paise,
            "result_inr": format_inr(result_paise),
            "base_inr": format_inr(base_paise),
            "percent": percent,
            "description": (
                f"{percent}% of {format_inr(base_paise)} = {format_inr(result_paise)}"
            ),
        },
    )


async def run_growth(
    session: AsyncSession | None,
    from_paise: int,
    to_paise: int,
) -> ToolResult:
    """
    Compute absolute and percentage change from *from_paise* to *to_paise*.
    Returns direction: "up", "down", or "flat".
    """
    delta = to_paise - from_paise
    warnings: list[str] = []

    if from_paise == 0:
        pct_change: float | None = None
        warnings.append("from_paise is zero; percentage change is undefined.")
    else:
        pct_change = float(
            (Decimal(str(delta)) / Decimal(str(from_paise)) * Decimal("100"))
            .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )

    direction = "flat" if delta == 0 else ("up" if delta > 0 else "down")

    return ToolResult(
        tool_name="calculate_growth",
        query_params={"from_paise": from_paise, "to_paise": to_paise},
        data={
            "from_inr": format_inr(from_paise),
            "to_inr": format_inr(to_paise),
            "absolute_change_paise": delta,
            "absolute_change_inr": format_inr(abs(delta)),
            "percent_change": pct_change,
            "direction": direction,
        },
        warnings=warnings,
    )


async def run_compound_interest(
    session: AsyncSession | None,
    principal_paise: int,
    annual_rate_pct: float,
    years: float,
    compounding_frequency: int = 12,
) -> ToolResult:
    """
    Compound interest on a lump sum (FD / investment projection).
    Formula: A = P × (1 + r/n)^(n×t).
    compounding_frequency: 1=annual, 2=semi-annual, 4=quarterly, 12=monthly, 365=daily.
    """
    if compounding_frequency <= 0:
        return ToolResult(
            tool_name="calculate_compound_interest",
            data={},
            warnings=["compounding_frequency must be a positive integer."],
        )
    if annual_rate_pct < 0:
        return ToolResult(
            tool_name="calculate_compound_interest",
            data={},
            warnings=["annual_rate_pct must be non-negative."],
        )
    if years <= 0:
        return ToolResult(
            tool_name="calculate_compound_interest",
            data={},
            warnings=["years must be positive."],
        )

    rate_per_period = annual_rate_pct / 100.0 / compounding_frequency
    periods = compounding_frequency * years
    growth_factor = (1.0 + rate_per_period) ** periods

    maturity_paise = round(principal_paise * growth_factor)
    interest_paise = maturity_paise - principal_paise

    # Effective annual rate: (1 + r/n)^n − 1
    ear = round(((1.0 + rate_per_period) ** compounding_frequency - 1.0) * 100, 4)

    return ToolResult(
        tool_name="calculate_compound_interest",
        query_params={
            "principal_paise": principal_paise,
            "annual_rate_pct": annual_rate_pct,
            "years": years,
            "compounding_frequency": compounding_frequency,
        },
        data={
            "principal_inr": format_inr(principal_paise),
            "maturity_paise": maturity_paise,
            "maturity_inr": format_inr(maturity_paise),
            "interest_earned_paise": interest_paise,
            "interest_earned_inr": format_inr(interest_paise),
            "effective_annual_rate_pct": ear,
            "years": years,
        },
    )
