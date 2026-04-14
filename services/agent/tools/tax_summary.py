"""
tax_summary — ITR and tax data summary per fiscal year.

Reads from the tax_data table (populated from ITR uploads or manual entry).
Falls back to computing estimated taxable income from the transactions table
if no explicit tax record exists.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import TaxData, Transaction
from libs.schemas.money import format_inr
from libs.telemetry.tracing import start_span
from services.agent.tools.base import ToolResult

log = structlog.get_logger(__name__)


async def run(
    session: AsyncSession,
    owner_id: str,
    fiscal_year: str | None = None,
) -> ToolResult:
    """Return ITR/tax summary per fiscal year. If no explicit record, estimates from transactions."""
    log.info("tool.tax_summary.start", owner_id=owner_id, fiscal_year=fiscal_year)

    with start_span("tool.tax_summary", {"owner_id": owner_id}):
        owner_uuid = uuid.UUID(owner_id)

        stmt = select(TaxData).where(TaxData.owner_id == owner_uuid)
        if fiscal_year:
            stmt = stmt.where(TaxData.fiscal_year == fiscal_year)
        stmt = stmt.order_by(TaxData.fiscal_year.desc())

        tax_rows = (await session.scalars(stmt)).all()

        summaries = [
            {
                "fiscal_year": t.fiscal_year,
                "gross_income_paise": t.gross_income_paise,
                "gross_income_inr": format_inr(t.gross_income_paise) if t.gross_income_paise else None,
                "taxable_income_paise": t.taxable_income_paise,
                "taxable_income_inr": format_inr(t.taxable_income_paise) if t.taxable_income_paise else None,
                "tax_paid_paise": t.tax_paid_paise,
                "tax_paid_inr": format_inr(t.tax_paid_paise) if t.tax_paid_paise else None,
                "tds_paise": t.tds_paise,
                "tds_inr": format_inr(t.tds_paise) if t.tds_paise else None,
                "itr_filed": t.itr_filed,
                "source": "itr_record",
            }
            for t in tax_rows
        ]

        warnings = []

        # If no explicit records, estimate from SALARY credits in transactions
        if not tax_rows:
            fy_filter = [Transaction.fiscal_year == fiscal_year] if fiscal_year else []
            est_stmt = (
                select(
                    Transaction.fiscal_year,
                    func.sum(Transaction.amount_paise).label("total_credits"),
                )
                .where(
                    Transaction.owner_id == owner_uuid,
                    Transaction.transaction_type == "CREDIT",
                    Transaction.category == "SALARY",
                    *fy_filter,
                )
                .group_by(Transaction.fiscal_year)
                .order_by(Transaction.fiscal_year.desc())
            )
            est_rows = (await session.execute(est_stmt)).all()

            for fy, total in est_rows:
                summaries.append(
                    {
                        "fiscal_year": fy,
                        "gross_income_paise": total,
                        "gross_income_inr": format_inr(total),
                        "taxable_income_paise": None,
                        "taxable_income_inr": None,
                        "tax_paid_paise": None,
                        "tax_paid_inr": None,
                        "tds_paise": None,
                        "tds_inr": None,
                        "itr_filed": False,
                        "source": "estimated_from_salary_credits",
                    }
                )

            if not summaries:
                warnings.append("No tax records or salary credits found. Upload ITR data to populate.")
            else:
                warnings.append("Tax data estimated from SALARY credit transactions — not from actual ITR.")

        log.info("tool.tax_summary.complete", owner_id=owner_id, fiscal_year_count=len(summaries))

        return ToolResult(
            tool_name="tax_summary",
            query_params={"owner_id": owner_id, "fiscal_year": fiscal_year},
            data={"fiscal_years": summaries},
            warnings=warnings,
        )
