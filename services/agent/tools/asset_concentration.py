"""
asset_concentration — detect dangerous over-concentration in a single asset class.

Queries all holdings and computes what fraction of total portfolio value is held
in each asset class. Flags any class above *concentration_threshold_pct* (default 40 %).

Use-case: a portfolio with 80 % in a single equity or real-estate holding is a
significant risk the user may not be aware of.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import Holding
from libs.schemas.money import format_inr
from libs.telemetry.tracing import start_span
from services.agent.tools.base import ToolResult

log = structlog.get_logger(__name__)


async def run(
    session: AsyncSession,
    owner_id: str,
    concentration_threshold_pct: float = 40.0,
) -> ToolResult:
    """
    Compute portfolio concentration by asset class.
    Flags any asset class that exceeds *concentration_threshold_pct* % of total portfolio.
    """
    log.info("tool.asset_concentration.start", owner_id=owner_id)

    with start_span("tool.asset_concentration", {"owner_id": owner_id}):
        owner_uuid = uuid.UUID(owner_id)

        stmt = (
            select(
                Holding.asset_class,
                func.sum(Holding.current_value_paise).label("total_paise"),
            )
            .where(
                Holding.owner_id == owner_uuid,
                Holding.current_value_paise.isnot(None),
                Holding.current_value_paise > 0,
            )
            .group_by(Holding.asset_class)
        )

        rows = (await session.execute(stmt)).all()

        if not rows:
            return ToolResult(
                tool_name="asset_concentration",
                query_params={"owner_id": owner_id, "threshold_pct": concentration_threshold_pct},
                data={
                    "total_portfolio_paise": 0,
                    "total_portfolio_inr": format_inr(0),
                    "breakdown": [],
                    "concentrated_classes": [],
                    "is_concentrated": False,
                },
                warnings=["No holdings found. Ingest a CAS statement to analyse concentration."],
            )

        total_paise = sum(r.total_paise or 0 for r in rows)

        breakdown = []
        concentrated: list[str] = []

        for row in sorted(rows, key=lambda r: -(r.total_paise or 0)):
            value = row.total_paise or 0
            pct = round(value / total_paise * 100, 2) if total_paise else 0.0
            entry = {
                "asset_class": row.asset_class,
                "value_paise": value,
                "value_inr": format_inr(value),
                "concentration_pct": pct,
                "above_threshold": pct > concentration_threshold_pct,
            }
            breakdown.append(entry)
            if pct > concentration_threshold_pct:
                concentrated.append(row.asset_class)

        warnings = []
        if concentrated:
            names = ", ".join(concentrated)
            warnings.append(
                f"High concentration detected in: {names}. "
                f"Each exceeds {concentration_threshold_pct:.0f}% of total portfolio. "
                "Consider diversifying to reduce single-class risk."
            )

        log.info(
            "tool.asset_concentration.complete",
            owner_id=owner_id,
            concentrated_classes=concentrated,
        )

        return ToolResult(
            tool_name="asset_concentration",
            query_params={"owner_id": owner_id, "threshold_pct": concentration_threshold_pct},
            data={
                "total_portfolio_paise": total_paise,
                "total_portfolio_inr": format_inr(total_paise),
                "breakdown": breakdown,
                "concentrated_classes": concentrated,
                "is_concentrated": len(concentrated) > 0,
                "threshold_pct": concentration_threshold_pct,
            },
            warnings=warnings,
        )
