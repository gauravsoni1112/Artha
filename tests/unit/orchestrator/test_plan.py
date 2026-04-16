"""Unit tests for Plan and AgentCall serialisation."""

import uuid
from datetime import datetime, timezone

from services.orchestrator.plan import AgentCall, Plan


def _call(agent_id: str = "cashflow_agent", n_owners: int = 1, **kwargs) -> AgentCall:
    return AgentCall(
        agent_id=agent_id,
        allowed_owner_ids=[uuid.uuid4() for _ in range(n_owners)],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# AgentCall
# ---------------------------------------------------------------------------


def test_agent_call_round_trip():
    owner = uuid.uuid4()
    call = AgentCall(
        agent_id="investment_agent",
        allowed_owner_ids=[owner],
        context={"fiscal_year": "2024-25"},
        depends_on=["cashflow_agent"],
    )
    restored = AgentCall.from_dict(call.to_dict())
    assert restored.agent_id == "investment_agent"
    assert restored.allowed_owner_ids == [owner]
    assert restored.context == {"fiscal_year": "2024-25"}
    assert restored.depends_on == ["cashflow_agent"]


def test_agent_call_defaults():
    call = _call()
    assert call.context == {}
    assert call.depends_on == []


def test_agent_call_is_frozen():
    call = _call()
    try:
        call.agent_id = "other"  # type: ignore[misc]
        assert False, "should have raised"
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def test_plan_round_trip():
    query = "Should I increase SIP by ₹10k?"
    steps = [
        _call("cashflow_agent"),
        _call("investment_agent"),
        _call("goal_agent"),
    ]
    plan = Plan(original_query=query, steps=steps)
    restored = Plan.from_dict(plan.to_dict())

    assert restored.plan_id == plan.plan_id
    assert restored.original_query == query
    assert len(restored.steps) == 3
    assert restored.steps[0].agent_id == "cashflow_agent"


def test_plan_agent_ids():
    plan = Plan(
        original_query="test",
        steps=[_call("cashflow_agent"), _call("tax_agent")],
    )
    assert plan.agent_ids() == ["cashflow_agent", "tax_agent"]


def test_plan_parallel_steps_excludes_dependents():
    steps = [
        _call("cashflow_agent"),                                         # parallel
        _call("investment_agent"),                                       # parallel
        _call("goal_agent", depends_on=["cashflow_agent"]),              # sequential
    ]
    plan = Plan(original_query="test", steps=steps)

    assert len(plan.parallel_steps()) == 2
    assert {s.agent_id for s in plan.parallel_steps()} == {"cashflow_agent", "investment_agent"}

    assert len(plan.sequential_steps()) == 1
    assert plan.sequential_steps()[0].agent_id == "goal_agent"


def test_plan_all_parallel_when_no_depends():
    steps = [_call("cashflow_agent"), _call("tax_agent"), _call("risk_agent")]
    plan = Plan(original_query="test", steps=steps)
    assert len(plan.parallel_steps()) == 3
    assert plan.sequential_steps() == []


def test_plan_empty_steps():
    plan = Plan(original_query="unknown intent", steps=[])
    assert plan.agent_ids() == []
    assert plan.parallel_steps() == []
    d = plan.to_dict()
    restored = Plan.from_dict(d)
    assert restored.steps == []


def test_plan_created_at_preserved_in_serialisation():
    ts = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)
    plan = Plan(original_query="test", steps=[], created_at=ts)
    restored = Plan.from_dict(plan.to_dict())
    assert restored.created_at == ts


def test_plan_serialisation_owner_ids_as_strings():
    """owner UUIDs must survive JSON storage (stored as str, restored as UUID)."""
    owner = uuid.uuid4()
    plan = Plan(
        original_query="test",
        steps=[AgentCall(agent_id="cashflow_agent", allowed_owner_ids=[owner])],
    )
    d = plan.to_dict()
    assert isinstance(d["steps"][0]["allowed_owner_ids"][0], str)
    restored = Plan.from_dict(d)
    assert restored.steps[0].allowed_owner_ids[0] == owner
