"""
Deterministic composite confidence composition.

Algorithm:
  1. Exclude FAILURE-tier agents; record them as gaps.
  2. For each active agent: adjusted = max(0, base_confidence_pct + tier_penalty).
  3. Composite score = simple average of adjusted scores.
  4. Collect warnings for every non-PRIMARY tier.

The Critic receives this CompositeResult and may only LOWER the score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from libs.confidence.tier import TIER_PENALTY, FallbackTier


@dataclass(frozen=True)
class AgentConfidenceInput:
    agent_id: str
    base_confidence: float      # 0.0–1.0 as returned in AgentResponse.confidence
    fallback_tier: FallbackTier


@dataclass
class CompositeResult:
    score: float                    # 0.0–100.0, rounded to 2 dp
    gaps: list[str] = field(default_factory=list)      # agent_ids excluded (FAILURE tier)
    warnings: list[str] = field(default_factory=list)  # non-PRIMARY tier notices


def compose(inputs: list[AgentConfidenceInput]) -> CompositeResult:
    """
    Compute baseline composite confidence from a list of agent responses.

    Returns score=0.0 with all agents listed as gaps if every agent failed.
    """
    if not inputs:
        return CompositeResult(score=0.0, gaps=[], warnings=["No agent inputs provided"])

    active = [i for i in inputs if i.fallback_tier != FallbackTier.FAILURE]
    gaps = [i.agent_id for i in inputs if i.fallback_tier == FallbackTier.FAILURE]

    if not active:
        return CompositeResult(
            score=0.0,
            gaps=gaps,
            warnings=["All agents failed — no confidence score available"],
        )

    adjusted: list[float] = []
    warnings: list[str] = []

    for inp in active:
        base_pct = inp.base_confidence * 100.0
        penalty = TIER_PENALTY[inp.fallback_tier]
        adj = max(0.0, base_pct + penalty)
        adjusted.append(adj)

        if inp.fallback_tier == FallbackTier.SECONDARY:
            warnings.append(
                f"{inp.agent_id}: cached response used (confidence −10 pp)"
            )
        elif inp.fallback_tier == FallbackTier.TERTIARY:
            warnings.append(
                f"{inp.agent_id}: stale/estimated data used (confidence −25 pp)"
            )

    score = round(sum(adjusted) / len(adjusted), 2)
    return CompositeResult(score=score, gaps=gaps, warnings=warnings)
