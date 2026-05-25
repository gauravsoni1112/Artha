"""
Query decomposer — rule-based fast path with LLM fallback (Phase 6).

Translates a natural-language query into a Plan by:
  1. Pattern-matching query tokens against per-agent keyword sets.
  2. If zero patterns match, calling a local LLM (PLANNER role) for structured
     agent selection on ambiguous queries.
  3. Filtering to registered/healthy agents; building steps with depends_on
     populated from _AGENT_DEPENDENCIES.

LLM fallback fires only when rule-based matches 0 patterns (roughly 20% of
queries — vague health-checks like "am I doing ok?"). All other queries go
through the fast regex path with no LLM overhead.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from services.agent.config import LLMRole, RoutingPolicy
from services.orchestrator.metrics import (
    record_decompose_agent_count,
    record_decompose_cycle,
    record_decompose_path,
)
from services.orchestrator.plan import AgentCall, Plan
from services.orchestrator.scope import ScopeContext

log = structlog.get_logger(__name__)


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
# Agent dependency table
# ---------------------------------------------------------------------------

_AGENT_DEPENDENCIES: dict[str, list[str]] = {
    "goal_agent": ["cashflow_agent", "investment_agent"],
    "risk_agent": ["cashflow_agent"],
}

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
    Build a Plan for the given query and scope, respecting agent dependencies.

    Args:
        query:            Original user query.
        scope:            Pre-resolved ScopeContext (allowed_owner_ids).
        available_agents: Current healthy registry snapshot.
        extra_context:    Extra key/values merged into every AgentCall.context.

    Returns:
        Plan whose steps respect _AGENT_DEPENDENCIES: dependency agents run first
        (parallel), dependent agents run after (sequential via depends_on).
    """
    available_ids = {a.agent_id for a in available_agents}
    matched = _matched_agent_ids(query)

    # Filter to registered agents only
    target_ids: list[str] = [aid for aid in matched if aid in available_ids]

    # No pattern match or none registered → use all available agents
    if not target_ids:
        target_ids = sorted(available_ids)

    # Auto-add dependency agents that are missing from the matched set
    augmented_ids: list[str] = list(target_ids)
    for agent_id in list(target_ids):
        for dep_id in _AGENT_DEPENDENCIES.get(agent_id, []):
            if dep_id in available_ids and dep_id not in augmented_ids:
                augmented_ids.insert(0, dep_id)  # prepend so dep runs first

    # Build steps — set depends_on only for agents with active deps in this plan
    ctx = extra_context or {}
    steps = []
    for agent_id in augmented_ids:
        declared_deps = _AGENT_DEPENDENCIES.get(agent_id, [])
        active_deps = [d for d in declared_deps if d in augmented_ids]
        steps.append(
            AgentCall(
                agent_id=agent_id,
                allowed_owner_ids=list(scope.allowed_owner_ids),
                context=dict(ctx),
                depends_on=active_deps,
            )
        )

    return Plan(original_query=query, steps=steps)


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


def _assert_no_cycles(calls: list[AgentCall]) -> None:
    """Kahn's algorithm — raises ValueError if depends_on forms a cycle."""
    in_degree: dict[str, int] = {c.agent_id: 0 for c in calls}
    adj: dict[str, list[str]] = {c.agent_id: [] for c in calls}
    for call in calls:
        for dep in call.depends_on:
            if dep in adj:
                adj[dep].append(call.agent_id)
                in_degree[call.agent_id] += 1

    queue = [aid for aid, deg in in_degree.items() if deg == 0]
    visited = 0
    while queue:
        node = queue.pop()
        visited += 1
        for neighbour in adj[node]:
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    if visited != len(calls):
        cycle_nodes = [aid for aid, deg in in_degree.items() if deg > 0]
        record_decompose_cycle()
        raise ValueError(f"Cycle detected in agent depends_on graph: {cycle_nodes}")


# ---------------------------------------------------------------------------
# LLM fallback — Pydantic schema + helpers
# ---------------------------------------------------------------------------


class _AgentStep(BaseModel):
    agent_id: str
    depends_on: list[str] = []


class _LLMPlan(BaseModel):
    steps: list[_AgentStep]
    reasoning: str


def _build_planner_system(available_agents: list[RegisteredAgent]) -> str:
    agent_lines = "\n".join(
        f"  - {a.agent_id}: {', '.join(a.capabilities) or 'general'}"
        for a in available_agents
    )
    dep_lines = "\n".join(
        f"  - {agent} requires: {', '.join(deps)}"
        for agent, deps in _AGENT_DEPENDENCIES.items()
    )
    return f"""\
You are a financial query planner. Given a user question, select which agents
should answer it and whether any agent needs another agent's output first.

Available agents:
{agent_lines}

Pre-declared data dependencies (always honour these when the agent is selected):
{dep_lines}

Output ONLY valid JSON — no markdown, no explanation:
{{
  "steps": [
    {{"agent_id": "<id>", "depends_on": []}},
    {{"agent_id": "<id>", "depends_on": ["<id of agent that must run first>"]}}
  ],
  "reasoning": "<why you chose these agents>"
}}

Rules:
- Only use agent_ids from the list above. Never invent new ones.
- Set depends_on only when one agent genuinely needs another's data to answer.
- Always honour pre-declared dependencies when the dependent agent is included.
- When in doubt, include more agents rather than fewer — the Critic filters noise.
- Maximum 5 agents in steps.
"""


def _to_orchestrator_plan(
    llm_plan: _LLMPlan,
    scope: ScopeContext,
    available_agents: list[RegisteredAgent],
    extra_context: dict[str, Any] | None,
) -> Plan | None:
    """
    Convert _LLMPlan → orchestrator Plan, validating agent_ids and merging
    declared dependencies with _AGENT_DEPENDENCIES. Returns None if the
    resulting plan has a cycle (caller should fall back to all-agents).
    """
    available_ids = {a.agent_id for a in available_agents}
    # Drop any agent_id the LLM hallucinated
    valid_steps = [s for s in llm_plan.steps if s.agent_id in available_ids]
    if not valid_steps:
        return None

    included_ids = {s.agent_id for s in valid_steps}
    ctx = extra_context or {}
    calls: list[AgentCall] = []
    for step in valid_steps:
        # Merge LLM-declared deps with pre-declared deps; filter to included agents
        declared = set(step.depends_on) | set(_AGENT_DEPENDENCIES.get(step.agent_id, []))
        active_deps = sorted(declared & included_ids - {step.agent_id})
        calls.append(
            AgentCall(
                agent_id=step.agent_id,
                allowed_owner_ids=list(scope.allowed_owner_ids),
                context=dict(ctx),
                depends_on=active_deps,
            )
        )

    try:
        _assert_no_cycles(calls)
    except ValueError:
        return None  # caller falls back to rule-based all-agents plan

    return Plan(original_query="", steps=calls)


# ---------------------------------------------------------------------------
# LLM fallback entry point
# ---------------------------------------------------------------------------


async def decompose_with_llm_fallback(
    query: str,
    scope: ScopeContext,
    available_agents: list[RegisteredAgent],
    extra_context: dict[str, Any] | None = None,
) -> Plan:
    """
    Rule-based fast path with LLM fallback for zero-match queries.

    Flow:
      1. Run regex patterns. If ≥1 agent matched → return rule-based Plan.
      2. Zero matches → call local LLM (PLANNER role) with structured output.
      3. Parse + validate LLM response; drop hallucinated agent_ids.
      4. On any LLM/parse/cycle error → fall back to all-agents parallel Plan.
    """
    matched = _matched_agent_ids(query)
    available_ids = {a.agent_id for a in available_agents}
    if any(aid in available_ids for aid in matched):
        plan = decompose(query, scope, available_agents, extra_context)
        record_decompose_path("rule_based")
        record_decompose_agent_count(len(plan.steps), "rule_based")
        return plan

    # Zero-match path — delegate to LLM
    log.info("decomposer.llm_route", query=query[:80], available=sorted(available_ids))
    try:
        llm = RoutingPolicy.from_env(LLMRole.PLANNER).build_chat_model()
        structured_llm = llm.with_structured_output(_LLMPlan)
        system = _build_planner_system(available_agents)
        llm_plan: _LLMPlan | None = await structured_llm.ainvoke(
            [SystemMessage(system), HumanMessage(query)]
        )
        if llm_plan is not None:
            plan = _to_orchestrator_plan(llm_plan, scope, available_agents, extra_context)
            if plan is not None:
                plan = Plan(original_query=query, steps=plan.steps)
                log.info(
                    "decomposer.llm_plan_accepted",
                    agents=plan.agent_ids(),
                    reasoning=llm_plan.reasoning[:120],
                )
                record_decompose_path("llm_fallback")
                record_decompose_agent_count(len(plan.steps), "llm_fallback")
                return plan
    except Exception as exc:
        err_str = str(exc)
        extra: dict = {"hint": "Check GOOGLE_API_KEY in .env"} if (
            "API_KEY_INVALID" in err_str or "API key not valid" in err_str
        ) else {}
        log.warning("decomposer.llm_route_error", error=err_str, **extra)

    # Safe fallback — all available agents, no dependencies
    fallback_plan = decompose(query, scope, available_agents, extra_context)
    record_decompose_path("llm_fallback")
    record_decompose_agent_count(len(fallback_plan.steps), "llm_fallback")
    return fallback_plan
