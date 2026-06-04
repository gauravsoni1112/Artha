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
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence that this decomposition correctly captures the user's intent (0–1).",
    )
    confidence_reason: str = Field(
        default="",
        description="Brief explanation of the confidence score — what is ambiguous or uncertain, if anything.",
    )

    @classmethod
    def trivial(cls, question: str) -> "Plan":
        """Single-step plan — used for simple questions that need no decomposition."""
        return cls(
            steps=[question],
            reasoning="Single-step question; no decomposition needed.",
            confidence=1.0,
            confidence_reason="Unambiguous single-step query.",
        )


# ── Planner prompt ────────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """\
You are a financial query planner. Given a user question, decide whether it
requires multiple information-gathering steps.

Output ONLY valid JSON matching this schema (no markdown, no explanation):
{
  "steps": ["<sub-question or action 1>", "<sub-question or action 2>", ...],
  "reasoning": "<why you decomposed it this way>",
  "confidence": <float 0.0–1.0>,
  "confidence_reason": "<what is ambiguous or uncertain; 'Unambiguous query.' if nothing>"
}

Rules:
- If the question is simple (single data lookup), return a single step.
- Split into 2–4 steps when the question:
  - Uses "vs", "compare", "trend", "versus", or compares two time periods.
  - Asks about multiple financial domains (e.g. goals AND spending, net worth
    AND investments).
  - Requests an overall financial health assessment.
  - Asks "Am I saving enough?", "What is my biggest risk?", or similar
    multi-domain advisory questions.
- Each step MUST be answerable by at least one of these tools:
  fetch_accounts, transaction_query, category_analysis, spending_trend,
  net_worth, portfolio_value, tax_summary, upcoming_expenses, goal_progress,
  emergency_fund_months, asset_concentration, debt_to_income,
  insurance_coverage_gap, budget_comparison.
  (arithmetic tools — convert_amount, calculate_percentage, calculate_growth,
   calculate_compound_interest — are called within steps, not as plan targets)
- Do NOT generate steps that require human judgment or external data not
  available through the tools above.
- Maximum 4 steps.

Confidence scoring guide:
  1.0 — Query is unambiguous; the decomposition is the only sensible one.
  0.8 — Query is mostly clear; one minor ambiguity (e.g. which month to use).
  0.6 — Query is partially ambiguous; an assumption was required (e.g. "this year" vs fiscal year).
  0.4 — Query is vague or uses jargon that required interpretation.
  0.2 — Query is too open-ended; this decomposition is a best guess.

Examples:
Simple query → 1 step:
  Q: "What did I spend on food this month?"
  {"steps": ["What did I spend on food this month?"], "reasoning": "Single category lookup.", "confidence": 1.0, "confidence_reason": "Unambiguous query."}

Multi-step query → 2 steps:
  Q: "How does my spending compare to last month?"
  {"steps": ["What was my category spending this month?", "What was my category spending last month?"], "reasoning": "Comparison requires two separate period queries.", "confidence": 1.0, "confidence_reason": "Unambiguous comparison; both periods are well-defined."}

Multi-domain query → 3 steps (with ambiguity):
  Q: "Am I saving enough for retirement?"
  {"steps": ["What is my progress toward savings goals?", "What is my current net worth?", "What is my 6-month spending trend?"], "reasoning": "Retirement readiness needs goals, net worth, and spending trajectory.", "confidence": 0.6, "confidence_reason": "Assumed 'saving enough' means goal progress + net worth; no explicit retirement goal may exist."}
"""


# ── Planner node ──────────────────────────────────────────────────────────────

class PlannerNode:
    """
    LangGraph-compatible node that converts a user message into a Plan.

    Usage inside a StateGraph:
        planner = PlannerNode(llm=chat_model)
        graph.add_node("planner", planner)
    """

    def __init__(self, llm: Any) -> None:
        self._llm = llm
        self._structured_llm = llm.with_structured_output(Plan)

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

    async def acall(self, state: dict, **kwargs) -> dict:
        """Async node callable."""
        messages = state.get("messages", [])
        callbacks = kwargs.get("callbacks", [])
        last_human = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)),
            None,
        )
        question = last_human.content if last_human else ""
        plan = await self._aplan(question, callbacks=callbacks)
        log.info("planner.produced", steps=len(plan.steps), reasoning=plan.reasoning)
        return {"plan": plan, "messages": messages}

    def _plan(self, question: str) -> Plan:
        prompt = [
            SystemMessage(content=_PLANNER_SYSTEM),
            HumanMessage(content=question),
        ]
        try:
            return self._structured_llm.invoke(prompt)
        except Exception as exc:
            log.warning("planner.parse_failed", error=str(exc))
            return Plan.trivial(question)

    async def _aplan(self, question: str, callbacks: list | None = None) -> Plan:
        prompt = [
            SystemMessage(content=_PLANNER_SYSTEM),
            HumanMessage(content=question),
        ]
        lf_config = {"callbacks": callbacks} if callbacks else {}
        try:
            return await self._structured_llm.ainvoke(prompt, config=lf_config)
        except Exception as exc:
            log.warning("planner.parse_failed", error=str(exc))
            return Plan.trivial(question)
