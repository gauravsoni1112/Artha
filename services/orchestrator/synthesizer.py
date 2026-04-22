"""
SynthesizerNode (Phase 5 — Item 2 fix).

After the Critic adjusts confidence, all domain-agent answers exist as
separate strings.  This module makes one LLM call to merge them into a
single, coherent narrative that the user actually reads.

Design decisions:
- Uses RoutingPolicy.from_env(LLMRole.SYNTHESIZER) — model/destination
  controlled entirely via env vars (SYNTHESIZER_MODEL, etc.).
- Falls back to a plain concatenation if the LLM call fails, so the
  orchestrator never hard-fails just because synthesis is unavailable.
- Skips agents with FAILURE tier (no data to include).
- Thinking mode disabled (/no_think) for speed; synthesis doesn't need CoT.
"""

from __future__ import annotations

import re
import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from libs.confidence.tier import FallbackTier
from libs.privacy.anonymiser import default_anonymiser
from libs.privacy.pii_scanner import default_scanner
from libs.privacy.token_map import TokenMap
from libs.telemetry.langfuse_handler import get_callback_handler
from services.agent.config import LLMRole, RoutingPolicy
from services.orchestrator.critic import CriticResult
from services.orchestrator.dispatch import DispatchedResult

log = structlog.get_logger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

_SYSTEM_PROMPT = """\
You are Artha, a personal finance assistant. You have received domain-specific \
analysis from multiple specialist agents. Your job is to merge their findings \
into a single, fluent, integrated response for the user.

Rules:
- Write in second person ("You have...", "Your portfolio...").
- Do NOT use section headers or bullet lists — write flowing prose.
- Integrate insights across domains naturally (e.g. connect surplus to goals, \
  debt to risk).
- Express all amounts in Indian Rupee format (₹X,XX,XXX).
- If agents disagree on a figure, note the uncertainty briefly.
- Omit agents that had no data (marked as unavailable below).
- Keep the response concise: 150–300 words unless the query demands more detail.
"""


def _agent_contributed(r: DispatchedResult) -> bool:
    """True if the agent actually called tools and produced a usable answer.

    An agent that returned an answer string but called zero tools almost
    certainly hallucinated — it had no domain tool to answer the query.
    Treat it the same as a FAILURE so the synthesizer omits it rather than
    presenting fabricated data to the user.
    """
    if r.fallback_tier == FallbackTier.FAILURE or r.response is None:
        return False
    if not r.response.tools_used:
        return False
    return bool(r.response.result.get("answer", "").strip())


def _build_user_prompt(
    query: str,
    dispatched_results: list[DispatchedResult],
    critic_result: CriticResult | None = None,
) -> str:
    lines = [f"User question: {query}\n\nAgent findings:"]
    for r in dispatched_results:
        if not _agent_contributed(r):
            reason = r.error or ("no tools called" if r.response is not None else "no data")
            lines.append(f"\n[{r.agent_id}]: unavailable — {reason}")
            continue
        answer = r.response.result.get("answer", "").strip()  # type: ignore[union-attr]
        if answer:
            lines.append(f"\n[{r.agent_id}]:\n{answer}")

    if critic_result is not None:
        if critic_result.gaps:
            lines.append(
                f"\nData gaps (agents with no data): {', '.join(critic_result.gaps)}."
                " Acknowledge these limitations in your response."
            )
        if critic_result.warnings:
            lines.append(
                "\nQuality warnings from consistency checks:\n"
                + "\n".join(f"- {w}" for w in critic_result.warnings)
                + "\nReflect these caveats appropriately."
            )

    lines.append("\nWrite a unified response:")
    return "\n".join(lines)


def _scrub_messages_for_cloud(
    messages: list, tm: TokenMap, context: str
) -> list:
    """Scrub messages with full anonymiser pipeline and verify clean via PIIScanner.

    Uses TokenMap so names/merchants are tokenised reversibly (detokenise after
    the cloud LLM responds).  Raises ValueError if PII survives scrubbing.
    """
    scrubbed = default_anonymiser.scrub_messages(messages, tm)
    combined = " ".join(m.content for m in scrubbed if isinstance(m.content, str))
    default_scanner.assert_safe_for_cloud(combined, context=context)
    return scrubbed


def _fallback_concat(dispatched_results: list[DispatchedResult]) -> str:
    parts = []
    for r in dispatched_results:
        if _agent_contributed(r):
            answer = r.response.result.get("answer", "").strip()  # type: ignore[union-attr]
            if answer:
                parts.append(answer)
    return "\n\n".join(parts) if parts else "No agent data available."


async def synthesize(
    query: str,
    dispatched_results: list[DispatchedResult],
    critic_result: CriticResult | None = None,
    trace_id: str = "",
) -> str:
    """
    Merge all agent answers into one narrative. Falls back to concatenation
    on any LLM error so the orchestrator pipeline never breaks.
    """
    # Skip the LLM call entirely when no agent produced useful tool-backed output.
    has_content = any(_agent_contributed(r) for r in dispatched_results)
    if not has_content:
        log.info("synthesizer.skipped_no_agent_data", trace_id=trace_id)
        return _fallback_concat(dispatched_results)

    try:
        policy = RoutingPolicy.from_env(LLMRole.SYNTHESIZER)
        llm = policy.build_chat_model()

        user_prompt = _build_user_prompt(query, dispatched_results, critic_result)

        system_content = _SYSTEM_PROMPT
        if policy.provider == "ollama":
            system_content = "/no_think\n" + system_content

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=user_prompt),
        ]

        tm: TokenMap | None = None

        if policy.destination == "cloud" and policy.anonymise:
            tm = TokenMap()
            try:
                messages = _scrub_messages_for_cloud(
                    messages, tm, context=f"synthesizer.trace={trace_id}"
                )
                log.debug("synthesizer.cloud_scrub_ok", trace_id=trace_id)
            except ValueError as pii_exc:
                log.warning(
                    "synthesizer.pii_fallback",
                    trace_id=trace_id,
                    error=str(pii_exc),
                )
                return _fallback_concat(dispatched_results)

        lf_handler = get_callback_handler(
            trace_id=trace_id,
            metadata={"agent_id": "orchestrator"},
            node_name="synthesizer",
        ) if trace_id else None
        lf_config = {"callbacks": [lf_handler]} if lf_handler is not None else {}

        response = await llm.ainvoke(messages, config=lf_config)
        answer = response.content if hasattr(response, "content") else str(response)
        answer = answer.strip()

        # Detokenise names/merchants that the cloud model may have echoed back
        if tm is not None:
            answer = default_anonymiser.detokenise_answer(answer, tm)

        log.info(
            "synthesizer.complete",
            trace_id=trace_id,
            model=policy.model,
            destination=policy.destination,
            answer_len=len(answer),
        )
        return answer

    except Exception as exc:
        log.warning("synthesizer.fallback", trace_id=trace_id, error=str(exc))
        return _fallback_concat(dispatched_results)
