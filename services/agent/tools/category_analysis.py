"""
category_analysis — spending breakdown by category for a given period.

Groups transactions by category, computes totals and percentages.
Supports filtering by date range or fiscal year.
"""

from __future__ import annotations

import uuid
from datetime import date

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import Transaction
from libs.schemas.money import format_inr
from libs.telemetry.tracing import start_span
from services.agent.tools.base import ToolResult

log = structlog.get_logger(__name__)


async def run(
    session: AsyncSession,
    owner_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    fiscal_year: str | None = None,
) -> ToolResult:
    """Analyse spending by category. Returns per-category totals and % of spend."""
    log.info("tool.category_analysis.start", owner_id=owner_id, fiscal_year=fiscal_year)

    with start_span("tool.category_analysis", {"owner_id": owner_id}):
        owner_uuid = uuid.UUID(owner_id)

        stmt = (
            select(
                Transaction.category,
                Transaction.transaction_type,
                func.sum(Transaction.amount_paise).label("total_paise"),
                func.count(Transaction.id).label("count"),
            )
            .where(Transaction.owner_id == owner_uuid)
            .group_by(Transaction.category, Transaction.transaction_type)
        )

        if fiscal_year:
            stmt = stmt.where(Transaction.fiscal_year == fiscal_year)
        else:
            if start_date:
                stmt = stmt.where(Transaction.transaction_date >= date.fromisoformat(start_date))
            if end_date:
                stmt = stmt.where(Transaction.transaction_date <= date.fromisoformat(end_date))

        rows = (await session.execute(stmt)).all()

        # Separate credit and debit buckets
        debit_by_category: dict[str, int] = {}
        credit_by_category: dict[str, int] = {}

        for category, txn_type, total_paise, count in rows:
            cat = category or "UNCATEGORIZED"
            if txn_type == "DEBIT":
                debit_by_category[cat] = debit_by_category.get(cat, 0) + total_paise
            else:
                credit_by_category[cat] = credit_by_category.get(cat, 0) + total_paise

        total_debit = sum(debit_by_category.values())

        breakdown = []
        for cat, paise in sorted(debit_by_category.items(), key=lambda x: -x[1]):
            pct = round(paise / total_debit * 100, 2) if total_debit else 0.0
            breakdown.append(
                {
                    "category": cat,
                    "amount_paise": paise,
                    "amount_inr": format_inr(paise),
                    "pct_of_spend": pct,
                }
            )

        total_credit = sum(credit_by_category.values())

        log.info(
            "tool.category_analysis.complete",
            owner_id=owner_id,
            category_count=len(breakdown),
        )

        return ToolResult(
            tool_name="category_analysis",
            query_params={
                "owner_id": owner_id,
                "start_date": start_date,
                "end_date": end_date,
                "fiscal_year": fiscal_year,
            },
            data={
                "spend_breakdown": breakdown,
                "total_spend_paise": total_debit,
                "total_spend_inr": format_inr(total_debit),
                "total_income_paise": total_credit,
                "total_income_inr": format_inr(total_credit),
                "savings_paise": total_credit - total_debit,
                "savings_inr": format_inr(total_credit - total_debit),
            },
        )
