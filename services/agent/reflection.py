"""
Phase 3 — Reflection / self-critique node.

After the executor_loop produces per-step observations, the ReflectionNode
evaluates whether the answer is complete and confident:

  - Parses a JSON verdict from the LLM containing confidence_score (0–1)
    and optional reflection_notes.
  - If confidence is below REFLECTION_THRESHOLD and iterations remain,
    it marks the state for re-execution (needs_rerun=True) so the graph
    can loop back to the executor.
  - At most MAX_REFLECT_ITERATIONS re-runs are attempted (env var, default 2).

The reflection result is stored on AgentRun via confidence_score and
reflection_notes columns added in migration 0003.
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

REFLECTION_THRESHOLD: float = float(os.getenv("REFLECTION_THRESHOLD", "0.7"))
MAX_REFLECT_ITERATIONS: int = int(os.getenv("MAX_REFLECT_ITERATIONS", "2"))


class _LLMReflection(BaseModel):
    """Schema for the structured output returned by the reflection LLM."""

    confidence_score: float = Field(ge=0.0, le=1.0)
    is_complete: bool
    reflection_notes: str


_REFLECTION_SYSTEM = """\
You are a financial answer quality evaluator.

Given a user question and the assistant's draft answer, rate how complete and
accurate the answer is. Output ONLY valid JSON (no markdown, no explanation):

{
  "confidence_score": <float between 0.0 and 1.0>,
  "is_complete": <true|false>,
  "reflection_notes": "<brief note — what is missing or uncertain, or 'Answer is complete.' if nothing>"
}

Quality checks to apply:
1. Does the answer directly state the key figure the user asked for (amount, %, date)?
2. If the user asked about a time range, does the answer confirm which range was queried?
3. Are all ₹ amounts plausibly from tool data (not computed inline)?
4. If the answer is "no data available", does it explain what data is missing and why?

Scoring guide:
  1.0 — All figures present, time range confirmed, data clearly sourced.
  0.8 — Key figure present; minor gap (e.g. no data freshness citation).
  0.6 — Partial answer; key figure present but time range or sourcing unclear.
  0.4 — Answer is vague or hedged without citing tool results.
  0.0 — No useful answer or the answer appears to compute figures inline.

Be strict: if the answer says "data unavailable" without explaining why,
score ≤ 0.4.
"""


# ── ReflectionResult ─────────────────────────────────────────────────────────

class ReflectionResult:
    """Parsed output of one reflection pass."""

    __slots__ = ("confidence_score", "is_complete", "reflection_notes", "needs_rerun")

    def __init__(
        self,
        confidence_score: float,
        is_complete: bool,
        reflection_notes: str,
        needs_rerun: bool,
    ) -> None:
        self.confidence_score = confidence_score
        self.is_complete = is_complete
        self.reflection_notes = reflection_notes
        self.needs_rerun = needs_rerun

    @classmethod
    def high_confidence(cls) -> "ReflectionResult":
        return cls(
            confidence_score=1.0,
            is_complete=True,
            reflection_notes="Answer is complete.",
            needs_rerun=False,
        )

    @classmethod
    def fallback(cls) -> "ReflectionResult":
        """Used when the LLM returns unparseable output."""
        return cls(
            confidence_score=0.5,
            is_complete=True,
            reflection_notes="Reflection parse failed; proceeding with current answer.",
            needs_rerun=False,
        )


# ── ReflectionNode ────────────────────────────────────────────────────────────

class ReflectionNode:
    """
    LangGraph-compatible node that critiques the executor_loop's answer.

    State keys consumed:
        messages          — full message list (last AI message = draft answer)
        step_observations — per-step answers from executor_loop
        reflect_count     — number of reflection iterations so far (int, default 0)

    State keys produced:
        confidence_score  — float 0–1
        reflection_notes  — str
        needs_rerun       — bool (True → graph should loop back to executor)
        reflect_count     — incremented
    """

    def __init__(self, llm: Any) -> None:
        self._llm = llm
        self._structured_llm = llm.with_structured_output(_LLMReflection)

    async def acall(self, state: dict, **kwargs) -> dict:
        messages = state.get("messages", [])
        reflect_count: int = state.get("reflect_count", 0)
        callbacks = kwargs.get("callbacks", [])

        # Extract the original question and draft answer
        question = ""
        draft_answer = ""
        for m in messages:
            if isinstance(m, HumanMessage) and not question:
                question = m.content
            content = getattr(m, "content", "")
            if content and not isinstance(m, HumanMessage):
                draft_answer = content  # keep updating — we want the last AI content

        result = await self._evaluate(question, draft_answer, callbacks=callbacks)

        # Decide whether to re-run: incomplete OR below confidence threshold
        below_threshold = result.confidence_score < REFLECTION_THRESHOLD
        if (not result.is_complete or below_threshold) and reflect_count < MAX_REFLECT_ITERATIONS:
            result.needs_rerun = True
            log.info(
                "reflection.needs_rerun",
                confidence=result.confidence_score,
                reflect_count=reflect_count,
            )
        else:
            result.needs_rerun = False

        log.info(
            "reflection.complete",
            confidence=result.confidence_score,
            is_complete=result.is_complete,
            needs_rerun=result.needs_rerun,
        )

        return {
            "confidence_score": result.confidence_score,
            "reflection_notes": result.reflection_notes,
            "needs_rerun": result.needs_rerun,
            "reflect_count": reflect_count + 1,
            "messages": messages,
        }

    async def _evaluate(self, question: str, draft_answer: str, callbacks: list | None = None) -> ReflectionResult:
        if not draft_answer:
            return ReflectionResult.fallback()

        prompt = [
            SystemMessage(content=_REFLECTION_SYSTEM),
            HumanMessage(
                content=(
                    f"Question: {question}\n\n"
                    f"Draft answer:\n{draft_answer}"
                )
            ),
        ]
        try:
            lf_config = {"callbacks": callbacks} if callbacks else {}
            parsed: _LLMReflection = await self._structured_llm.ainvoke(prompt, config=lf_config)
            return ReflectionResult(
                confidence_score=parsed.confidence_score,
                is_complete=parsed.is_complete,
                reflection_notes=parsed.reflection_notes,
                needs_rerun=False,
            )
        except Exception as exc:
            log.warning("reflection.llm_error", error=str(exc))
            return ReflectionResult.fallback()
