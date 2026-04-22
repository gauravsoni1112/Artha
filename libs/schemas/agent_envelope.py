"""
Agent contract envelopes (Phase 4).

Every agent receives an AgentRequest and returns an AgentResponse.
The envelope is the ONLY integration surface between the router and agents.

Schema versioning:
  - schema_version = "1.0" for Phase 4
  - Agents must tolerate unknown fields in requests (extra="ignore")
  - Routers must tolerate unknown fields in responses (extra="ignore")

Data tiers:
  REALTIME  — queried live from DB (<1 min old)
  CACHED    — served from Redis cache
  STALE     — cache expired, background refresh pending
  ESTIMATED — computed from partial data
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from libs.schemas.user_profile import UserProfile


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DataTier(StrEnum):
    REALTIME = "REALTIME"
    CACHED = "CACHED"
    STALE = "STALE"
    ESTIMATED = "ESTIMATED"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AgentScope(StrEnum):
    INDIVIDUAL = "individual"
    FAMILY = "family"


# ---------------------------------------------------------------------------
# Request envelope
# ---------------------------------------------------------------------------


class AgentRequest(BaseModel):
    """Sent by the router to a domain agent."""

    model_config = {"extra": "ignore"}

    query: str = Field(..., description="Natural-language question for the agent")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured context (e.g. date range, account filter)",
    )
    user_profile: UserProfile
    trace_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    request_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------


class AgentResponse(BaseModel):
    """Returned by every domain agent."""

    model_config = {"extra": "ignore"}

    agent_id: str = Field(..., description="Stable agent identifier, e.g. 'cashflow_agent'")
    schema_version: str = Field("1.0")
    trace_id: uuid.UUID

    # Data provenance
    data_tier: DataTier
    data_freshness_hours: float = Field(
        ..., ge=0, description="How old is the underlying data (hours)"
    )

    # Answer payload
    result: dict[str, Any] = Field(..., description="Structured answer from the agent")
    confidence: float = Field(..., ge=0.0, le=1.0)
    risk_level: RiskLevel
    reasoning: str = Field(..., description="Chain-of-thought / explanation")
    warnings: list[str] = Field(default_factory=list)

    # Tool provenance — names of tools actually called during execution
    tools_used: list[str] = Field(default_factory=list)

    # Fallback
    fallback_used: bool = False
    fallback_reason: str | None = None
