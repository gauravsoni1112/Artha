"""
Confidence composition for Phase 5 Planner + Critic.

Two-layer model:
  1. FallbackTier penalties — applied by Planner at dispatch time based on
     *how* the agent response was obtained (live, cached, stale, or failed).
  2. Critic adjustments — downward-only, applied after cross-agent consistency checks.

compose() produces the deterministic baseline score before the Critic runs.
"""

from libs.confidence.composition import AgentConfidenceInput, CompositeResult, compose
from libs.confidence.tier import TIER_PENALTY, FallbackTier

__all__ = [
    "FallbackTier",
    "TIER_PENALTY",
    "AgentConfidenceInput",
    "CompositeResult",
    "compose",
]
