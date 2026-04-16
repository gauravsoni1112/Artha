"""
FallbackTier — describes *how* the Planner obtained an agent response.

This is distinct from DataTier in agent_envelope.py, which describes the
freshness of data *inside* the agent's domain (REALTIME/CACHED/STALE/ESTIMATED).

FallbackTier is an orchestrator-level concept:
  - PRIMARY:   live HTTP call succeeded
  - SECONDARY: served from Redis cache, still within the agent's cache_ttl
  - TERTIARY:  stale Redis cache (TTL exceeded) or estimated from partial data
  - FAILURE:   agent could not be reached at all; excluded from composite

Confidence penalties are in percentage points (0–100 scale).
FAILURE has no penalty because the agent is excluded entirely — the Critic
flags the gap instead.
"""

from enum import StrEnum


class FallbackTier(StrEnum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    TERTIARY = "TERTIARY"
    FAILURE = "FAILURE"


# Penalty in percentage points, subtracted from an agent's base confidence (×100).
# The Critic may lower further but never raises above this baseline.
TIER_PENALTY: dict[FallbackTier, float] = {
    FallbackTier.PRIMARY: 0.0,
    FallbackTier.SECONDARY: -10.0,
    FallbackTier.TERTIARY: -25.0,
    FallbackTier.FAILURE: 0.0,  # excluded; not penalised — gap flagged by Critic
}
