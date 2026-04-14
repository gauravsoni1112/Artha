"""
budget_comparison — compare actual spending vs. budget for a period.

Queries transactions for the requested period and compares them to the
budgets defined in the financial_goals table (goals where category is set
are treated as monthly spending budgets).

If no goals exist, returns actuals only with a note that no budget is set.
"""

from __future__ import annotations

import uuid
from datetime import date

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import FinancialGoal, Transaction
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
    """Compare actual spending vs. budget targets for a period."""
    log.info("tool.budget_comparison.start", owner_id=owner_id)

    with start_span("tool.budget_comparison", {"owner_id": owner_id}):
        owner_uuid = uuid.UUID(owner_id)

        # ── Actuals ────────────────────────────────────────────────────
        actual_stmt = (
            select(
                Transaction.category,
                func.sum(Transaction.amount_paise).label("actual_paise"),
            )
            .where(
                Transaction.owner_id == owner_uuid,
                Transaction.transaction_type == "DEBIT",
            )
            .group_by(Transaction.category)
        )

        if fiscal_year:
            actual_stmt = actual_stmt.where(Transaction.fiscal_year == fiscal_year)
        else:
            if start_date:
                actual_stmt = actual_stmt.where(
                    Transaction.transaction_date >= date.fromisoformat(start_date)
                )
            if end_date:
                actual_stmt = actual_stmt.where(
                    Transaction.transaction_date <= date.fromisoformat(end_date)
                )

        actual_rows = (await session.execute(actual_stmt)).all()
        actuals: dict[str, int] = {
            (row.category or "UNCATEGORIZED"): int(row.actual_paise)
            for row in actual_rows
        }

        # ── Budgets from financial_goals ───────────────────────────────
        goal_stmt = select(FinancialGoal).where(
            FinancialGoal.owner_id == owner_uuid,
            FinancialGoal.is_active == True,  # noqa: E712
            FinancialGoal.category.isnot(None),
        )
        goals = (await session.execute(goal_stmt)).scalars().all()
        # target_amount_paise on a goal with a category = monthly budget
        budgets: dict[str, int] = {
            g.category: int(g.target_amount_paise) for g in goals if g.category
        }

        # ── Merge ──────────────────────────────────────────────────────
        all_categories = sorted(set(actuals) | set(budgets))
        comparison = []
        for cat in all_categories:
            actual = actuals.get(cat, 0)
            budget = budgets.get(cat, 0)
            over_budget = actual > budget if budget else None
            variance = actual - budget if budget else None
            comparison.append(
                {
                    "category": cat,
                    "actual_paise": actual,
                    "actual_inr": format_inr(actual),
                    "budget_paise": budget if budget else None,
                    "budget_inr": format_inr(budget) if budget else None,
                    "variance_paise": variance,
                    "variance_inr": format_inr(variance) if variance is not None else None,
                    "over_budget": over_budget,
                }
            )

        total_actual = sum(actuals.values())
        total_budget = sum(budgets.values())

        log.info(
            "tool.budget_comparison.complete",
            owner_id=owner_id,
            categories=len(comparison),
            has_budgets=bool(budgets),
        )

        return ToolResult(
            tool_name="budget_comparison",
            query_params={
                "owner_id": owner_id,
                "start_date": start_date,
                "end_date": end_date,
                "fiscal_year": fiscal_year,
            },
            data={
                "comparison": comparison,
                "total_actual_paise": total_actual,
                "total_actual_inr": format_inr(total_actual),
                "total_budget_paise": total_budget,
                "total_budget_inr": format_inr(total_budget) if total_budget else None,
                "has_budgets": bool(budgets),
            },
        )
