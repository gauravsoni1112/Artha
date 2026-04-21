"""
fetch_accounts — retrieve all bank accounts for an owner with transaction summaries.

Returns account details including type, institution, nickname, and transaction count.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import Account, Transaction
from libs.telemetry.tracing import start_span
from services.agent.tools.base import ToolResult

log = structlog.get_logger(__name__)


async def run(
    session: AsyncSession,
    owner_id: str,
    account_type: str | None = None,
) -> ToolResult:
    """
    Fetch all accounts for an owner with transaction summaries.

    Optionally filter by account type (e.g., BANK, CREDIT_CARD, INVESTMENT).
    """
    log.info("tool.fetch_accounts.start", owner_id=owner_id, account_type=account_type)

    with start_span("tool.fetch_accounts", {"owner_id": owner_id}):
        owner_uuid = uuid.UUID(owner_id)

        stmt = select(Account).where(Account.owner_id == owner_uuid)
        if account_type:
            stmt = stmt.where(Account.account_type == account_type.upper())

        stmt = stmt.order_by(Account.created_at.desc())

        accounts = (await session.scalars(stmt)).all()

        # Get transaction counts for each account
        accounts_data = []
        for account in accounts:
            txn_count_stmt = select(func.count(Transaction.id)).where(
                Transaction.account_id == account.id
            )
            txn_count = (await session.scalar(txn_count_stmt)) or 0

            accounts_data.append(
                {
                    "id": str(account.id),
                    "type": account.account_type,
                    "institution": account.institution,
                    "nickname": account.nickname or f"{account.institution} {account.account_type}",
                    "is_active": account.is_active,
                    "transaction_count": txn_count,
                    "created_at": account.created_at.isoformat(),
                }
            )

        log.info(
            "tool.fetch_accounts.complete",
            owner_id=owner_id,
            count=len(accounts_data),
        )

        return ToolResult(
            tool_name="fetch_accounts",
            query_params={
                "owner_id": owner_id,
                "account_type": account_type,
            },
            data={
                "count": len(accounts_data),
                "accounts": accounts_data,
            },
        )
