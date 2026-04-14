"""
debt_to_income — compute the debt-to-income (DTI) ratio from transaction history.

Methodology:
  - Monthly debt payments: average monthly spend in debt-related categories
    (LOAN_PAYMENT, EMI, CREDIT_CARD_PAYMENT) over the last *months* months.
  - Monthly gross income: average monthly CREDIT transactions over the same period.

DTI = (monthly_debt_payments / monthly_gross_income) × 100

Benchmarks (Indian personal finance norms):
  DTI < 30 %  → healthy
  DTI 30–40 % → caution — approaching limit
  DTI 40–50 % → elevated — review debt obligations
  DTI > 50 %  → critical — debt burden is high
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import Transaction
from libs.schemas.money import format_inr
from libs.telemetry.tracing import start_span
from services.agent.tools.base import ToolResult

log = structlog.get_logger(__name__)

_DEBT_CATEGORIES = {"LOAN_PAYMENT", "EMI", "CREDIT_CARD_PAYMENT", "LOAN"}


async def run(
    session: AsyncSession,
    owner_id: str,
    months: int = 3,
) -> ToolResult:
    """
    Compute debt-to-income ratio from the last *months* months of transaction data.
    Returns monthly debt payments, monthly income estimate, and DTI %.
    """
    log.info("tool.debt_to_income.start", owner_id=owner_id, months=months)

    with start_span("tool.debt_to_income", {"owner_id": owner_id}):
        owner_uuid = uuid.UUID(owner_id)
        cutoff = date.today() - timedelta(days=months * 30)

        # ── Monthly debt payments ────────────────────────────────────────
        debt_stmt = (
            select(func.sum(Transaction.amount_paise))
            .where(
                Transaction.owner_id == owner_uuid,
                Transaction.transaction_type == "DEBIT",
                Transaction.transaction_date >= cutoff,
                Transaction.category.in_(list(_DEBT_CATEGORIES)),
            )
        )
        total_debt = (await session.scalar(debt_stmt)) or 0
        avg_monthly_debt = total_debt / months if months else 0

        # ── Monthly income estimate (CREDIT transactions) ────────────────
        income_stmt = (
            select(func.sum(Transaction.amount_paise))
            .where(
                Transaction.owner_id == owner_uuid,
                Transaction.transaction_type == "CREDIT",
                Transaction.transaction_date >= cutoff,
            )
        )
        total_income = (await session.scalar(income_stmt)) or 0
        avg_monthly_income = total_income / months if months else 0

        # ── DTI ratio ────────────────────────────────────────────────────
        dti_pct: float | None = None
        if avg_monthly_income > 0:
            dti_pct = round(avg_monthly_debt / avg_monthly_income * 100, 2)

        warnings: list[str] = []
        if dti_pct is None:
            assessment = "insufficient_data"
            warnings.append("No income (CREDIT) transactions found; cannot compute DTI.")
        elif dti_pct < 30:
            assessment = "healthy"
        elif dti_pct < 40:
            assessment = "caution"
            warnings.append(
                f"DTI of {dti_pct:.1f}% is approaching the 40% caution threshold. "
                "Consider avoiding new debt obligations."
            )
        elif dti_pct < 50:
            assessment = "elevated"
            warnings.append(
                f"DTI of {dti_pct:.1f}% is elevated. Review existing debt obligations "
                "and avoid taking new loans."
            )
        else:
            assessment = "critical"
            warnings.append(
                f"DTI of {dti_pct:.1f}% is critical (>50%). Immediate debt restructuring "
                "or income augmentation is recommended."
            )

        log.info(
            "tool.debt_to_income.complete",
            owner_id=owner_id,
            dti_pct=dti_pct,
            assessment=assessment,
        )

        return ToolResult(
            tool_name="debt_to_income",
            query_params={"owner_id": owner_id, "months": months},
            data={
                "avg_monthly_debt_paise": int(avg_monthly_debt),
                "avg_monthly_debt_inr": format_inr(int(avg_monthly_debt)),
                "avg_monthly_income_paise": int(avg_monthly_income),
                "avg_monthly_income_inr": format_inr(int(avg_monthly_income)),
                "dti_pct": dti_pct,
                "assessment": assessment,
                "debt_categories_used": sorted(_DEBT_CATEGORIES),
                "period_months": months,
            },
            warnings=warnings,
        )
