"""
transaction_query — fetch transactions filtered by date range, category, or account.

Returns a paginated list of transactions with amounts in paise and INR.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import Transaction
from libs.schemas.money import format_inr
from services.agent.tools.base import ToolResult


async def run(
    session: AsyncSession,
    owner_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    account_id: str | None = None,
    limit: int = 50,
) -> ToolResult:
    """Fetch transactions for an owner filtered by date range, category, or account."""
    owner_uuid = uuid.UUID(owner_id)

    stmt = select(Transaction).where(Transaction.owner_id == owner_uuid)

    if start_date:
        stmt = stmt.where(Transaction.transaction_date >= date.fromisoformat(start_date))
    if end_date:
        stmt = stmt.where(Transaction.transaction_date <= date.fromisoformat(end_date))
    if category:
        stmt = stmt.where(Transaction.category == category.upper())
    if account_id:
        stmt = stmt.where(Transaction.account_id == uuid.UUID(account_id))

    stmt = stmt.order_by(Transaction.transaction_date.desc()).limit(limit)

    rows = (await session.scalars(stmt)).all()

    transactions = [
        {
            "id": str(r.id),
            "date": r.transaction_date.isoformat(),
            "description": r.raw_description,
            "category": r.category,
            "type": r.transaction_type,
            "amount_paise": r.amount_paise,
            "amount_inr": format_inr(r.amount_paise),
            "fiscal_year": r.fiscal_year,
            "account_id": str(r.account_id),
        }
        for r in rows
    ]

    total_credit = sum(r.amount_paise for r in rows if r.transaction_type == "CREDIT")
    total_debit = sum(r.amount_paise for r in rows if r.transaction_type == "DEBIT")

    return ToolResult(
        tool_name="transaction_query",
        query_params={
            "owner_id": owner_id,
            "start_date": start_date,
            "end_date": end_date,
            "category": category,
            "account_id": account_id,
            "limit": limit,
        },
        data={
            "count": len(transactions),
            "transactions": transactions,
            "summary": {
                "total_credit_paise": total_credit,
                "total_credit_inr": format_inr(total_credit),
                "total_debit_paise": total_debit,
                "total_debit_inr": format_inr(total_debit),
                "net_paise": total_credit - total_debit,
                "net_inr": format_inr(total_credit - total_debit),
            },
        },
    )
