"""
HTTP-layer tests for the registry and agent_router endpoints.

Uses FastAPI TestClient with dependency_overrides so no real DB or LLM is needed.
Tests the full HTTP stack: routing, serialisation, status codes, error branches.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.database import get_session
from api.routers.registry import router as registry_router
from api.routers.agent_router import router as domain_router
from libs.schemas.db_models import AgentRegistryEntry


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_entry(
    agent_id: str = "cashflow_agent",
    capabilities: list[str] | None = None,
    status: str = "HEALTHY",
) -> AgentRegistryEntry:
    now = datetime.now(timezone.utc)
    e = AgentRegistryEntry()
    e.agent_id = agent_id
    e.endpoint = f"http://{agent_id}:8001"
    e.health_endpoint = f"http://{agent_id}:8001/health"
    e.capabilities = capabilities or ["cashflow", "spending"]
    e.schema_version = "1.0"
    e.timeout_ms = 10_000
    e.fallback_strategy = "cached_response"
    e.cache_ttl_hours = 1.0
    e.scope = "individual"
    e.status = status
    e.last_heartbeat = now
    e.registered_at = now
    e.updated_at = now
    return e


def _agent_response_json(agent_id: str = "cashflow_agent") -> dict:
    return {
        "agent_id": agent_id,
        "schema_version": "1.0",
        "trace_id": str(uuid.uuid4()),
        "data_tier": "CACHED",
        "data_freshness_hours": 0.5,
        "result": {"answer": "You spent ₹12,400."},
        "confidence": 0.92,
        "risk_level": "LOW",
        "reasoning": "Based on last 30 days of GROCERIES transactions.",
        "warnings": [],
        "fallback_used": False,
        "fallback_reason": None,
    }


# ---------------------------------------------------------------------------
# Registry HTTP tests
# ---------------------------------------------------------------------------


@pytest.fixture
def registry_app() -> FastAPI:
    app = FastAPI()
    app.include_router(registry_router)
    return app


def _registry_client(mock_session) -> TestClient:
    app = FastAPI()
    app.include_router(registry_router)

    async def override():
        yield mock_session

    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_get_agent_not_found_http():
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)
    client = _registry_client(mock_session)

    resp = client.get("/registry/agents/nonexistent_agent")
    assert resp.status_code == 404
    assert "nonexistent_agent" in resp.json()["detail"]


def test_get_agent_found_http():
    entry = _make_entry(agent_id="risk_agent", capabilities=["risk"])
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=entry)
    client = _registry_client(mock_session)

    resp = client.get("/registry/agents/risk_agent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "risk_agent"
    assert "risk" in data["capabilities"]
    assert data["status"] == "HEALTHY"


def test_list_agents_http():
    entries = [
        _make_entry("cashflow_agent", ["cashflow"]),
        _make_entry("tax_agent", ["tax", "itr"]),
    ]
    mock_session = AsyncMock()
    mock_session.scalars = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=entries))
    )
    client = _registry_client(mock_session)

    resp = client.get("/registry/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    ids = {d["agent_id"] for d in data}
    assert "cashflow_agent" in ids
    assert "tax_agent" in ids


def test_delete_agent_not_found_http():
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)
    client = _registry_client(mock_session)

    resp = client.delete("/registry/agents/ghost_agent")
    assert resp.status_code == 404


def test_delete_agent_success_http():
    entry = _make_entry("goal_agent")
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=entry)
    mock_session.delete = AsyncMock()
    mock_session.commit = AsyncMock()
    client = _registry_client(mock_session)

    resp = client.delete("/registry/agents/goal_agent")
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Agent router HTTP tests
# ---------------------------------------------------------------------------


def _router_client(mock_session) -> TestClient:
    app = FastAPI()
    app.include_router(domain_router)

    async def override():
        yield mock_session

    app.dependency_overrides[get_session] = override
    return TestClient(app)


def _valid_query_body(capability: str = "cashflow") -> dict:
    return {
        "query": "What did I spend on groceries?",
        "capability": capability,
        "user_profile": {
            "owner_id": str(uuid.uuid4()),
            "name": "Test User",
            "total_monthly_income_paise": 10_000_000,
            "risk_appetite": "moderate",
        },
    }


def test_route_query_no_agent_503():
    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=None)
    client = _router_client(mock_session)

    resp = client.post("/router/query", json=_valid_query_body("unknown_cap"))
    assert resp.status_code == 503
    assert "unknown_cap" in resp.json()["detail"]


def test_route_query_success_200():
    entry = _make_entry("cashflow_agent", ["cashflow"])
    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=entry)

    mock_http_resp = MagicMock()
    mock_http_resp.raise_for_status = MagicMock()
    mock_http_resp.json = MagicMock(return_value=_agent_response_json("cashflow_agent"))

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_http_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    client = _router_client(mock_session)

    with patch("api.routers.agent_router.httpx.AsyncClient", return_value=mock_client):
        resp = client.post("/router/query", json=_valid_query_body("cashflow"))

    assert resp.status_code == 200
    data = resp.json()
    assert data["routed_to"] == "cashflow_agent"
    assert data["response"]["agent_id"] == "cashflow_agent"
    assert data["response"]["confidence"] == pytest.approx(0.92)


def test_route_query_agent_timeout_504():
    import httpx as _httpx
    entry = _make_entry("cashflow_agent", ["cashflow"])
    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=entry)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    client = _router_client(mock_session)

    with patch("api.routers.agent_router.httpx.AsyncClient", return_value=mock_client):
        resp = client.post("/router/query", json=_valid_query_body("cashflow"))

    assert resp.status_code == 504


def test_list_routable_agents_200():
    rows = [
        MagicMock(
            agent_id="cashflow_agent",
            capabilities=["cashflow"],
            scope="individual",
            status="HEALTHY",
            last_heartbeat=datetime.now(timezone.utc),
        ),
    ]
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    client = _router_client(mock_session)

    resp = client.get("/router/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["agent_id"] == "cashflow_agent"


# ---------------------------------------------------------------------------
# /agent/chat HTTP tests — Phase 4 capability routing path
# ---------------------------------------------------------------------------


from api.routers.agent import router as agent_router


def _chat_client(mock_session) -> TestClient:
    app = FastAPI()
    # Rate limiter needs state
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    app.state.limiter = Limiter(key_func=get_remote_address)
    app.include_router(agent_router)

    async def override():
        yield mock_session

    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_chat_capability_requires_user_profile():
    """capability without user_profile → 422 validation error."""
    mock_session = AsyncMock()
    client = _chat_client(mock_session)

    resp = client.post(
        "/agent/chat",
        json={
            "owner_id": str(uuid.uuid4()),
            "message": "What is my cashflow?",
            "capability": "cashflow",
            # missing user_profile
        },
    )
    assert resp.status_code == 422


def test_chat_user_profile_without_capability():
    """user_profile without capability → 422."""
    mock_session = AsyncMock()
    client = _chat_client(mock_session)

    resp = client.post(
        "/agent/chat",
        json={
            "owner_id": str(uuid.uuid4()),
            "message": "What is my cashflow?",
            "user_profile": {
                "owner_id": str(uuid.uuid4()),
                "name": "Test",
                "risk_appetite": "moderate",
            },
            # missing capability
        },
    )
    assert resp.status_code == 422


def test_chat_phase4_no_agent_503():
    """Phase 4 path: no healthy agent → 503."""
    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=None)
    client = _chat_client(mock_session)

    resp = client.post(
        "/agent/chat",
        json={
            "owner_id": str(uuid.uuid4()),
            "message": "What is my cashflow?",
            "capability": "cashflow",
            "user_profile": {
                "owner_id": str(uuid.uuid4()),
                "name": "Ravi",
                "risk_appetite": "moderate",
            },
        },
    )
    assert resp.status_code == 503


def test_chat_phase4_success():
    """Phase 4 path: agent found → dispatch → ChatResponse with routed_to."""
    entry = _make_entry("cashflow_agent", ["cashflow"])
    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=entry)

    mock_http_resp = MagicMock()
    mock_http_resp.raise_for_status = MagicMock()
    mock_http_resp.json = MagicMock(return_value=_agent_response_json("cashflow_agent"))

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_http_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    client = _chat_client(mock_session)

    with patch("api.routers.agent_router.httpx.AsyncClient", return_value=mock_client):
        resp = client.post(
            "/agent/chat",
            json={
                "owner_id": str(uuid.uuid4()),
                "message": "What is my cashflow?",
                "capability": "cashflow",
                "user_profile": {
                    "owner_id": str(uuid.uuid4()),
                    "name": "Priya",
                    "risk_appetite": "moderate",
                },
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["routed_to"] == "cashflow_agent"
    assert data["response"] == "You spent ₹12,400."
    assert data["confidence"] == pytest.approx(0.92)
    assert len(data["reasoning_steps"]) == 1
