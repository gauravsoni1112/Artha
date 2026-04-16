"""
Unit tests for api/routers/auth.py, api/routers/owners.py,
api/routers/accounts.py, and api/routers/profile.py.

All tests use TestClient with dependency_overrides — no real DB or Redis needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.database import get_session
from api.deps import create_token, current_owner, hash_pin, require_admin, verify_pin
from api.routers.auth import router as auth_router
from api.routers.owners import router as owners_router
from api.routers.accounts import router as accounts_router
from api.routers.profile import router as profile_router
from libs.schemas.db_models import Account, FamilyMembership, Owner, UserProfile, UserProfileScope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_owner(
    name: str = "Alice",
    is_admin: bool = False,
    pin: str | None = None,
) -> Owner:
    now = datetime.now(timezone.utc)
    o = Owner()
    o.id = uuid.uuid4()
    o.name = name
    o.pan_hash = None
    o.is_admin = is_admin
    o.pin_hash = hash_pin(pin) if pin else None
    o.created_at = now
    o.updated_at = now
    return o


def _make_account(owner_id: uuid.UUID) -> Account:
    a = Account()
    a.id = uuid.uuid4()
    a.owner_id = owner_id
    a.account_type = "SAVINGS"
    a.institution = "HDFC Bank"
    a.nickname = "Main Savings"
    a.account_number_hash = None
    a.is_active = True
    a.created_at = datetime.now(timezone.utc)
    return a


def _make_profile(owner_id: uuid.UUID) -> UserProfile:
    now = datetime.now(timezone.utc)
    p = UserProfile()
    p.id = uuid.uuid4()
    p.owner_id = owner_id
    p.risk_appetite = "moderate"
    p.age = 32
    p.is_family_scope = False
    p.total_monthly_income_paise = 10_000_00  # ₹1,00,000
    p.income_sources_json = []
    p.emis_json = []
    p.preferences = {}
    p.scopes = []
    p.created_at = now
    p.updated_at = now
    return p


# ---------------------------------------------------------------------------
# deps helpers — test directly
# ---------------------------------------------------------------------------


class TestPinHashing:
    def test_roundtrip(self):
        stored = hash_pin("1234")
        assert verify_pin("1234", stored) is True

    def test_wrong_pin(self):
        stored = hash_pin("1234")
        assert verify_pin("9999", stored) is False

    def test_different_salts_produce_different_hashes(self):
        h1 = hash_pin("1234")
        h2 = hash_pin("1234")
        assert h1 != h2  # Different random salts


class TestTokenRoundtrip:
    def test_valid_token(self):
        owner_id = uuid.uuid4()
        token = create_token(owner_id)
        assert "." in token

    def test_token_has_two_parts(self):
        token = create_token(uuid.uuid4())
        parts = token.split(".")
        assert len(parts) == 2


# ---------------------------------------------------------------------------
# Auth router
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_client():
    app = FastAPI()
    app.include_router(auth_router)
    return TestClient(app)


class TestAuthLogin:
    def test_missing_owner(self, auth_client):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        auth_client.app.dependency_overrides[get_session] = override_session

        resp = auth_client.post(
            "/auth/login", json={"owner_id": str(uuid.uuid4()), "pin": "1234"}
        )
        assert resp.status_code == 401

    def test_wrong_pin(self, auth_client):
        owner = _make_owner(pin="5678")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = owner
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        auth_client.app.dependency_overrides[get_session] = override_session

        resp = auth_client.post(
            "/auth/login", json={"owner_id": str(owner.id), "pin": "9999"}
        )
        assert resp.status_code == 401

    def test_correct_pin(self, auth_client):
        owner = _make_owner(pin="1234")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = owner
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        auth_client.app.dependency_overrides[get_session] = override_session

        resp = auth_client.post(
            "/auth/login", json={"owner_id": str(owner.id), "pin": "1234"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["is_admin"] is False

    def test_correct_pin_admin(self, auth_client):
        owner = _make_owner(is_admin=True, pin="securepin")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = owner
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        auth_client.app.dependency_overrides[get_session] = override_session

        resp = auth_client.post(
            "/auth/login", json={"owner_id": str(owner.id), "pin": "securepin"}
        )
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True


class TestAuthLogout:
    def test_logout_always_200(self, auth_client):
        resp = auth_client.post("/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestAuthMe:
    def test_me_returns_owner(self, auth_client):
        owner = _make_owner(name="Bob", is_admin=True)

        async def override_current_owner():
            return owner

        auth_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = auth_client.get("/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Bob"
        assert data["is_admin"] is True


# ---------------------------------------------------------------------------
# Owners router
# ---------------------------------------------------------------------------


@pytest.fixture()
def owners_client():
    app = FastAPI()
    app.include_router(owners_router)
    return TestClient(app)


class TestListOwners:
    def test_returns_list(self, owners_client):
        alice = _make_owner("Alice")
        bob = _make_owner("Bob", is_admin=True)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [alice, bob]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return alice

        owners_client.app.dependency_overrides[get_session] = override_session
        owners_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = owners_client.get("/owners")
        assert resp.status_code == 200
        names = [o["name"] for o in resp.json()]
        assert "Alice" in names
        assert "Bob" in names


class TestGetOwner:
    def test_found(self, owners_client):
        alice = _make_owner("Alice")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = alice
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return alice

        owners_client.app.dependency_overrides[get_session] = override_session
        owners_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = owners_client.get(f"/owners/{alice.id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Alice"

    def test_not_found(self, owners_client):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        admin = _make_owner(is_admin=True)

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return admin

        owners_client.app.dependency_overrides[get_session] = override_session
        owners_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = owners_client.get(f"/owners/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestCreateOwner:
    def test_non_admin_forbidden(self, owners_client):
        async def override_require_admin():
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Admin access required")

        owners_client.app.dependency_overrides[require_admin] = override_require_admin

        resp = owners_client.post("/owners", json={"name": "Eve"})
        assert resp.status_code == 403

    def test_admin_can_create(self, owners_client):
        admin = _make_owner("Admin", is_admin=True)

        mock_session = AsyncMock()
        mock_session.add = MagicMock()  # add() is synchronous in SQLAlchemy
        mock_session.commit = AsyncMock()

        # refresh populates the new Owner instance with required fields
        async def _refresh_side_effect(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)

        mock_session.refresh.side_effect = _refresh_side_effect

        async def override_session():
            yield mock_session

        async def override_require_admin():
            return admin

        owners_client.app.dependency_overrides[get_session] = override_session
        owners_client.app.dependency_overrides[require_admin] = override_require_admin

        resp = owners_client.post("/owners", json={"name": "NewUser", "pin": "4321"})
        assert resp.status_code == 201


class TestSetPin:
    def test_set_pin(self, owners_client):
        admin = _make_owner("Admin", is_admin=True)
        target = _make_owner("Target")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        async def override_session():
            yield mock_session

        async def override_require_admin():
            return admin

        owners_client.app.dependency_overrides[get_session] = override_session
        owners_client.app.dependency_overrides[require_admin] = override_require_admin

        resp = owners_client.post(f"/owners/{target.id}/pin", json={"pin": "newsecurepin"})
        assert resp.status_code == 204
        assert target.pin_hash is not None


# ---------------------------------------------------------------------------
# Accounts router
# ---------------------------------------------------------------------------


@pytest.fixture()
def accounts_client():
    app = FastAPI()
    app.include_router(accounts_router)
    return TestClient(app)


class TestListAccounts:
    def test_self_access(self, accounts_client):
        owner = _make_owner("Alice")
        acct = _make_account(owner.id)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [acct]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        accounts_client.app.dependency_overrides[get_session] = override_session
        accounts_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = accounts_client.get(f"/owners/{owner.id}/accounts")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["institution"] == "HDFC Bank"

    def test_other_owner_forbidden_non_admin(self, accounts_client):
        alice = _make_owner("Alice", is_admin=False)
        other_id = uuid.uuid4()

        async def override_current_owner():
            return alice

        accounts_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = accounts_client.get(f"/owners/{other_id}/accounts")
        assert resp.status_code == 403

    def test_admin_can_access_others(self, accounts_client):
        admin = _make_owner("Admin", is_admin=True)
        other_id = uuid.uuid4()
        acct = _make_account(other_id)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [acct]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return admin

        accounts_client.app.dependency_overrides[get_session] = override_session
        accounts_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = accounts_client.get(f"/owners/{other_id}/accounts")
        assert resp.status_code == 200


class TestDeactivateAccount:
    def test_deactivates(self, accounts_client):
        owner = _make_owner("Alice")
        acct = _make_account(owner.id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = acct
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        accounts_client.app.dependency_overrides[get_session] = override_session
        accounts_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = accounts_client.delete(f"/owners/{owner.id}/accounts/{acct.id}")
        assert resp.status_code == 204
        assert acct.is_active is False

    def test_not_found(self, accounts_client):
        owner = _make_owner("Alice")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        accounts_client.app.dependency_overrides[get_session] = override_session
        accounts_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = accounts_client.delete(f"/owners/{owner.id}/accounts/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Profile router
# ---------------------------------------------------------------------------


@pytest.fixture()
def profile_client():
    app = FastAPI()
    app.include_router(profile_router)
    return TestClient(app)


class TestGetProfile:
    def test_returns_profile(self, profile_client):
        owner = _make_owner("Alice")
        profile = _make_profile(owner.id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = profile
        mock_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        profile_client.app.dependency_overrides[get_session] = override_session
        profile_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = profile_client.get(f"/owners/{owner.id}/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_appetite"] == "moderate"
        assert data["age"] == 32

    def test_not_found(self, profile_client):
        owner = _make_owner("Alice")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        profile_client.app.dependency_overrides[get_session] = override_session
        profile_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = profile_client.get(f"/owners/{owner.id}/profile")
        assert resp.status_code == 404

    def test_other_owner_forbidden(self, profile_client):
        alice = _make_owner("Alice", is_admin=False)
        other_id = uuid.uuid4()

        async def override_current_owner():
            return alice

        profile_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = profile_client.get(f"/owners/{other_id}/profile")
        assert resp.status_code == 403


class TestPatchProfile:
    def test_patch_risk_appetite(self, profile_client):
        owner = _make_owner("Alice")
        profile = _make_profile(owner.id)
        empty_scopes = MagicMock(**{"scalars.return_value.all.return_value": []})

        # _load_profile_with_scopes = 2 executes (profile + scopes)
        # after commit/refresh: 1 more execute for scopes reload = 3 total
        results = [
            MagicMock(**{"scalar_one_or_none.return_value": profile}),
            empty_scopes,
            empty_scopes,
        ]
        mock_session = AsyncMock()
        mock_session.execute.side_effect = results
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        profile_client.app.dependency_overrides[get_session] = override_session
        profile_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = profile_client.patch(
            f"/owners/{owner.id}/profile", json={"risk_appetite": "aggressive"}
        )
        assert resp.status_code == 200
        assert profile.risk_appetite == "aggressive"

    def test_patch_preferences_merges(self, profile_client):
        owner = _make_owner("Alice")
        profile = _make_profile(owner.id)
        profile.preferences = {"theme": "light"}
        empty_scopes = MagicMock(**{"scalars.return_value.all.return_value": []})

        results = [
            MagicMock(**{"scalar_one_or_none.return_value": profile}),
            empty_scopes,
            empty_scopes,
        ]
        mock_session = AsyncMock()
        mock_session.execute.side_effect = results
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        async def override_session():
            yield mock_session

        async def override_current_owner():
            return owner

        profile_client.app.dependency_overrides[get_session] = override_session
        profile_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = profile_client.patch(
            f"/owners/{owner.id}/profile", json={"preferences": {"currency": "INR"}}
        )
        assert resp.status_code == 200
        # Existing key preserved, new key added
        assert profile.preferences == {"theme": "light", "currency": "INR"}

    def test_invalid_risk_appetite(self, profile_client):
        owner = _make_owner("Alice")

        async def override_current_owner():
            return owner

        profile_client.app.dependency_overrides[current_owner] = override_current_owner

        resp = profile_client.patch(
            f"/owners/{owner.id}/profile", json={"risk_appetite": "YOLO"}
        )
        assert resp.status_code == 422
