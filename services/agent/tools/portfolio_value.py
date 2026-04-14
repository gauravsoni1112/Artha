"""
portfolio_value — summarise investment holdings (MF, equity, FD, etc.).

Returns per-instrument detail with NAV, units, current value, and gain/loss
where purchase price is available.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import Holding
from libs.schemas.money import format_inr
from libs.telemetry.tracing import start_span
from services.agent.tools.base import ToolResult

log = structlog.get_logger(__name__)


async def run(
    session: AsyncSession,
    owner_id: str,
    asset_class: str | None = None,
) -> ToolResult:
    """Summarise investment portfolio. Optionally filter by asset class (MUTUAL_FUND, EQUITY, …)."""
    log.info("tool.portfolio_value.start", owner_id=owner_id, asset_class=asset_class)

    with start_span("tool.portfolio_value", {"owner_id": owner_id}):
        owner_uuid = uuid.UUID(owner_id)

        stmt = select(Holding).where(Holding.owner_id == owner_uuid)
        if asset_class:
            stmt = stmt.where(Holding.asset_class == asset_class.upper())

        stmt = stmt.order_by(Holding.asset_class, Holding.instrument_name)
        holdings = (await session.scalars(stmt)).all()

        instruments = []
        total_invested = 0
        total_current = 0

        for h in holdings:
            current = h.current_value_paise or 0
            purchased = h.purchase_price_paise or 0
            gain = current - purchased if purchased else None

            instruments.append(
                {
                    "instrument_name": h.instrument_name,
                    "asset_class": h.asset_class,
                    "isin": h.isin,
                    "units": float(h.units) if h.units is not None else None,
                    "nav_paise": h.nav_paise,
                    "nav_inr": format_inr(h.nav_paise) if h.nav_paise else None,
                    "current_value_paise": current,
                    "current_value_inr": format_inr(current),
                    "purchase_price_paise": purchased if purchased else None,
                    "purchase_price_inr": format_inr(purchased) if purchased else None,
                    "gain_loss_paise": gain,
                    "gain_loss_inr": format_inr(gain) if gain is not None else None,
                    "gain_loss_pct": round(gain / purchased * 100, 2) if purchased and gain is not None else None,
                    "valuation_date": h.valuation_date.isoformat() if h.valuation_date else None,
                }
            )
            total_current += current
            total_invested += purchased

        total_gain = total_current - total_invested if total_invested else None

        warnings = []
        if not instruments:
            warnings.append("No holdings found. Ingest a CAS statement to populate portfolio data.")

        log.info("tool.portfolio_value.complete", owner_id=owner_id, instrument_count=len(instruments))

        return ToolResult(
            tool_name="portfolio_value",
            query_params={"owner_id": owner_id, "asset_class": asset_class},
            data={
                "instrument_count": len(instruments),
                "instruments": instruments,
                "totals": {
                    "total_current_value_paise": total_current,
                    "total_current_value_inr": format_inr(total_current),
                    "total_invested_paise": total_invested,
                    "total_invested_inr": format_inr(total_invested),
                    "total_gain_loss_paise": total_gain,
                    "total_gain_loss_inr": format_inr(total_gain) if total_gain is not None else None,
                    "total_gain_loss_pct": round(total_gain / total_invested * 100, 2)
                    if total_invested and total_gain is not None
                    else None,
                },
            },
            warnings=warnings,
        )
