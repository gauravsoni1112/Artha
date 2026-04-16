"""
Transactions router.

GET /owners/{owner_id}/transactions          — paginated transaction list with filters
GET /owners/{owner_id}/transactions.csv      — CSV export (streaming)
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.deps import current_owner
from libs.schemas.db_models import Owner, Transaction

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/owners/{owner_id}/transactions", tags=["transactions"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TransactionOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    account_id: uuid.UUID
    transaction_date: date
    amount_paise: int
    transaction_type: str
    category: str | None
    description: str
    merchant: str | None
    fiscal_year: str
    currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_access(requesting_owner: Owner, target_owner_id: uuid.UUID) -> None:
    from fastapi import HTTPException, status
    if not requesting_owner.is_admin and requesting_owner.id != target_owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _apply_filters(
    q,
    account_id: uuid.UUID | None,
    category: str | None,
    date_from: date | None,
    date_to: date | None,
    transaction_type: str | None,
    search: str | None,
):
    if account_id is not None:
        q = q.where(Transaction.account_id == account_id)
    if category is not None:
        q = q.where(Transaction.category == category)
    if date_from is not None:
        q = q.where(Transaction.transaction_date >= date_from)
    if date_to is not None:
        q = q.where(Transaction.transaction_date <= date_to)
    if transaction_type is not None:
        q = q.where(Transaction.transaction_type == transaction_type)
    if search is not None:
        q = q.where(Transaction.description.ilike(f"%{search}%"))
    return q


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[TransactionOut])
async def list_transactions(
    owner_id: uuid.UUID,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
    account_id: uuid.UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    transaction_type: str | None = Query(default=None, pattern="^(CREDIT|DEBIT)$"),
    search: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[TransactionOut]:
    _check_access(requesting_owner, owner_id)

    q = select(Transaction).where(Transaction.owner_id == owner_id)
    q = _apply_filters(q, account_id, category, date_from, date_to, transaction_type, search)
    q = q.order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
    q = q.offset(offset).limit(limit)

    result = await session.execute(q)
    return result.scalars().all()


@router.get(".csv")
async def export_transactions_csv(
    owner_id: uuid.UUID,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
    account_id: uuid.UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    transaction_type: str | None = Query(default=None, pattern="^(CREDIT|DEBIT)$"),
    search: str | None = Query(default=None, max_length=128),
) -> StreamingResponse:
    """Stream transactions as a CSV file. No pagination — exports all matching rows."""
    _check_access(requesting_owner, owner_id)

    q = select(Transaction).where(Transaction.owner_id == owner_id)
    q = _apply_filters(q, account_id, category, date_from, date_to, transaction_type, search)
    q = q.order_by(Transaction.transaction_date.desc())

    result = await session.execute(q)
    transactions = result.scalars().all()

    def _generate_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "transaction_date", "amount_paise", "amount_inr",
            "transaction_type", "category", "description", "merchant",
            "fiscal_year", "account_id", "currency",
        ])
        buf.seek(0)
        yield buf.read()

        for tx in transactions:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                str(tx.id),
                tx.transaction_date.isoformat(),
                tx.amount_paise,
                f"{tx.amount_paise / 100:.2f}",  # display only — never compute in float elsewhere
                tx.transaction_type,
                tx.category or "",
                tx.description,
                tx.merchant or "",
                tx.fiscal_year,
                str(tx.account_id),
                tx.currency,
            ])
            buf.seek(0)
            yield buf.read()

    filename = f"transactions_{owner_id}_{date.today().isoformat()}.csv"
    return StreamingResponse(
        _generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
