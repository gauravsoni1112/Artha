"""
spending_trend — month-over-month spending trend for a category (or all).

Returns monthly totals for the requested category over the last N months,
sorted chronologically, so the LLM can describe trends and compute changes.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import structlog
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import Transaction
from libs.schemas.money import format_inr
from libs.telemetry.tracing import start_span
from services.agent.tools.base import ToolResult

log = structlog.get_logger(__name__)


async def run(
    session: AsyncSession,
    owner_id: str,
    category: str | None = None,
    months: int = 6,
) -> ToolResult:
    """Month-over-month spending trend for a category over the last N months."""
    log.info("tool.spending_trend.start", owner_id=owner_id, category=category, months=months)

    with start_span("tool.spending_trend", {"owner_id": owner_id}):
        owner_uuid = uuid.UUID(owner_id)
        today = date.today()
        # Start of the window: first day of (today - months) month
        start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        for _ in range(months - 1):
            start = (start - timedelta(days=1)).replace(day=1)

        stmt = (
            select(
                extract("year", Transaction.transaction_date).label("year"),
                extract("month", Transaction.transaction_date).label("month"),
                func.sum(Transaction.amount_paise).label("total_paise"),
                func.count(Transaction.id).label("count"),
            )
            .where(
                Transaction.owner_id == owner_uuid,
                Transaction.transaction_type == "DEBIT",
                Transaction.transaction_date >= start,
                Transaction.transaction_date <= today,
            )
            .group_by("year", "month")
            .order_by("year", "month")
        )

        if category:
            stmt = stmt.where(Transaction.category == category.upper())

        rows = (await session.execute(stmt)).all()

        monthly = []
        for year, month, total_paise, count in rows:
            monthly.append(
                {
                    "period": f"{int(year):04d}-{int(month):02d}",
                    "amount_paise": int(total_paise),
                    "amount_inr": format_inr(int(total_paise)),
                    "transaction_count": int(count),
                }
            )

        # Compute MoM deltas
        for i in range(1, len(monthly)):
            prev = monthly[i - 1]["amount_paise"]
            curr = monthly[i]["amount_paise"]
            if prev:
                monthly[i]["mom_change_pct"] = round((curr - prev) / prev * 100, 2)
            else:
                monthly[i]["mom_change_pct"] = None

        log.info("tool.spending_trend.complete", owner_id=owner_id, periods=len(monthly))

        return ToolResult(
            tool_name="spending_trend",
            query_params={"owner_id": owner_id, "category": category, "months": months},
            data={"monthly_trend": monthly, "category": category or "ALL"},
        )
