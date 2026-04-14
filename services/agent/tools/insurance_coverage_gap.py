"""
insurance_coverage_gap — estimate life and health insurance coverage gap.

There is no dedicated insurance table in the current schema; this tool uses
Indian insurance industry heuristics applied to the user's income to estimate
recommended coverage and highlight any shortfall.

Heuristics (widely used by Indian financial planners):
  Life cover    : 10× annual income (term plan)
  Health cover  : ₹5 lakh minimum for individual; ₹10 lakh for family
                  Higher earners: annual_income × 0.1 subject to ₹5L–₹50L cap

The agent is expected to pass *annual_income_paise* extracted from the
user_profile context injected into each request. If 0 is passed, the tool
returns a warning and advisory-only output.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.money import format_inr
from libs.telemetry.tracing import start_span
from services.agent.tools.base import ToolResult

log = structlog.get_logger(__name__)

# Caps and floors in paise
_HEALTH_COVER_INDIVIDUAL_MIN = 500_000 * 100       # ₹5 lakh
_HEALTH_COVER_INDIVIDUAL_MAX = 5_000_000 * 100     # ₹50 lakh
_HEALTH_COVER_FAMILY_MIN     = 1_000_000 * 100     # ₹10 lakh
_HEALTH_COVER_FAMILY_MAX     = 5_000_000 * 100     # ₹50 lakh
_LIFE_MULTIPLIER             = 10


async def run(
    session: AsyncSession,
    owner_id: str,
    annual_income_paise: int = 0,
    is_family_scope: bool = False,
    existing_life_cover_paise: int = 0,
    existing_health_cover_paise: int = 0,
) -> ToolResult:
    """
    Estimate life and health insurance coverage gap based on annual income.
    Pass annual_income_paise from the user profile. Returns recommended cover,
    existing cover (if provided), and gap amounts.
    """
    log.info(
        "tool.insurance_coverage_gap.start",
        owner_id=owner_id,
        annual_income_paise=annual_income_paise,
        is_family_scope=is_family_scope,
    )

    with start_span("tool.insurance_coverage_gap", {"owner_id": owner_id}):
        warnings: list[str] = []

        if annual_income_paise <= 0:
            warnings.append(
                "annual_income_paise not provided or is zero; "
                "returning advisory estimates only. "
                "Pass the user's annual income for a personalised gap analysis."
            )
            annual_income_paise = 0

        # ── Recommended life cover ───────────────────────────────────────
        recommended_life_paise = annual_income_paise * _LIFE_MULTIPLIER

        life_gap_paise = max(0, recommended_life_paise - existing_life_cover_paise)

        # ── Recommended health cover ─────────────────────────────────────
        if is_family_scope:
            floor = _HEALTH_COVER_FAMILY_MIN
            cap = _HEALTH_COVER_FAMILY_MAX
        else:
            floor = _HEALTH_COVER_INDIVIDUAL_MIN
            cap = _HEALTH_COVER_INDIVIDUAL_MAX

        income_based_health = int(annual_income_paise * 0.1)
        recommended_health_paise = max(floor, min(cap, income_based_health)) if annual_income_paise > 0 else floor

        health_gap_paise = max(0, recommended_health_paise - existing_health_cover_paise)

        # ── Warnings ─────────────────────────────────────────────────────
        if life_gap_paise > 0 and annual_income_paise > 0:
            warnings.append(
                f"Life insurance gap of {format_inr(life_gap_paise)} detected. "
                f"Recommended: {format_inr(recommended_life_paise)} (10× annual income). "
                "Consider a term plan to bridge this gap."
            )
        if health_gap_paise > 0:
            label = "family floater" if is_family_scope else "individual"
            warnings.append(
                f"Health insurance gap of {format_inr(health_gap_paise)} for {label} cover. "
                f"Recommended minimum: {format_inr(recommended_health_paise)}."
            )

        log.info(
            "tool.insurance_coverage_gap.complete",
            owner_id=owner_id,
            life_gap_paise=life_gap_paise,
            health_gap_paise=health_gap_paise,
        )

        return ToolResult(
            tool_name="insurance_coverage_gap",
            query_params={
                "owner_id": owner_id,
                "annual_income_paise": annual_income_paise,
                "is_family_scope": is_family_scope,
            },
            data={
                "life_cover": {
                    "recommended_paise": recommended_life_paise,
                    "recommended_inr": format_inr(recommended_life_paise),
                    "existing_paise": existing_life_cover_paise,
                    "existing_inr": format_inr(existing_life_cover_paise),
                    "gap_paise": life_gap_paise,
                    "gap_inr": format_inr(life_gap_paise),
                    "is_adequate": life_gap_paise == 0,
                },
                "health_cover": {
                    "recommended_paise": recommended_health_paise,
                    "recommended_inr": format_inr(recommended_health_paise),
                    "existing_paise": existing_health_cover_paise,
                    "existing_inr": format_inr(existing_health_cover_paise),
                    "gap_paise": health_gap_paise,
                    "gap_inr": format_inr(health_gap_paise),
                    "is_adequate": health_gap_paise == 0,
                    "is_family_scope": is_family_scope,
                },
                "annual_income_paise": annual_income_paise,
                "annual_income_inr": format_inr(annual_income_paise),
                "methodology": "10x_income_life_0.1x_income_health",
            },
            warnings=warnings,
        )
