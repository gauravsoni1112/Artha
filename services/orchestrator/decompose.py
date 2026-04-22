"""
Rule-based query decomposer (Phase 5).

Translates a natural-language query into a Plan by:
  1. Pattern-matching query tokens against per-agent keyword sets.
  2. Filtering to agents that are registered and available.
  3. Building a flat parallel Plan (all matched agents, no depends_on).

If no patterns match, all available agents are included (safe default —
the Critic will discard irrelevant outputs).

LLM fallback is stubbed as decompose_with_llm_fallback(); it is called only
when pattern confidence is below PATTERN_CONFIDENCE_THRESHOLD.  Phase 5
wires the real LLM call in the Planner dispatch layer.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from services.orchestrator.plan import AgentCall, Plan
from services.orchestrator.scope import ScopeContext


# ---------------------------------------------------------------------------
# Registry snapshot — lightweight projection of AgentRegistryEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisteredAgent:
    """
    Snapshot of one registry row passed into the decomposer.
    Caller (Planner) loads live registry and converts rows to this type.
    """

    agent_id: str
    capabilities: list[str]  # e.g. ["cashflow", "spending_trend", "budget_comparison"]


# ---------------------------------------------------------------------------
# Intent → agent mapping (rule-based)
# ---------------------------------------------------------------------------

# Each entry: (compiled pattern, canonical agent_id)
# Patterns are matched against the lower-cased query.
_INTENT_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"cashflow|spending|budget|expense|income|salary|payment|transaction|"
            r"spend|monthly|outflow|inflow|surplus|deficit|afford|can\s*i|should\s*i|"
            r"\bbank\b|\baccount\b|\baccounts\b|\bbalance\b|\bstatement\b"
        ),
        "cashflow_agent",
    ),
    (
        re.compile(
            r"invest|portfolio|mutual\s*fund|sip|stock|share|nifty|sensex|"
            r"xirr|nav|demat|equity|folio|holding|return|asset|allocation"
        ),
        "investment_agent",
    ),
    (
        re.compile(
            r"\btax\b|itr|80c|capital\s*gain|deduction|tds|refund|"
            r"cess|surcharge|new\s*regime|old\s*regime|section"
        ),
        "tax_agent",
    ),
    (
        re.compile(
            r"goal|retire|retirement|target|saving\s*plan|corpus|milestone|"
            r"education|marriage|house|down\s*payment|achieve|"
            r"increase\s*sip|sip.*increase|save\s*more|invest\s*more"
        ),
        "goal_agent",
    ),
    (
        re.compile(
            r"risk|insurance|emergency\s*fund|debt|loan|cover|coverage|"
            r"term\s*plan|health\s*cover|concentration|liability"
        ),
        "risk_agent",
    ),
]

# Minimum number of pattern matches to trust rule-based decomposition.
# Queries matching 0 patterns fall back to "all agents".
PATTERN_CONFIDENCE_THRESHOLD = 1


# ---------------------------------------------------------------------------
# Decomposition
# ---------------------------------------------------------------------------


def _matched_agent_ids(query: str) -> list[str]:
    """Return agent_ids whose patterns match the query (preserves rule order)."""
    lowered = query.lower()
    seen: set[str] = set()
    matched: list[str] = []
    for pattern, agent_id in _INTENT_RULES:
        if agent_id not in seen and pattern.search(lowered):
            matched.append(agent_id)
            seen.add(agent_id)
    return matched


def decompose(
    query: str,
    scope: ScopeContext,
    available_agents: list[RegisteredAgent],
    extra_context: dict[str, Any] | None = None,
) -> Plan:
    """
    Build a parallel Plan for the given query and scope.

    Args:
        query:            Original user query.
        scope:            Pre-resolved ScopeContext (allowed_owner_ids).
        available_agents: Current healthy registry snapshot.
        extra_context:    Extra key/values merged into every AgentCall.context.

    Returns:
        Plan with flat parallel steps.  Empty steps list if no agents available.
    """
    available_ids = {a.agent_id for a in available_agents}
    matched = _matched_agent_ids(query)

    # Filter to registered agents only
    target_ids = [aid for aid in matched if aid in available_ids]

    # No pattern match or none registered → use all available agents
    if not target_ids:
        target_ids = sorted(available_ids)

    ctx = extra_context or {}
    steps = [
        AgentCall(
            agent_id=agent_id,
            allowed_owner_ids=list(scope.allowed_owner_ids),
            context=dict(ctx),
            depends_on=[],  # all parallel in Phase 5
        )
        for agent_id in target_ids
    ]

    return Plan(original_query=query, steps=steps)


# ---------------------------------------------------------------------------
# LLM fallback stub (wired by Planner in commit 5)
# ---------------------------------------------------------------------------


async def decompose_with_llm_fallback(
    query: str,
    scope: ScopeContext,
    available_agents: list[RegisteredAgent],
    extra_context: dict[str, Any] | None = None,
) -> Plan:
    """
    Attempt rule-based decomposition; fall back to LLM for ambiguous queries.

    LLM path is a stub in Phase 5 commit 4 — it returns the rule-based plan.
    The real async LLM call is wired in commit 5 (Planner dispatch layer).
    """
    plan = decompose(query, scope, available_agents, extra_context)

    # If rule-based matched at least one agent, trust it.
    matched = _matched_agent_ids(query)
    available_ids = {a.agent_id for a in available_agents}
    if any(aid in available_ids for aid in matched):
        return plan

    # TODO (commit 5): call Ollama with structured output to produce agent list
    # For now, return the all-agents fallback plan from decompose().
    return plan
