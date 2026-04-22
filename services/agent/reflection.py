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

import json
import os
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

log = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

REFLECTION_THRESHOLD: float = float(os.getenv("REFLECTION_THRESHOLD", "0.7"))
MAX_REFLECT_ITERATIONS: int = int(os.getenv("MAX_REFLECT_ITERATIONS", "2"))


def _extract_json_object(text: str) -> str | None:
    """Return the first balanced JSON object from *text*, or None."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None

_REFLECTION_SYSTEM = """\
You are a financial answer quality evaluator.

Given a user question and the assistant's draft answer, rate how complete and
accurate the answer is.  Output ONLY valid JSON (no markdown, no explanation):

{
  "confidence_score": <float between 0.0 and 1.0>,
  "is_complete": <true|false>,
  "reflection_notes": "<brief note — what is missing or uncertain, or 'Answer is complete.' if nothing>"
}

Scoring guide:
  1.0 — All figures cited, data clearly sourced, question fully answered.
  0.7 — Mostly answered; minor data gaps or hedging.
  0.5 — Partial answer; key data missing.
  0.0 — No useful answer produced.

Be strict: if the answer says "data unavailable" without explaining why,
score ≤ 0.5.
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

    async def acall(self, state: dict, **kwargs) -> dict:
        messages = state.get("messages", [])
        reflect_count: int = state.get("reflect_count", 0)
        callbacks = kwargs.get("callbacks", [])

        # Extract the original question and draft answer
        question = ""
        draft_answer = ""
        for m in messages:
            if isinstance(m, HumanMessage) and not question:
                q = m.content
                # Strip owner_id token if present
                if q.startswith("[owner_id="):
                    q = q.split("] ", 1)[-1]
                question = q
            content = getattr(m, "content", "")
            if content and not isinstance(m, HumanMessage):
                draft_answer = content  # keep updating — we want the last AI content

        result = await self._evaluate(question, draft_answer, callbacks=callbacks)

        # Decide whether to re-run
        if not result.is_complete and reflect_count < MAX_REFLECT_ITERATIONS:
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
            response = await self._llm.ainvoke(prompt, config=lf_config)
            return self._parse(response.content)
        except Exception as exc:
            log.warning("reflection.llm_error", error=str(exc))
            return ReflectionResult.fallback()

    def _parse(self, content: str) -> ReflectionResult:
        for candidate in (content.strip(), _extract_json_object(content)):
            if not candidate:
                continue
            try:
                data = json.loads(candidate)
                score = float(data.get("confidence_score", 0.5))
                score = max(0.0, min(1.0, score))  # clamp to [0, 1]
                is_complete = bool(data.get("is_complete", True))
                notes = str(data.get("reflection_notes", ""))
                needs_rerun = not is_complete and score < REFLECTION_THRESHOLD
                return ReflectionResult(
                    confidence_score=score,
                    is_complete=is_complete,
                    reflection_notes=notes,
                    needs_rerun=needs_rerun,
                )
            except Exception:
                continue
        log.warning("reflection.parse_error", raw=content[:200])
        return ReflectionResult.fallback()
