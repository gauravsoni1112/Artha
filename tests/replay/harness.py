"""
Replay harness for Phase 5 recommendation pipeline.

Two modes:
  FIXTURE — dispatch is replaced by pre-recorded agent responses.
            Deterministic; no live agents required.  Suitable for CI.
  LIVE    — dispatch calls real agents, then diffs output against fixture.
            Surfaces drift in agent behaviour or confidence calibration.

Usage (FIXTURE):
    scenario = load_scenario("sip_increase")
    result = await replay(scenario, ReplayMode.FIXTURE, scope, profile, agents, session)
    assert result.critic_result.final_confidence > 0

Usage (LIVE):
    result = await replay(scenario, ReplayMode.LIVE, ..., registry=..., breaker=..., cache=...)
    for diff in result.diffs:
        print(diff)

Seeding from the audit log (future):
    rows = await session.execute(select(Recommendation).limit(100))
    for rec in rows.scalars():
        scenario = scenario_from_audit_row(rec)
        await replay(scenario, ReplayMode.FIXTURE, ...)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from libs.confidence.composition import AgentConfidenceInput, CompositeResult, compose
from libs.confidence.tier import FallbackTier
from libs.schemas.agent_envelope import AgentResponse
from libs.schemas.user_profile import UserProfile
from services.orchestrator.critic import CriticResult, evaluate as critic_evaluate
from services.orchestrator.decompose import RegisteredAgent, decompose
from services.orchestrator.dispatch import DispatchedResult
from services.orchestrator.plan import Plan
from services.orchestrator.scope import ScopeContext

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class ReplayMode(StrEnum):
    FIXTURE = "FIXTURE"
    LIVE = "LIVE"


@dataclass
class ReplayScenario:
    scenario_id: str
    query: str
    fixture_results: list[DispatchedResult]
    description: str = ""


@dataclass
class ReplayResult:
    plan: Plan
    dispatched_results: list[DispatchedResult]
    baseline: CompositeResult
    critic_result: CriticResult
    diffs: list[str] = field(default_factory=list)  # populated in LIVE mode


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def load_scenario(fixture_name: str) -> ReplayScenario:
    """
    Load a scenario from tests/replay/fixtures/{fixture_name}.json.
    Converts stored agent_responses into DispatchedResult objects (PRIMARY tier).
    """
    path = _FIXTURES_DIR / f"{fixture_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")

    data: dict[str, Any] = json.loads(path.read_text())

    fixture_results = [
        DispatchedResult(
            agent_id=r["agent_id"],
            response=AgentResponse.model_validate(r),
            fallback_tier=FallbackTier.PRIMARY,
        )
        for r in data["agent_responses"]
    ]

    return ReplayScenario(
        scenario_id=data["scenario_id"],
        query=data["query"],
        description=data.get("description", ""),
        fixture_results=fixture_results,
    )


def scenario_from_audit_row(
    query: str,
    agent_outputs_json: list[dict[str, Any]],
    scenario_id: str = "from_audit",
) -> ReplayScenario:
    """
    Reconstruct a ReplayScenario from a recommendations.agent_outputs_json row.
    Preserves the original fallback_tier so replays reflect the exact conditions.
    """
    results = []
    for entry in agent_outputs_json:
        tier = FallbackTier(entry.get("fallback_tier", "PRIMARY"))
        response = AgentResponse.model_validate(entry["response"]) if entry.get("response") else None
        results.append(
            DispatchedResult(
                agent_id=entry["agent_id"],
                response=response,
                fallback_tier=tier,
                error=entry.get("error"),
            )
        )
    return ReplayScenario(
        scenario_id=scenario_id,
        query=query,
        fixture_results=results,
    )


# ---------------------------------------------------------------------------
# Core replay engine
# ---------------------------------------------------------------------------


def _build_confidence_inputs(dispatched_results: list[DispatchedResult]) -> list[AgentConfidenceInput]:
    inputs = []
    for r in dispatched_results:
        if r.fallback_tier == FallbackTier.FAILURE:
            inputs.append(AgentConfidenceInput(r.agent_id, 0.0, FallbackTier.FAILURE))
        else:
            conf = r.response.confidence if r.response else 0.0
            inputs.append(AgentConfidenceInput(r.agent_id, conf, r.fallback_tier))
    return inputs


def _diff_results(
    fixture: list[DispatchedResult],
    live: list[DispatchedResult],
) -> list[str]:
    """Compare live results against fixture; return human-readable diff lines."""
    diffs: list[str] = []
    fixture_map = {r.agent_id: r for r in fixture}
    live_map = {r.agent_id: r for r in live}

    for agent_id, fix_r in fixture_map.items():
        if agent_id not in live_map:
            diffs.append(f"{agent_id}: present in fixture, MISSING in live run")
            continue
        live_r = live_map[agent_id]
        if live_r.fallback_tier != fix_r.fallback_tier:
            diffs.append(
                f"{agent_id}: tier changed {fix_r.fallback_tier} → {live_r.fallback_tier}"
            )
        if fix_r.response and live_r.response:
            fix_conf = fix_r.response.confidence
            live_conf = live_r.response.confidence
            if abs(live_conf - fix_conf) > 0.1:
                diffs.append(
                    f"{agent_id}: confidence drift {fix_conf:.2f} → {live_conf:.2f}"
                )

    for agent_id in live_map:
        if agent_id not in fixture_map:
            diffs.append(f"{agent_id}: NEW in live run, not in fixture")

    return diffs


async def replay(
    scenario: ReplayScenario,
    mode: ReplayMode,
    scope: ScopeContext,
    user_profile: UserProfile,
    available_agents: list[RegisteredAgent],
    # LIVE mode only — pass None for FIXTURE mode
    registry=None,
    breaker=None,
    response_cache=None,
) -> ReplayResult:
    """
    Run the reasoning pipeline for *scenario* in the specified *mode*.

    FIXTURE: uses scenario.fixture_results, no network calls.
    LIVE:    calls dispatch_plan (requires registry/breaker/cache), then diffs.
    """
    # 1. Decompose query → Plan (always rule-based, deterministic)
    plan = decompose(scenario.query, scope, available_agents)

    diffs: list[str] = []

    if mode == ReplayMode.FIXTURE:
        dispatched_results = scenario.fixture_results
    else:
        # LIVE: real dispatch
        from services.orchestrator.dispatch import dispatch_plan
        dispatched_results = await dispatch_plan(
            plan, user_profile, registry, breaker, response_cache
        )
        diffs = _diff_results(scenario.fixture_results, dispatched_results)

    # 2. Compose baseline confidence
    confidence_inputs = _build_confidence_inputs(dispatched_results)
    baseline = compose(confidence_inputs)

    # 3. Critic evaluate
    critic_result = critic_evaluate(scenario.query, dispatched_results, baseline)

    return ReplayResult(
        plan=plan,
        dispatched_results=dispatched_results,
        baseline=baseline,
        critic_result=critic_result,
        diffs=diffs,
    )
