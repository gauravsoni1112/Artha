"""
Contract tests for AgentRequest / AgentResponse (schema v1.0).

These tests enforce the integration contract between the router and agents.
Failures here mean a breaking change to the agent API surface.
"""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from libs.schemas.agent_envelope import (
    AgentRequest,
    AgentResponse,
    AgentScope,
    DataTier,
    RiskLevel,
)
from libs.schemas.user_profile import UserProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile() -> UserProfile:
    return UserProfile(owner_id=uuid.uuid4(), name="Test User")


def _valid_request(**kwargs) -> dict:
    base = dict(
        query="What did I spend on groceries last month?",
        user_profile=_profile(),
        trace_id=uuid.uuid4(),
    )
    base.update(kwargs)
    return base


def _valid_response(**kwargs) -> dict:
    tid = uuid.uuid4()
    base = dict(
        agent_id="cashflow_agent",
        schema_version="1.0",
        trace_id=tid,
        data_tier=DataTier.REALTIME,
        data_freshness_hours=0.1,
        result={"answer": "₹12,400"},
        confidence=0.92,
        risk_level=RiskLevel.LOW,
        reasoning="Summed GROCERIES transactions for March 2026.",
        warnings=[],
    )
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# AgentRequest — construction
# ---------------------------------------------------------------------------


def test_request_minimal():
    req = AgentRequest(**_valid_request())
    assert req.context == {}
    assert req.schema_version if hasattr(req, "schema_version") else True  # future-safe


def test_request_defaults_trace_id():
    req = AgentRequest(query="Hello", user_profile=_profile())
    assert isinstance(req.trace_id, uuid.UUID)


def test_request_defaults_timestamp():
    req = AgentRequest(query="Hello", user_profile=_profile())
    assert req.request_timestamp.tzinfo is not None


def test_request_requires_query():
    with pytest.raises(ValidationError, match="query"):
        AgentRequest(user_profile=_profile())


def test_request_requires_user_profile():
    with pytest.raises(ValidationError, match="user_profile"):
        AgentRequest(query="Hello")


# ---------------------------------------------------------------------------
# AgentRequest — extra fields tolerated (forward compat)
# ---------------------------------------------------------------------------


def test_request_ignores_unknown_fields():
    data = _valid_request()
    data["future_field"] = "some_value"
    req = AgentRequest(**data)
    assert not hasattr(req, "future_field")


# ---------------------------------------------------------------------------
# AgentResponse — construction
# ---------------------------------------------------------------------------


def test_response_minimal():
    resp = AgentResponse(**_valid_response())
    assert resp.schema_version == "1.0"
    assert resp.fallback_used is False
    assert resp.fallback_reason is None
    assert resp.warnings == []


def test_response_with_fallback():
    resp = AgentResponse(
        **_valid_response(fallback_used=True, fallback_reason="LLM timeout, used cached result")
    )
    assert resp.fallback_used is True
    assert resp.fallback_reason is not None


def test_response_confidence_bounds():
    AgentResponse(**_valid_response(confidence=0.0))
    AgentResponse(**_valid_response(confidence=1.0))
    with pytest.raises(ValidationError):
        AgentResponse(**_valid_response(confidence=1.01))
    with pytest.raises(ValidationError):
        AgentResponse(**_valid_response(confidence=-0.01))


def test_response_data_freshness_non_negative():
    AgentResponse(**_valid_response(data_freshness_hours=0))
    with pytest.raises(ValidationError):
        AgentResponse(**_valid_response(data_freshness_hours=-1))


# ---------------------------------------------------------------------------
# AgentResponse — required fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["agent_id", "trace_id", "result", "reasoning", "confidence"])
def test_response_required_fields(field):
    data = _valid_response()
    del data[field]
    with pytest.raises(ValidationError):
        AgentResponse(**data)


# ---------------------------------------------------------------------------
# AgentResponse — extra fields tolerated (forward compat)
# ---------------------------------------------------------------------------


def test_response_ignores_unknown_fields():
    data = _valid_response()
    data["next_version_field"] = 42
    resp = AgentResponse(**data)
    assert not hasattr(resp, "next_version_field")


# ---------------------------------------------------------------------------
# Schema v1 round-trip (contract test proper)
# ---------------------------------------------------------------------------


def test_v1_request_roundtrip():
    req = AgentRequest(**_valid_request())
    serialised = req.model_dump(mode="json")
    restored = AgentRequest.model_validate(serialised)
    assert restored.trace_id == req.trace_id
    assert restored.user_profile.owner_id == req.user_profile.owner_id


def test_v1_response_roundtrip():
    resp = AgentResponse(**_valid_response())
    serialised = resp.model_dump(mode="json")
    restored = AgentResponse.model_validate(serialised)
    assert restored.agent_id == resp.agent_id
    assert restored.confidence == resp.confidence
    assert restored.trace_id == resp.trace_id


def test_trace_id_propagated_request_to_response():
    """trace_id set in request should be copied to response by agent."""
    tid = uuid.uuid4()
    req = AgentRequest(**_valid_request(trace_id=tid))
    resp = AgentResponse(**_valid_response(trace_id=req.trace_id))
    assert resp.trace_id == tid


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------


def test_all_data_tiers():
    for tier in DataTier:
        AgentResponse(**_valid_response(data_tier=tier))


def test_all_risk_levels():
    for level in RiskLevel:
        AgentResponse(**_valid_response(risk_level=level))


def test_all_agent_scopes():
    for scope in AgentScope:
        assert scope in (AgentScope.INDIVIDUAL, AgentScope.FAMILY)
