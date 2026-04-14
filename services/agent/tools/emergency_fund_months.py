"""
emergency_fund_months — compute how many months of expenses are covered by liquid savings.

Liquid balance is approximated as net flow (CREDIT - DEBIT) across all SAVINGS and
CURRENT accounts. Average monthly expense is computed from the last *expense_months*
months of DEBIT transactions (excluding loan/EMI repayments to avoid double-counting).

Rule-of-thumb:
  < 3 months → critical
  3–6 months → adequate
  > 6 months → healthy
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import Account, Transaction
from libs.schemas.money import format_inr
from libs.telemetry.tracing import start_span
from services.agent.tools.base import ToolResult

log = structlog.get_logger(__name__)

_LIQUID_ACCOUNT_TYPES = {"SAVINGS", "CURRENT", "savings", "current"}
_DEBT_CATEGORIES = {"LOAN_PAYMENT", "EMI", "CREDIT_CARD_PAYMENT", "LOAN"}


async def run(
    session: AsyncSession,
    owner_id: str,
    expense_months: int = 3,
) -> ToolResult:
    """
    Compute emergency fund coverage in months.
    Liquid balance = net flow on SAVINGS/CURRENT accounts.
    Avg monthly expense = mean of last *expense_months* months of DEBIT spend.
    """
    log.info("tool.emergency_fund_months.start", owner_id=owner_id)

    with start_span("tool.emergency_fund_months", {"owner_id": owner_id}):
        owner_uuid = uuid.UUID(owner_id)

        # ── Step 1: liquid account balance ───────────────────────────────
        liquid_account_ids_stmt = (
            select(Account.id)
            .where(
                Account.owner_id == owner_uuid,
                Account.account_type.in_(list(_LIQUID_ACCOUNT_TYPES)),
                Account.is_active == True,  # noqa: E712
            )
        )
        liquid_ids = list((await session.scalars(liquid_account_ids_stmt)).all())

        liquid_balance_paise = 0
        if liquid_ids:
            balance_stmt = (
                select(
                    Transaction.transaction_type,
                    func.sum(Transaction.amount_paise).label("total"),
                )
                .where(
                    Transaction.owner_id == owner_uuid,
                    Transaction.account_id.in_(liquid_ids),
                )
                .group_by(Transaction.transaction_type)
            )
            for txn_type, total in (await session.execute(balance_stmt)).all():
                total = total or 0
                if txn_type == "CREDIT":
                    liquid_balance_paise += total
                else:
                    liquid_balance_paise -= total

        liquid_balance_paise = max(0, liquid_balance_paise)

        # ── Step 2: average monthly non-debt expense ─────────────────────
        cutoff = date.today() - timedelta(days=expense_months * 30)
        expense_stmt = (
            select(func.sum(Transaction.amount_paise))
            .where(
                Transaction.owner_id == owner_uuid,
                Transaction.transaction_type == "DEBIT",
                Transaction.transaction_date >= cutoff,
                Transaction.category.notin_(list(_DEBT_CATEGORIES)),
            )
        )
        total_expense = (await session.scalar(expense_stmt)) or 0
        avg_monthly_expense = total_expense / expense_months if expense_months else 0

        # ── Step 3: compute coverage ─────────────────────────────────────
        months_covered = (
            round(liquid_balance_paise / avg_monthly_expense, 2)
            if avg_monthly_expense > 0
            else None
        )

        if months_covered is None:
            assessment = "insufficient_data"
            warnings = ["No expense data found for the period; cannot compute coverage."]
        elif months_covered < 3:
            assessment = "critical"
            warnings = [
                f"Emergency fund covers only {months_covered:.1f} months. "
                "Target: at least 6 months of expenses."
            ]
        elif months_covered < 6:
            assessment = "adequate"
            warnings = [
                f"Emergency fund covers {months_covered:.1f} months. "
                "Consider building to 6 months for a healthy buffer."
            ]
        else:
            assessment = "healthy"
            warnings = []

        log.info(
            "tool.emergency_fund_months.complete",
            owner_id=owner_id,
            months_covered=months_covered,
            assessment=assessment,
        )

        return ToolResult(
            tool_name="emergency_fund_months",
            query_params={"owner_id": owner_id, "expense_months": expense_months},
            data={
                "liquid_balance_paise": liquid_balance_paise,
                "liquid_balance_inr": format_inr(liquid_balance_paise),
                "avg_monthly_expense_paise": int(avg_monthly_expense),
                "avg_monthly_expense_inr": format_inr(int(avg_monthly_expense)),
                "months_covered": months_covered,
                "assessment": assessment,
                "target_months": 6,
                "shortfall_paise": max(
                    0,
                    int((6 - (months_covered or 0)) * avg_monthly_expense),
                ),
                "shortfall_inr": format_inr(
                    max(0, int((6 - (months_covered or 0)) * avg_monthly_expense))
                ),
            },
            warnings=warnings,
        )
