"""
Serialisable Plan DAG (Phase 5).

A Plan is a list of AgentCall steps.  Steps with no depends_on can be
dispatched in parallel (asyncio.gather).  Steps with depends_on must wait
for the named agent_ids to complete first.

For Phase 5, all domain agents are independent — plans are mostly flat
parallel.  depends_on exists for future sequential chains (e.g. a
downstream Critic step that waits on all domain agents).

Plans are stored verbatim in recommendations.plan_json for replay.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AgentCall:
    """
    One node in the Plan DAG — a single agent invocation.

    agent_id:          target agent (matches agent_registry.agent_id)
    allowed_owner_ids: pre-resolved scope; serialised as str UUIDs in JSON
    context:           extra structured context merged into AgentRequest.context
    depends_on:        agent_ids that must complete before this call starts
    """

    agent_id: str
    allowed_owner_ids: list[uuid.UUID]
    context: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "allowed_owner_ids": [str(oid) for oid in self.allowed_owner_ids],
            "context": self.context,
            "depends_on": list(self.depends_on),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentCall":
        return cls(
            agent_id=d["agent_id"],
            allowed_owner_ids=[uuid.UUID(oid) for oid in d["allowed_owner_ids"]],
            context=d.get("context", {}),
            depends_on=d.get("depends_on", []),
        )


@dataclass
class Plan:
    """
    Ordered execution plan for one recommendation request.

    steps:          AgentCall list; use parallel_steps() / sequential_steps()
                    to split by execution mode.
    original_query: verbatim user query (stored in audit log for replay).
    plan_id:        stable ID for tracing correlation.
    created_at:     frozen at plan-creation time for audit reproducibility.
    """

    original_query: str
    steps: list[AgentCall]
    plan_id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

    def parallel_steps(self) -> list[AgentCall]:
        """Steps with no depends_on — safe to gather concurrently."""
        return [s for s in self.steps if not s.depends_on]

    def sequential_steps(self) -> list[AgentCall]:
        """Steps that depend on prior agent completions."""
        return [s for s in self.steps if s.depends_on]

    def agent_ids(self) -> list[str]:
        return [s.agent_id for s in self.steps]

    # ------------------------------------------------------------------
    # Serialisation (stored in recommendations.plan_json)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": str(self.plan_id),
            "original_query": self.original_query,
            "created_at": self.created_at.isoformat(),
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Plan":
        return cls(
            plan_id=uuid.UUID(d["plan_id"]),
            original_query=d["original_query"],
            created_at=datetime.fromisoformat(d["created_at"]),
            steps=[AgentCall.from_dict(s) for s in d["steps"]],
        )
