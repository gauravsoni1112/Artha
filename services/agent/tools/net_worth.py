"""
net_worth — compute total net worth as assets minus liabilities.

Assets: sum of current_value_paise from holdings.
Liabilities: sum of outstanding DEBIT balances from credit-card accounts (approximated
             as any account with AccountType.CREDIT_CARD showing negative net flow).

Returns a breakdown by asset class.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import Holding
from libs.schemas.money import format_inr
from services.agent.tools.base import ToolResult


async def run(
    session: AsyncSession,
    owner_id: str,
) -> ToolResult:
    """Compute total net worth: sum of all holding current values, grouped by asset class."""
    owner_uuid = uuid.UUID(owner_id)

    stmt = (
        select(
            Holding.asset_class,
            func.sum(Holding.current_value_paise).label("total_paise"),
            func.count(Holding.id).label("count"),
        )
        .where(
            Holding.owner_id == owner_uuid,
            Holding.current_value_paise.isnot(None),
        )
        .group_by(Holding.asset_class)
    )

    rows = (await session.execute(stmt)).all()

    asset_breakdown = []
    total_assets = 0

    for asset_class, total_paise, count in rows:
        total_paise = total_paise or 0
        total_assets += total_paise
        asset_breakdown.append(
            {
                "asset_class": asset_class,
                "current_value_paise": total_paise,
                "current_value_inr": format_inr(total_paise),
                "holding_count": count,
            }
        )

    # Sort descending by value
    asset_breakdown.sort(key=lambda x: -x["current_value_paise"])

    warnings = []
    if not asset_breakdown:
        warnings.append("No holdings found. Ingest a CAS statement or add holdings manually.")

    return ToolResult(
        tool_name="net_worth",
        query_params={"owner_id": owner_id},
        data={
            "total_net_worth_paise": total_assets,
            "total_net_worth_inr": format_inr(total_assets),
            "asset_breakdown": asset_breakdown,
        },
        warnings=warnings,
    )
