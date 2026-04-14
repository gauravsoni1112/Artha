"""
Phase 3 — Structured agent answer schema.

AgentAnswer is the canonical output format for every agent response.
The executor_loop requests the LLM to return this structure via
`with_structured_output`, which Artha then formats for display.

Fields:
  answer          — human-readable response string (INR-formatted)
  confidence      — 0.0–1.0 score from the reflection node
  reasoning_steps — ordered list of Thought/Action/Observation strings
  supporting_data — list of dicts, each a raw data point cited in the answer
                    e.g. {"tool": "category_analysis", "category": "FOOD",
                           "amount_paise": 450000, "period": "2025-01"}
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class AgentAnswer(BaseModel):
    """Structured output returned by the final synthesis step of the agent."""

    answer: str = Field(
        description="Human-readable answer to the user's question. Use ₹ formatting."
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score 0–1.  Populated by the reflection node.",
    )
    reasoning_steps: list[str] = Field(
        default_factory=list,
        description="Ordered Thought/Action/Observation steps that led to this answer.",
    )
    supporting_data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Raw data points cited in the answer (tool name + key figures).",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 1.0
        return max(0.0, min(1.0, f))

    @classmethod
    def from_agent_result(
        cls,
        response: str,
        scratchpad: list[dict] | None,
        confidence_score: float | None,
    ) -> "AgentAnswer":
        """
        Build an AgentAnswer from the raw dict returned by ArthaAgent.chat().

        reasoning_steps are derived from the scratchpad (Phase 3 chain-of-thought).
        supporting_data is left empty here; tools can inject it via structured output.
        """
        steps: list[str] = []
        if scratchpad:
            for step in scratchpad:
                parts = []
                if "thought" in step:
                    parts.append(f"Thought: {step['thought']}")
                if "action" in step:
                    parts.append(f"Action: {step['action']}")
                if "observation" in step:
                    parts.append(f"Observation: {step['observation']}")
                if "final_answer" in step:
                    parts.append(f"Final Answer: {step['final_answer']}")
                if parts:
                    steps.append(" | ".join(parts))

        return cls(
            answer=response,
            confidence=confidence_score if confidence_score is not None else 1.0,
            reasoning_steps=steps,
            supporting_data=[],
        )
