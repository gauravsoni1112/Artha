"""
Critic Agent (Phase 5).

Evaluates all agent outputs AFTER the Planner has dispatched and collected
responses.  Applies deterministic consistency checks and schema validation,
then adjusts the composite confidence score **downward only**.

Design invariant: the Critic can only LOWER confidence, never raise it.
The baseline from compose() is the ceiling; Critic reduces from there.

Penalty schedule (additive, floored at 0.0):
  GAP_PENALTY_PP         5.0  per FAILURE-tier agent (data missing)
  INCONSISTENCY_PP       5.0  per detected cross-agent inconsistency
  UNKNOWN_SCHEMA_PP      3.0  per agent with unknown schema_version
  Maximum Critic penalty: 30.0 pp

Checks implemented:
  1. surplus_paise cross-check    — agents that both report surplus must agree ≤15%
  2. net_worth_paise cross-check  — same for net worth
  3. time_horizon cross-check     — goal target_years vs risk time_horizon_years ≤5yr delta
  4. schema_version validation    — only "1.0" is currently known

Adding a new check: implement `_CheckFn = Callable[[list[DispatchedResult]], list[ConsistencyFlag]]`
and append it to _CHECKS at module level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from libs.confidence.composition import CompositeResult
from libs.confidence.tier import FallbackTier
from services.orchestrator.dispatch import DispatchedResult
from services.orchestrator.metrics import record_critic_flag

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GAP_PENALTY_PP: float = 5.0
INCONSISTENCY_PP: float = 5.0
UNKNOWN_SCHEMA_PP: float = 3.0
MAX_CRITIC_PENALTY_PP: float = 30.0

KNOWN_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0"})

# Relative tolerance for numeric cross-checks (15 %)
_NUMERIC_TOLERANCE = 0.15

# Absolute difference tolerance below which cross-check is skipped (₹1 000 = 100 000 paise)
# Avoids noise when agents report near-zero values.
_NUMERIC_MIN_PAISE = 100_000


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsistencyFlag:
    check_type: str             # e.g. "surplus_mismatch"
    agent_ids: list[str]        # agents involved
    description: str
    confidence_penalty: float   # pp to subtract from composite


@dataclass
class CriticResult:
    """
    Output of the Critic — passed directly into the audit writer.

    final_confidence:    adjusted score (≤ baseline_confidence)
    baseline_confidence: score from compose() before Critic ran
    total_penalty:       total pp subtracted by the Critic
    consistency_flags:   per-check findings
    schema_warnings:     agents with unrecognised schema_version
    gaps:                agent_ids with FAILURE tier (from baseline)
    warnings:            combined tier + Critic narrative warnings
    """

    final_confidence: float
    baseline_confidence: float
    total_penalty: float
    consistency_flags: list[ConsistencyFlag] = field(default_factory=list)
    schema_warnings: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------

_CheckFn = Callable[[list[DispatchedResult]], list[ConsistencyFlag]]


def _active(results: list[DispatchedResult]) -> list[DispatchedResult]:
    """Filter to results that have a response (non-FAILURE)."""
    return [r for r in results if r.response is not None]


def _check_numeric_field(
    results: list[DispatchedResult],
    field_name: str,
    check_type: str,
    label: str,
) -> list[ConsistencyFlag]:
    """
    Generic numeric cross-check: if ≥2 agents report the same field,
    flag if the relative spread exceeds _NUMERIC_TOLERANCE.
    """
    values: dict[str, int] = {}
    for r in _active(results):
        v = r.response.result.get(field_name)  # type: ignore[union-attr]
        if isinstance(v, (int, float)):
            values[r.agent_id] = int(v)

    if len(values) < 2:
        return []

    max_v = max(abs(v) for v in values.values())
    if max_v < _NUMERIC_MIN_PAISE:
        return []  # values too small to care about

    vals = list(values.values())
    spread = (max(vals) - min(vals)) / max_v
    if spread <= _NUMERIC_TOLERANCE:
        return []

    agents = list(values.keys())
    return [
        ConsistencyFlag(
            check_type=check_type,
            agent_ids=agents,
            description=(
                f"{label} values differ by {spread:.0%} across {agents}; "
                f"values (paise): {values}"
            ),
            confidence_penalty=INCONSISTENCY_PP,
        )
    ]


def _check_surplus(results: list[DispatchedResult]) -> list[ConsistencyFlag]:
    flags = _check_numeric_field(results, "surplus_paise", "surplus_mismatch", "Surplus")
    if flags:
        record_critic_flag("surplus_mismatch")
    return flags


def _check_net_worth(results: list[DispatchedResult]) -> list[ConsistencyFlag]:
    flags = _check_numeric_field(results, "net_worth_paise", "net_worth_mismatch", "Net worth")
    if flags:
        record_critic_flag("net_worth_mismatch")
    return flags


def _check_time_horizon(results: list[DispatchedResult]) -> list[ConsistencyFlag]:
    """
    Cross-check goal agent's target_years vs risk agent's time_horizon_years.
    Flag if they differ by more than 5 years.
    """
    goal_years: int | None = None
    risk_years: int | None = None
    goal_agent = risk_agent = None

    for r in _active(results):
        result = r.response.result  # type: ignore[union-attr]
        if r.agent_id == "goal_agent" and "target_years" in result:
            goal_years = int(result["target_years"])
            goal_agent = r.agent_id
        if r.agent_id == "risk_agent" and "time_horizon_years" in result:
            risk_years = int(result["time_horizon_years"])
            risk_agent = r.agent_id

    if goal_years is None or risk_years is None:
        return []

    delta = abs(goal_years - risk_years)
    if delta <= 5:
        return []

    record_critic_flag("time_horizon_mismatch")
    return [
        ConsistencyFlag(
            check_type="time_horizon_mismatch",
            agent_ids=[goal_agent, risk_agent],  # type: ignore[list-item]
            description=(
                f"goal target_years={goal_years} vs risk time_horizon_years={risk_years} "
                f"(delta={delta} years)"
            ),
            confidence_penalty=INCONSISTENCY_PP,
        )
    ]


_CHECKS: list[_CheckFn] = [
    _check_surplus,
    _check_net_worth,
    _check_time_horizon,
]


# ---------------------------------------------------------------------------
# Schema version validation
# ---------------------------------------------------------------------------


def _check_schema_versions(results: list[DispatchedResult]) -> list[str]:
    warnings: list[str] = []
    for r in _active(results):
        v = r.response.schema_version  # type: ignore[union-attr]
        if v not in KNOWN_SCHEMA_VERSIONS:
            warnings.append(
                f"{r.agent_id}: unknown schema_version={v!r} — "
                "response accepted but extra validation recommended"
            )
    return warnings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def evaluate(
    query: str,  # noqa: ARG001  — reserved for future LLM narrative check
    dispatched_results: list[DispatchedResult],
    baseline: CompositeResult,
) -> CriticResult:
    """
    Run all consistency checks and produce a CriticResult.

    Args:
        query:             Original user query (reserved for future LLM check).
        dispatched_results: Full list from dispatch_plan() — includes FAILURE entries.
        baseline:          CompositeResult from compose() — score is the ceiling.

    Returns:
        CriticResult with final_confidence ≤ baseline.score.
    """
    flags: list[ConsistencyFlag] = []
    for check in _CHECKS:
        flags.extend(check(dispatched_results))

    schema_warnings = _check_schema_versions(dispatched_results)

    # Compute penalty
    inconsistency_penalty = sum(f.confidence_penalty for f in flags)
    gap_penalty = len(baseline.gaps) * GAP_PENALTY_PP
    schema_penalty = len(schema_warnings) * UNKNOWN_SCHEMA_PP

    total_penalty = min(
        inconsistency_penalty + gap_penalty + schema_penalty,
        MAX_CRITIC_PENALTY_PP,
    )
    final_confidence = max(0.0, baseline.score - total_penalty)

    # Merge warnings
    all_warnings = list(baseline.warnings)
    if baseline.gaps:
        all_warnings.append(
            f"Missing data from: {', '.join(baseline.gaps)} — recommendation may be incomplete"
        )
    for f in flags:
        all_warnings.append(f"Consistency issue ({f.check_type}): {f.description}")

    return CriticResult(
        final_confidence=round(final_confidence, 2),
        baseline_confidence=baseline.score,
        total_penalty=round(total_penalty, 2),
        consistency_flags=flags,
        schema_warnings=schema_warnings,
        gaps=baseline.gaps,
        warnings=all_warnings,
    )
