"""
goal_progress — query financial_goals and compute % completion.

Returns all active goals for the owner, including:
  - current vs. target amounts
  - % completion
  - days remaining to target_date (if set)
  - whether the goal is on track based on time elapsed
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import FinancialGoal
from libs.schemas.money import format_inr
from libs.telemetry.tracing import start_span
from services.agent.tools.base import ToolResult

log = structlog.get_logger(__name__)


async def run(
    session: AsyncSession,
    owner_id: str,
    goal_name: str | None = None,
) -> ToolResult:
    """Query financial goals and compute % completion and on-track status."""
    log.info("tool.goal_progress.start", owner_id=owner_id)

    with start_span("tool.goal_progress", {"owner_id": owner_id}):
        owner_uuid = uuid.UUID(owner_id)

        stmt = select(FinancialGoal).where(
            FinancialGoal.owner_id == owner_uuid,
            FinancialGoal.is_active == True,  # noqa: E712
        )
        if goal_name:
            stmt = stmt.where(FinancialGoal.goal_name.ilike(f"%{goal_name}%"))

        goals = (await session.execute(stmt)).scalars().all()

        today = date.today()
        result_goals = []

        for g in goals:
            target = int(g.target_amount_paise)
            current = int(g.current_amount_paise)
            pct_complete = round(current / target * 100, 2) if target else 0.0

            days_remaining: int | None = None
            on_track: bool | None = None

            if g.target_date:
                days_remaining = (g.target_date - today).days
                if days_remaining > 0 and g.created_at:
                    created = g.created_at.date() if hasattr(g.created_at, "date") else today
                    total_days = (g.target_date - created).days
                    if total_days > 0:
                        time_elapsed_pct = (today - created).days / total_days * 100
                        on_track = pct_complete >= time_elapsed_pct

            result_goals.append(
                {
                    "goal_name": g.goal_name,
                    "category": g.category,
                    "target_amount_paise": target,
                    "target_amount_inr": format_inr(target),
                    "current_amount_paise": current,
                    "current_amount_inr": format_inr(current),
                    "pct_complete": pct_complete,
                    "remaining_paise": max(0, target - current),
                    "remaining_inr": format_inr(max(0, target - current)),
                    "target_date": g.target_date.isoformat() if g.target_date else None,
                    "days_remaining": days_remaining,
                    "on_track": on_track,
                }
            )

        log.info("tool.goal_progress.complete", owner_id=owner_id, goals=len(result_goals))

        return ToolResult(
            tool_name="goal_progress",
            query_params={"owner_id": owner_id, "goal_name": goal_name},
            data={"goals": result_goals, "total_goals": len(result_goals)},
        )
