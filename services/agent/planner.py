"""
Phase 3 — Planner node.

Given a user question, the planner decomposes it into an ordered list of
sub-questions that the executor loop resolves one by one before synthesising
a final answer.

The planner uses structured output (JSON) so the result is always parseable
even if the underlying LLM adds surrounding text.

Graph topology (Phase 3):

  START → planner → executor_loop → END

The executor_loop is the Phase-2 assistant↔tools sub-graph, invoked once per
plan step and collecting observations.  When the plan has a single trivial
step the planner just passes it through, so simple queries remain fast.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)

# ── Plan schema ───────────────────────────────────────────────────────────────

class Plan(BaseModel):
    """Decomposed execution plan produced by the planner node."""

    steps: list[str] = Field(
        description="Ordered list of sub-questions or actions to resolve.",
        min_length=1,
    )
    reasoning: str = Field(
        description="Why this decomposition is needed for the original question.",
    )

    @classmethod
    def trivial(cls, question: str) -> "Plan":
        """Single-step plan — used for simple questions that need no decomposition."""
        return cls(steps=[question], reasoning="Single-step question; no decomposition needed.")


# ── Planner prompt ────────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """\
You are a financial query planner.  Given a user question, decide whether it
requires multiple information-gathering steps.

Output ONLY valid JSON matching this schema (no markdown, no explanation):
{
  "steps": ["<sub-question or action 1>", "<sub-question or action 2>", ...],
  "reasoning": "<why you decomposed it this way>"
}

Rules:
- If the question is simple (single data lookup), return a single step.
- If the question compares two periods, uses the word "vs", "compare", "trend",
  "versus", or asks about multiple categories, produce 2–4 steps.
- Each step must be a self-contained question answerable by a financial tool.
- Always include the owner_id token in each step so tools can resolve it.
- Maximum 4 steps.
"""


# ── Planner node ──────────────────────────────────────────────────────────────

class PlannerNode:
    """
    LangGraph-compatible node that converts a user message into a Plan.

    Usage inside a StateGraph:
        planner = PlannerNode(llm=chat_model)
        graph.add_node("planner", planner)
    """

    # Regex to extract JSON even if the LLM wraps it in markdown fences
    _JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    def __call__(self, state: dict) -> dict:
        """Synchronous node callable for LangGraph (sync graph compile)."""
        messages = state.get("messages", [])
        last_human = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)),
            None,
        )
        question = last_human.content if last_human else ""
        plan = self._plan(question)
        log.info("planner.produced", steps=len(plan.steps), reasoning=plan.reasoning)
        return {"plan": plan, "messages": messages}

    async def acall(self, state: dict) -> dict:
        """Async node callable."""
        messages = state.get("messages", [])
        last_human = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)),
            None,
        )
        question = last_human.content if last_human else ""
        plan = await self._aplan(question)
        log.info("planner.produced", steps=len(plan.steps), reasoning=plan.reasoning)
        return {"plan": plan, "messages": messages}

    def _plan(self, question: str) -> Plan:
        prompt = [
            SystemMessage(content=_PLANNER_SYSTEM),
            HumanMessage(content=question),
        ]
        response = self._llm.invoke(prompt)
        return self._parse_response(response.content, question)

    async def _aplan(self, question: str) -> Plan:
        prompt = [
            SystemMessage(content=_PLANNER_SYSTEM),
            HumanMessage(content=question),
        ]
        response = await self._llm.ainvoke(prompt)
        return self._parse_response(response.content, question)

    def _parse_response(self, content: str, original_question: str) -> Plan:
        """Parse JSON from LLM output, falling back to a trivial plan on error."""
        match = self._JSON_RE.search(content)
        if not match:
            log.warning("planner.parse_failed", raw=content[:200])
            return Plan.trivial(original_question)
        try:
            data = json.loads(match.group())
            return Plan(**data)
        except Exception as exc:
            log.warning("planner.invalid_json", error=str(exc), raw=content[:200])
            return Plan.trivial(original_question)
