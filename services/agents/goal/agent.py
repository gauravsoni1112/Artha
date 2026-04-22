"""
GoalAgent — financial goal tracking and planning domain.

Tools exposed:
  - goal_progress      : % completion, on-track status for all active goals
  - upcoming_expenses  : predicted recurring expenses to plan around goal savings
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from services.agent.tools.registry import GoalProgressInput, UpcomingExpensesInput
from services.agent.tools.goal_progress import run as goal_progress_run
from services.agent.tools.upcoming_expenses import run as upcoming_expenses_run
from services.agents._common.base_agent import BaseAgent

_GOAL_TOOLS: list[tuple] = [
    ("goal_progress", goal_progress_run, GoalProgressInput),
    ("upcoming_expenses", upcoming_expenses_run, UpcomingExpensesInput),
]


class GoalAgent(BaseAgent):
    """Domain agent for financial goal tracking and planning."""

    AGENT_ID = "goal_agent"
    CAPABILITIES = ["goal", "planning", "savings"]

    def _build_tools(self, owner_id: str) -> list[StructuredTool]:
        return [
            StructuredTool(
                name=name,
                description=fn.__doc__ or name,
                args_schema=schema,
                coroutine=self._make_tool_bound(fn, owner_id),
            )
            for name, fn, schema in _GOAL_TOOLS
        ]
