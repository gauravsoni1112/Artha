"""
upcoming_expenses — detect recurring expenses and predict next occurrences.

Identifies patterns by looking at transactions with the same (description, category, amount_paise)
that repeat at roughly monthly intervals. Projects the next occurrence date.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import Transaction
from libs.schemas.money import format_inr
from libs.telemetry.tracing import start_span
from services.agent.tools.base import ToolResult

log = structlog.get_logger(__name__)

# Transactions must appear at least this many times to be considered recurring
_MIN_OCCURRENCES = 2
# Monthly interval tolerance (days)
_INTERVAL_TOLERANCE_DAYS = 7


async def run(
    session: AsyncSession,
    owner_id: str,
    lookahead_days: int = 30,
) -> ToolResult:
    """Detect recurring expenses and predict upcoming ones within lookahead_days."""
    log.info("tool.upcoming_expenses.start", owner_id=owner_id, lookahead_days=lookahead_days)

    with start_span("tool.upcoming_expenses", {"owner_id": owner_id}):
        owner_uuid = uuid.UUID(owner_id)

        stmt = (
            select(Transaction)
            .where(
                Transaction.owner_id == owner_uuid,
                Transaction.transaction_type == "DEBIT",
            )
            .order_by(Transaction.transaction_date.asc())
        )
        rows = (await session.scalars(stmt)).all()

        # Group by (category, amount_paise) — description varies too much
        groups: dict[tuple, list[date]] = defaultdict(list)
        for r in rows:
            key = (r.category or "UNCATEGORIZED", r.amount_paise, r.raw_description[:40])
            groups[key].append(r.transaction_date)

        today = date.today()
        cutoff = today + timedelta(days=lookahead_days)

        recurring = []
        for (category, amount_paise, desc_prefix), dates in groups.items():
            if len(dates) < _MIN_OCCURRENCES:
                continue

            # Check if intervals are roughly monthly (28-35 days)
            intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
            avg_interval = sum(intervals) / len(intervals)
            if not (28 - _INTERVAL_TOLERANCE_DAYS <= avg_interval <= 35 + _INTERVAL_TOLERANCE_DAYS):
                continue

            last_date = dates[-1]
            next_date = last_date + timedelta(days=round(avg_interval))

            if today <= next_date <= cutoff:
                recurring.append(
                    {
                        "description_prefix": desc_prefix,
                        "category": category,
                        "amount_paise": amount_paise,
                        "amount_inr": format_inr(amount_paise),
                        "avg_interval_days": round(avg_interval),
                        "last_seen": last_date.isoformat(),
                        "predicted_next": next_date.isoformat(),
                        "occurrences": len(dates),
                    }
                )

        # Sort by predicted date
        recurring.sort(key=lambda x: x["predicted_next"])

        total_upcoming = sum(r["amount_paise"] for r in recurring)

        warnings = []
        if not recurring:
            warnings.append(
                f"No recurring expenses detected in the next {lookahead_days} days. "
                "Need at least 2 months of transaction history."
            )

        log.info("tool.upcoming_expenses.complete", owner_id=owner_id, upcoming_count=len(recurring))

        return ToolResult(
            tool_name="upcoming_expenses",
            query_params={"owner_id": owner_id, "lookahead_days": lookahead_days},
            data={
                "lookahead_days": lookahead_days,
                "upcoming_count": len(recurring),
                "upcoming_total_paise": total_upcoming,
                "upcoming_total_inr": format_inr(total_upcoming),
                "upcoming": recurring,
            },
            warnings=warnings,
        )
