"""Unit tests for access scope resolution."""

import uuid

import pytest

from libs.schemas.enums import AccessScope
from libs.schemas.user_profile import UserProfile
from services.orchestrator.scope import (
    ScopeMember,
    query_implies_family,
    resolve_scope,
)


def _profile(**kwargs) -> UserProfile:
    defaults = dict(owner_id=uuid.uuid4(), name="Rahul")
    defaults.update(kwargs)
    return UserProfile(**defaults)


def _members(primary: uuid.UUID, spouse: uuid.UUID | None = None, dependent: uuid.UUID | None = None) -> list[ScopeMember]:
    ms = [ScopeMember(owner_id=primary, scope=AccessScope.PRIMARY)]
    if spouse:
        ms.append(ScopeMember(owner_id=spouse, scope=AccessScope.SPOUSE))
    if dependent:
        ms.append(ScopeMember(owner_id=dependent, scope=AccessScope.DEPENDENT))
    return ms


# ---------------------------------------------------------------------------
# Individual scope
# ---------------------------------------------------------------------------


def test_individual_scope_returns_only_primary():
    primary = uuid.uuid4()
    spouse = uuid.uuid4()
    profile = _profile()
    members = _members(primary, spouse)

    ctx = resolve_scope(profile, members, query_requests_family=False)

    assert ctx.allowed_owner_ids == [primary]
    assert ctx.is_family_scope is False


def test_no_family_keywords_stays_individual():
    primary = uuid.uuid4()
    profile = _profile()
    members = _members(primary)

    ctx = resolve_scope(profile, members)
    assert ctx.is_family_scope is False
    assert primary in ctx.allowed_owner_ids


# ---------------------------------------------------------------------------
# Family scope
# ---------------------------------------------------------------------------


def test_family_scope_returns_all_members():
    primary, spouse, dep = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    profile = _profile()
    members = _members(primary, spouse, dep)

    ctx = resolve_scope(profile, members, query_requests_family=True)

    assert set(ctx.allowed_owner_ids) == {primary, spouse, dep}
    assert ctx.is_family_scope is True


def test_profile_is_family_scope_flag_overrides():
    primary, spouse = uuid.uuid4(), uuid.uuid4()
    profile = _profile(is_family_scope=True)
    members = _members(primary, spouse)

    ctx = resolve_scope(profile, members, query_requests_family=False)

    assert set(ctx.allowed_owner_ids) == {primary, spouse}
    assert ctx.is_family_scope is True


def test_family_flag_and_profile_flag_both_true():
    primary, spouse = uuid.uuid4(), uuid.uuid4()
    profile = _profile(is_family_scope=True)
    members = _members(primary, spouse)

    ctx = resolve_scope(profile, members, query_requests_family=True)
    assert set(ctx.allowed_owner_ids) == {primary, spouse}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_members_returns_empty():
    profile = _profile()
    ctx = resolve_scope(profile, [])
    assert ctx.allowed_owner_ids == []


def test_only_primary_member_family_scope_returns_one():
    primary = uuid.uuid4()
    profile = _profile()
    members = _members(primary)

    ctx = resolve_scope(profile, members, query_requests_family=True)
    assert ctx.allowed_owner_ids == [primary]
    assert ctx.is_family_scope is True


def test_no_primary_member_individual_scope_returns_empty():
    # Unusual but defensive: profile has only SPOUSE and DEPENDENT entries
    profile = _profile()
    spouse = uuid.uuid4()
    members = [ScopeMember(owner_id=spouse, scope=AccessScope.SPOUSE)]

    ctx = resolve_scope(profile, members, query_requests_family=False)
    assert ctx.allowed_owner_ids == []


# ---------------------------------------------------------------------------
# query_implies_family
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "our combined net worth",
        "family savings plan",
        "how much have we saved together",
        "joint expenses this month",
        "household budget",
    ],
)
def test_family_queries_detected(query: str):
    assert query_implies_family(query)


@pytest.mark.parametrize(
    "query",
    [
        "my SIP performance",
        "increase my investment",
        "should I save more?",
        "tax deductions available",
        "emergency fund status",
    ],
)
def test_individual_queries_not_flagged(query: str):
    assert not query_implies_family(query)
