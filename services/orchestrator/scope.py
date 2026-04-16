"""
Access scope resolution (Phase 5).

The Planner calls resolve_scope() BEFORE dispatching any agent.
Agents receive only the allowed_owner_ids; they never see this logic.

Rules:
  - family scope: query covers all scoped members (PRIMARY + SPOUSE + DEPENDENT)
  - individual scope: query covers PRIMARY owner only
  - family scope triggers when: profile.is_family_scope=True OR caller passes
    query_requests_family=True (e.g. "our family savings", "combined net worth")

The caller (Planner) is responsible for loading ScopeMember records from the DB
and passing them in. This function is a pure computation — no DB access.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from libs.schemas.enums import AccessScope
from libs.schemas.user_profile import UserProfile


@dataclass(frozen=True)
class ScopeMember:
    """Lightweight projection of a UserProfileScope DB row."""

    owner_id: uuid.UUID
    scope: AccessScope


@dataclass(frozen=True)
class ScopeContext:
    """
    Result of scope resolution — passed into every AgentCall.

    allowed_owner_ids: the owner UUIDs the agent is permitted to query.
    is_family_scope:   True if the resolution included non-PRIMARY members.
    """

    allowed_owner_ids: list[uuid.UUID]
    is_family_scope: bool


def resolve_scope(
    profile: UserProfile,
    members: list[ScopeMember],
    query_requests_family: bool = False,
) -> ScopeContext:
    """
    Determine which owner_ids are accessible for this query.

    Args:
        profile:               The primary user's profile (Pydantic).
        members:               All scope memberships for this profile.
        query_requests_family: True when the NL query implies family context
                               (detected by the Planner before calling here).

    Returns:
        ScopeContext with allowed_owner_ids pre-filtered for agent dispatch.
    """
    use_family = profile.is_family_scope or query_requests_family

    if use_family:
        return ScopeContext(
            allowed_owner_ids=[m.owner_id for m in members],
            is_family_scope=True,
        )

    primary_ids = [m.owner_id for m in members if m.scope == AccessScope.PRIMARY]
    return ScopeContext(allowed_owner_ids=primary_ids, is_family_scope=False)


# ---------------------------------------------------------------------------
# Family-query detection heuristics (Planner calls this, not agents)
# ---------------------------------------------------------------------------

_FAMILY_KEYWORDS = frozenset(
    {
        "our", "we", "family", "combined", "together", "household",
        "spouse", "wife", "husband", "joint", "dependents",
    }
)


def query_implies_family(query: str) -> bool:
    """
    Lightweight keyword check — True if query text suggests family-scope.
    The Planner passes this result as query_requests_family to resolve_scope().
    """
    tokens = query.lower().split()
    return bool(_FAMILY_KEYWORDS & set(tokens))
