"""Unit tests for rule-based query decomposer."""

import uuid

import pytest

from services.orchestrator.decompose import RegisteredAgent, _matched_agent_ids, decompose
from services.orchestrator.scope import ScopeContext


def _scope(n: int = 1) -> ScopeContext:
    return ScopeContext(
        allowed_owner_ids=[uuid.uuid4() for _ in range(n)],
        is_family_scope=False,
    )


def _agents(*ids: str) -> list[RegisteredAgent]:
    cap_map = {
        "cashflow_agent": ["cashflow", "spending_trend", "budget_comparison"],
        "investment_agent": ["portfolio_value", "net_worth", "asset_allocation", "xirr"],
        "tax_agent": ["tax_summary", "capital_gains", "80c_tracker"],
        "goal_agent": ["goal_progress", "goal_feasibility"],
        "risk_agent": ["emergency_fund_months", "asset_concentration", "debt_to_income"],
    }
    return [RegisteredAgent(agent_id=aid, capabilities=cap_map.get(aid, [])) for aid in ids]


ALL_AGENTS = _agents(
    "cashflow_agent", "investment_agent", "tax_agent", "goal_agent", "risk_agent"
)


# ---------------------------------------------------------------------------
# Pattern matching (_matched_agent_ids)
# ---------------------------------------------------------------------------


def test_cashflow_keywords_match_cashflow_agent():
    for word in ["spending", "budget", "expense", "income", "salary", "surplus"]:
        assert "cashflow_agent" in _matched_agent_ids(word), f"missed: {word}"


def test_investment_keywords():
    for word in ["SIP", "portfolio", "mutual fund", "XIRR", "equity", "NAV"]:
        assert "investment_agent" in _matched_agent_ids(word), f"missed: {word}"


def test_tax_keywords():
    for word in ["tax", "80C", "capital gain", "TDS", "ITR", "deduction"]:
        assert "tax_agent" in _matched_agent_ids(word), f"missed: {word}"


def test_goal_keywords():
    for word in ["goal", "retirement", "corpus", "milestone", "target"]:
        assert "goal_agent" in _matched_agent_ids(word), f"missed: {word}"


def test_risk_keywords():
    for word in ["risk", "insurance", "emergency fund", "debt", "loan", "coverage"]:
        assert "risk_agent" in _matched_agent_ids(word), f"missed: {word}"


def test_no_keyword_match_returns_empty():
    assert _matched_agent_ids("hello world") == []


# ---------------------------------------------------------------------------
# decompose() — single-agent plans
# ---------------------------------------------------------------------------


def test_cashflow_query_produces_cashflow_agent():
    plan = decompose("show my spending this month", _scope(), ALL_AGENTS)
    assert plan.agent_ids() == ["cashflow_agent"]


def test_tax_query_produces_tax_agent():
    plan = decompose("what are my 80C deductions?", _scope(), ALL_AGENTS)
    assert "tax_agent" in plan.agent_ids()


# ---------------------------------------------------------------------------
# decompose() — multi-agent plans
# ---------------------------------------------------------------------------


def test_sip_increase_query_covers_cashflow_investment_goal():
    """Canonical exit-criterion query from spec."""
    plan = decompose("Should I increase SIP by ₹10k?", _scope(), ALL_AGENTS)
    ids = set(plan.agent_ids())
    assert "cashflow_agent" in ids, "need surplus info"
    assert "investment_agent" in ids, "need portfolio/SIP info"
    assert "goal_agent" in ids, "need goal feasibility"


def test_all_steps_parallel_no_depends():
    plan = decompose("Should I increase SIP by ₹10k?", _scope(), ALL_AGENTS)
    for step in plan.steps:
        assert step.depends_on == []
    assert len(plan.parallel_steps()) == len(plan.steps)


# ---------------------------------------------------------------------------
# decompose() — fallback to all agents on unknown intent
# ---------------------------------------------------------------------------


def test_unknown_query_dispatches_all_available():
    plan = decompose("hello", _scope(), ALL_AGENTS)
    assert set(plan.agent_ids()) == {a.agent_id for a in ALL_AGENTS}


def test_matched_but_unregistered_agent_excluded():
    # Only cashflow_agent registered; tax query matches tax_agent but it's not available
    plan = decompose("my tax deductions", _scope(), _agents("cashflow_agent"))
    # tax_agent not available → fallback to all available (only cashflow)
    assert plan.agent_ids() == ["cashflow_agent"]


# ---------------------------------------------------------------------------
# decompose() — scope propagation
# ---------------------------------------------------------------------------


def test_scope_owner_ids_propagated_to_all_steps():
    owner1, owner2 = uuid.uuid4(), uuid.uuid4()
    scope = ScopeContext(allowed_owner_ids=[owner1, owner2], is_family_scope=True)
    plan = decompose("our combined budget", scope, ALL_AGENTS)
    for step in plan.steps:
        assert set(step.allowed_owner_ids) == {owner1, owner2}


# ---------------------------------------------------------------------------
# decompose() — extra context
# ---------------------------------------------------------------------------


def test_extra_context_merged_into_every_step():
    ctx = {"fiscal_year": "2024-25", "currency": "INR"}
    plan = decompose("show spending", _scope(), ALL_AGENTS, extra_context=ctx)
    for step in plan.steps:
        assert step.context["fiscal_year"] == "2024-25"


def test_extra_context_steps_are_independent_copies():
    ctx = {"key": "value"}
    plan = decompose("spending and portfolio", _scope(), ALL_AGENTS, extra_context=ctx)
    # Mutating one step's context dict should not affect others
    plan.steps[0].context["key"] = "mutated"  # type: ignore[index]
    assert plan.steps[1].context["key"] == "value"


# ---------------------------------------------------------------------------
# decompose() — empty registry
# ---------------------------------------------------------------------------


def test_empty_registry_returns_empty_plan():
    plan = decompose("any query", _scope(), [])
    assert plan.steps == []


# ---------------------------------------------------------------------------
# Plan metadata
# ---------------------------------------------------------------------------


def test_original_query_preserved():
    q = "Should I increase SIP by ₹10k?"
    plan = decompose(q, _scope(), ALL_AGENTS)
    assert plan.original_query == q
