"""
Unit tests for api/routers/goals.py, api/routers/transactions.py,
and api/routers/admin.py.

All tests use TestClient with dependency_overrides — no real DB needed.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.database import get_session
from api.deps import current_owner, require_admin
from api.routers.goals import router as goals_router
from api.routers.transactions import router as transactions_router
from api.routers.admin import router as admin_router
from libs.schemas.db_models import (
    AgentRegistryEntry,
    FinancialGoal,
    IngestionRun,
    Owner,
    Recommendation,
    RecommendationEvent,
    TransactionQuarantine,
)
from libs.schemas.db_models import Transaction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_owner(name: str = "Alice", is_admin: bool = False) -> Owner:
    now = datetime.now(timezone.utc)
    o = Owner()
    o.id = uuid.uuid4()
    o.name = name
    o.pan_hash = None
    o.is_admin = is_admin
    o.pin_hash = None
    o.created_at = now
    o.updated_at = now
    return o


def _make_goal(owner_id: uuid.UUID, name: str = "Retirement", target: int = 1_00_00000) -> FinancialGoal:
    now = datetime.now(timezone.utc)
    g = FinancialGoal()
    g.id = uuid.uuid4()
    g.owner_id = owner_id
    g.goal_name = name
    g.target_amount_paise = target
    g.current_amount_paise = target // 4
    g.target_date = date(2030, 1, 1)
    g.category = "RETIREMENT"
    g.is_active = True
    g.created_at = now
    g.updated_at = now
    return g


def _make_transaction(owner_id: uuid.UUID) -> Transaction:
    t = Transaction()
    t.id = uuid.uuid4()
    t.owner_id = owner_id
    t.account_id = uuid.uuid4()
    t.source_hash = "abc123"
    t.transaction_date = date(2025, 3, 15)
    t.amount_paise = -5000_00  # ₹5,000 debit
    t.transaction_type = "DEBIT"
    t.category = "GROCERIES"
    t.description = "Supermarket"
    t.raw_description = "Supermarket"
    t.merchant = "Big Bazaar"
    t.fiscal_year = "2024-25"
    t.currency = "INR"
    t.created_at = datetime.now(timezone.utc)
    return t


def _make_recommendation(owner_id: uuid.UUID) -> Recommendation:
    r = Recommendation()
    r.id = uuid.uuid4()
    r.owner_id = owner_id
    r.snapshot_id = uuid.uuid4()
    r.query = "Should I increase SIP?"
    r.plan_json = {}
    r.agent_outputs_json = []
    r.final_output_json = {}
    r.composite_confidence = 0.82
    r.current_state = "GENERATED"
    r.created_at = datetime.now(timezone.utc)
    return r


def _make_ingestion_run() -> IngestionRun:
    r = IngestionRun()
    r.id = uuid.uuid4()
    r.source = "GMAIL"
    r.trigger_type = "ADHOC"
    r.status = "SUCCESS"
    r.records_fetched = 10
    r.records_passed = 9
    r.records_quarantined = 1
    r.started_at = datetime.now(timezone.utc)
    r.completed_at = datetime.now(timezone.utc)
    r.error_message = None
    return r


# ---------------------------------------------------------------------------
# Goals router
# ---------------------------------------------------------------------------


@pytest.fixture()
def goals_client():
    app = FastAPI()
    app.include_router(goals_router)
    return TestClient(app)


class TestListGoals:
    def test_returns_goals(self, goals_client):
        owner = _make_owner()
        goal = _make_goal(owner.id)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [goal]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        goals_client.app.dependency_overrides[get_session] = override_session
        goals_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = goals_client.get(f"/owners/{owner.id}/goals")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["goal_name"] == "Retirement"
        assert data[0]["progress_pct"] == 25.0

    def test_forbidden_for_other_owner(self, goals_client):
        alice = _make_owner(is_admin=False)
        other_id = uuid.uuid4()

        async def override_current_owner():
            return alice

        goals_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = goals_client.get(f"/owners/{other_id}/goals")
        assert resp.status_code == 403

    def test_admin_can_list_others(self, goals_client):
        admin = _make_owner(is_admin=True)
        other_id = uuid.uuid4()
        goal = _make_goal(other_id)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [goal]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return admin

        goals_client.app.dependency_overrides[get_session] = override_session
        goals_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = goals_client.get(f"/owners/{other_id}/goals")
        assert resp.status_code == 200


class TestCreateGoal:
    def test_creates_goal(self, goals_client):
        owner = _make_owner()

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        async def _refresh(obj):
            obj.id = uuid.uuid4()
            obj.is_active = True
            obj.current_amount_paise = obj.current_amount_paise or 0
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)

        mock_session.refresh.side_effect = _refresh

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        goals_client.app.dependency_overrides[get_session] = override_session
        goals_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = goals_client.post(
            f"/owners/{owner.id}/goals",
            json={
                "goal_name": "Emergency Fund",
                "target_amount_paise": 5_00_000_00,
                "target_date": "2026-12-31",
                "category": "EMERGENCY",
            },
        )
        assert resp.status_code == 201

    def test_invalid_target_rejected(self, goals_client):
        owner = _make_owner()

        async def override_current_owner():
            return owner

        goals_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = goals_client.post(
            f"/owners/{owner.id}/goals",
            json={"goal_name": "Bad Goal", "target_amount_paise": 0},  # must be > 0
        )
        assert resp.status_code == 422


class TestPatchGoal:
    def test_updates_name(self, goals_client):
        owner = _make_owner()
        goal = _make_goal(owner.id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = goal
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        goals_client.app.dependency_overrides[get_session] = override_session
        goals_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = goals_client.patch(
            f"/owners/{owner.id}/goals/{goal.id}",
            json={"goal_name": "Early Retirement"},
        )
        assert resp.status_code == 200
        assert goal.goal_name == "Early Retirement"


class TestDeactivateGoal:
    def test_deactivates(self, goals_client):
        owner = _make_owner()
        goal = _make_goal(owner.id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = goal
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        goals_client.app.dependency_overrides[get_session] = override_session
        goals_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = goals_client.delete(f"/owners/{owner.id}/goals/{goal.id}")
        assert resp.status_code == 204
        assert goal.is_active is False


class TestProgressPct:
    def test_zero_current(self):
        from api.routers.goals import _progress_pct
        assert _progress_pct(0, 100_000) == 0.0

    def test_full(self):
        from api.routers.goals import _progress_pct
        assert _progress_pct(100_000, 100_000) == 100.0

    def test_over_target_capped(self):
        from api.routers.goals import _progress_pct
        assert _progress_pct(150_000, 100_000) == 100.0

    def test_partial(self):
        from api.routers.goals import _progress_pct
        assert _progress_pct(25_000, 100_000) == 25.0


# ---------------------------------------------------------------------------
# Transactions router
# ---------------------------------------------------------------------------


@pytest.fixture()
def transactions_client():
    app = FastAPI()
    app.include_router(transactions_router)
    return TestClient(app)


class TestListTransactions:
    def test_returns_transactions(self, transactions_client):
        owner = _make_owner()
        tx = _make_transaction(owner.id)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tx]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        transactions_client.app.dependency_overrides[get_session] = override_session
        transactions_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = transactions_client.get(f"/owners/{owner.id}/transactions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["category"] == "GROCERIES"

    def test_forbidden_for_non_owner(self, transactions_client):
        alice = _make_owner(is_admin=False)
        other_id = uuid.uuid4()

        async def override_current_owner():
            return alice

        transactions_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = transactions_client.get(f"/owners/{other_id}/transactions")
        assert resp.status_code == 403


class TestCsvExport:
    def test_csv_headers(self, transactions_client):
        owner = _make_owner()
        tx = _make_transaction(owner.id)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tx]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        transactions_client.app.dependency_overrides[get_session] = override_session
        transactions_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = transactions_client.get(f"/owners/{owner.id}/transactions.csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in resp.headers["content-disposition"]
        lines = resp.text.strip().split("\n")
        # Header row
        assert "amount_paise" in lines[0]
        assert "amount_inr" in lines[0]
        # Data row
        assert "GROCERIES" in lines[1]

    def test_csv_forbidden_for_other(self, transactions_client):
        alice = _make_owner(is_admin=False)
        other_id = uuid.uuid4()

        async def override_current_owner():
            return alice

        transactions_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = transactions_client.get(f"/owners/{other_id}/transactions.csv")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin router
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_client():
    app = FastAPI()
    app.include_router(admin_router)
    return TestClient(app)


class TestAdminAuditLog:
    def test_non_admin_blocked(self, admin_client):
        async def override_require_admin():
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Admin access required")

        admin_client.app.dependency_overrides[require_admin] = override_require_admin

        resp = admin_client.get("/admin/audit-log")
        assert resp.status_code == 403

    def test_returns_recommendations(self, admin_client):
        admin = _make_owner(is_admin=True)
        rec = _make_recommendation(admin.id)

        rec_result = MagicMock()
        rec_result.scalars.return_value.all.return_value = [rec]
        event_result = MagicMock()
        event_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.side_effect = [rec_result, event_result]

        async def override_session():
            yield mock_session

        async def override_require_admin():
            return admin

        admin_client.app.dependency_overrides[get_session] = override_session
        admin_client.app.dependency_overrides[require_admin] = override_require_admin

        resp = admin_client.get("/admin/audit-log")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["query"] == "Should I increase SIP?"
        assert data[0]["composite_confidence"] == 0.82


class TestAdminIngestionRuns:
    def test_returns_runs(self, admin_client):
        admin = _make_owner(is_admin=True)
        run = _make_ingestion_run()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [run]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_require_admin():
            return admin

        admin_client.app.dependency_overrides[get_session] = override_session
        admin_client.app.dependency_overrides[require_admin] = override_require_admin

        resp = admin_client.get("/admin/ingestion-runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["source"] == "GMAIL"


class TestAdminAgents:
    def test_lists_agents(self, admin_client):
        admin = _make_owner(is_admin=True)

        now = datetime.now(timezone.utc)
        agent = AgentRegistryEntry()
        agent.agent_id = "cashflow_agent"
        agent.capabilities = ["cashflow"]
        agent.status = "HEALTHY"
        agent.last_heartbeat = now
        agent.endpoint = "http://cashflow:8001"
        agent.scope = "individual"
        agent.schema_version = "1.0"
        agent.timeout_ms = 10000
        agent.fallback_strategy = "cached_response"
        agent.cache_ttl_hours = 1.0
        agent.registered_at = now
        agent.updated_at = now

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [agent]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_require_admin():
            return admin

        admin_client.app.dependency_overrides[get_session] = override_session
        admin_client.app.dependency_overrides[require_admin] = override_require_admin

        resp = admin_client.get("/admin/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["agent_id"] == "cashflow_agent"
        assert data[0]["status"] == "HEALTHY"
