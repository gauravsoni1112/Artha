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


# ---------------------------------------------------------------------------
# /orchestrator/recommendation  (Phase 5)
# ---------------------------------------------------------------------------


from api.routers.orchestrator import (
    get_registry,
    get_breaker,
    get_response_cache,
    router as orchestrator_router,
)
from libs.schemas.db_models import UserProfile as UserProfileORM, UserProfileScope
from libs.schemas.enums import RecommendationState
from services.orchestrator.breaker import InMemoryBreakerStore, BreakerConfig
from services.orchestrator.critic import CriticResult
from services.orchestrator.dispatch import DispatchedResult
from libs.confidence.tier import FallbackTier


def _orchestrator_client(mock_session, mock_registry=None, mock_breaker=None, mock_cache=None) -> TestClient:
    app = FastAPI()
    app.include_router(orchestrator_router)

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session

    if mock_registry is not None:
        app.dependency_overrides[get_registry] = lambda: mock_registry
    if mock_breaker is not None:
        app.dependency_overrides[get_breaker] = lambda: mock_breaker
    if mock_cache is not None:
        app.dependency_overrides[get_response_cache] = lambda: mock_cache

    return TestClient(app)


def _mock_profile_orm(owner_id: uuid.UUID) -> UserProfileORM:
    p = UserProfileORM()
    p.id = uuid.uuid4()
    p.owner_id = owner_id
    p.risk_appetite = "moderate"
    p.age = 35
    p.is_family_scope = False
    p.total_monthly_income_paise = 500_000_00
    p.income_sources_json = []
    p.emis_json = []
    return p


def _mock_critic_result(score: float = 72.5) -> CriticResult:
    return CriticResult(
        final_confidence=score,
        baseline_confidence=score + 5.0,
        total_penalty=5.0,
        consistency_flags=[],
        schema_warnings=[],
        gaps=[],
        warnings=[],
    )


def _mock_dispatched_primary(agent_id: str = "cashflow_agent") -> DispatchedResult:
    from libs.schemas.agent_envelope import AgentResponse, DataTier, RiskLevel
    return DispatchedResult(
        agent_id=agent_id,
        response=AgentResponse(
            agent_id=agent_id,
            trace_id=uuid.uuid4(),
            data_tier=DataTier.REALTIME,
            data_freshness_hours=0.0,
            result={"surplus_paise": 1_800_000},
            confidence=0.85,
            risk_level=RiskLevel.LOW,
            reasoning="ok",
        ),
        fallback_tier=FallbackTier.PRIMARY,
    )


def test_create_recommendation_profile_not_found_404():
    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=None)  # no profile

    mock_registry = MagicMock()
    mock_registry.list_available.return_value = []
    mock_breaker = InMemoryBreakerStore(BreakerConfig())
    mock_cache = AsyncMock()

    client = _orchestrator_client(mock_session, mock_registry, mock_breaker, mock_cache)
    resp = client.post(
        "/orchestrator/recommendation",
        json={"owner_id": str(uuid.uuid4()), "query": "Should I increase SIP?"},
    )
    assert resp.status_code == 404
    assert "profile" in resp.json()["detail"].lower()


def test_create_recommendation_success_201():
    owner_id = uuid.uuid4()
    profile_orm = _mock_profile_orm(owner_id)

    # Fake Owner
    from libs.schemas.db_models import Owner
    owner = Owner()
    owner.id = owner_id
    owner.name = "Rahul"

    # Fake snapshot with id
    from libs.schemas.db_models import UserProfileSnapshot, Recommendation, RecommendationEvent
    snapshot = UserProfileSnapshot()
    snapshot.id = uuid.uuid4()
    snapshot.profile_id = profile_orm.id
    snapshot.snapshot_json = {}

    # Fake recommendation with id
    rec = Recommendation()
    rec.id = uuid.uuid4()
    rec.current_state = RecommendationState.GENERATED.value
    rec.composite_confidence = 72.5
    rec.final_output_json = {"final_confidence": 72.5}

    added_objects = []
    flush_call_count = [0]

    async def fake_flush():
        flush_call_count[0] += 1
        # Assign IDs on first two flushes (snapshot, then rec)
        for obj in added_objects:
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=profile_orm)
    mock_session.get = AsyncMock(side_effect=lambda model, pk: owner if model is Owner else rec)
    mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
    mock_session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
    mock_session.flush = fake_flush
    mock_session.commit = AsyncMock()

    mock_registry = MagicMock()
    mock_registry.list_available.return_value = []

    mock_breaker = InMemoryBreakerStore(BreakerConfig())
    mock_cache = AsyncMock()

    dispatched = [_mock_dispatched_primary()]
    critic = _mock_critic_result()

    client = _orchestrator_client(mock_session, mock_registry, mock_breaker, mock_cache)

    with (
        patch("api.routers.orchestrator.dispatch_plan", new=AsyncMock(return_value=dispatched)),
        patch("api.routers.orchestrator.critic_evaluate", return_value=critic),
        patch("api.routers.orchestrator.create_snapshot", new=AsyncMock(return_value=snapshot)),
        patch("api.routers.orchestrator.create_recommendation", new=AsyncMock(return_value=rec)),
    ):
        resp = client.post(
            "/orchestrator/recommendation",
            json={"owner_id": str(owner_id), "query": "Should I increase SIP by ₹10k?"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert "recommendation_id" in data
    assert data["state"] == "GENERATED"
    assert isinstance(data["final_confidence"], float)


def test_add_event_invalid_transition_422():
    """GENERATED → ACCEPTED is invalid → 422."""
    from libs.schemas.db_models import Recommendation

    rec = Recommendation()
    rec.id = uuid.uuid4()
    rec.current_state = RecommendationState.GENERATED.value

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=rec)
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    client = _orchestrator_client(mock_session)
    rec_id = uuid.uuid4()

    resp = client.post(
        f"/orchestrator/recommendation/{rec_id}/events",
        json={
            "event_type": "ACCEPTED",
            "actor_user_id": str(uuid.uuid4()),
            "payload": {},
        },
    )
    assert resp.status_code == 422
    assert "GENERATED" in resp.json()["detail"]


def test_add_event_valid_transition_200():
    """GENERATED → SURFACED is valid → 200."""
    from libs.schemas.db_models import Recommendation, RecommendationEvent

    rec = Recommendation()
    rec.id = uuid.uuid4()
    rec.current_state = RecommendationState.GENERATED.value

    event = RecommendationEvent()
    event.id = uuid.uuid4()
    event.recommendation_id = rec.id
    event.event_type = RecommendationState.SURFACED.value

    mock_session = AsyncMock()
    # First get → rec (for transition_state), second get → rec (for current_state)
    mock_session.get = AsyncMock(return_value=rec)
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    client = _orchestrator_client(mock_session)

    with patch(
        "api.routers.orchestrator.transition_state",
        new=AsyncMock(return_value=event),
    ):
        resp = client.post(
            f"/orchestrator/recommendation/{rec.id}/events",
            json={
                "event_type": "SURFACED",
                "actor_user_id": str(uuid.uuid4()),
                "payload": {},
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["event_type"] == "SURFACED"


def test_add_event_recommendation_not_found_404():
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    client = _orchestrator_client(mock_session)

    with patch(
        "api.routers.orchestrator.transition_state",
        new=AsyncMock(side_effect=ValueError("Recommendation not found")),
    ):
        resp = client.post(
            f"/orchestrator/recommendation/{uuid.uuid4()}/events",
            json={
                "event_type": "SURFACED",
                "actor_user_id": str(uuid.uuid4()),
            },
        )

    assert resp.status_code == 404
