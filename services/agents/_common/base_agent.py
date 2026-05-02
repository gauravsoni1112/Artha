"""
BaseAgent — abstract base class for all Phase 4 domain agents.

Each domain agent:
  1. Subclasses BaseAgent.
  2. Declares AGENT_ID and CAPABILITIES as class attributes.
  3. Overrides _build_tools() to return the tool subset for that domain.
  4. Optionally overrides _system_prompt() to customise the system message.

BaseAgent handles:
  - Envelope unpacking (AgentRequest → inner query)
  - LangGraph execution (reuses Phase 3 inner assistant↔tools loop)
  - Envelope packing (LangGraph output → AgentResponse)
  - Confidence + risk scoring from the ReflectionNode
  - data_freshness computed from ToolResult timestamps
  - Structured logging + tracing spans
  - Phase H3: per-role LLM routing, per-request PII anonymisation,
    PII pre-flight scan before cloud calls, detokenisation of final answer
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import ToolNode

from sqlalchemy.ext.asyncio import async_sessionmaker

from libs.privacy.anonymiser import default_anonymiser
from libs.privacy.pii_scanner import default_scanner
from libs.privacy.token_map import TokenMap
from libs.schemas.agent_envelope import AgentRequest, AgentResponse, DataTier, RiskLevel
from libs.schemas.user_profile import UserProfile
from libs.telemetry.langfuse_handler import (
    create_trace,
    end_callback_span,
    get_callback_handler,
    score_trace,
)
from libs.telemetry.tracing import start_span
from services.agent.config import LLMConfig, LLMRole, RoutingPolicy
from services.agent.context import compact_messages
from services.agent.grounding import check_answer_grounding
from services.agent.reflection import ReflectionNode

log = structlog.get_logger(__name__)

_MAX_REFLECT = int(os.getenv("MAX_REFLECT_ITERATIONS", "2"))
_REFLECT_THRESHOLD = float(os.getenv("REFLECTION_THRESHOLD", "0.7"))
_RECURSION_LIMIT = int(os.getenv("AGENT_MAX_ITERATIONS", "10"))


class BaseAgent(ABC):
    """
    Abstract domain agent.

    Subclasses must define:
      AGENT_ID: str          — stable snake_case identifier
      CAPABILITIES: list[str]  — capability tags for the registry
    """

    AGENT_ID: str
    CAPABILITIES: list[str]

    def __init__(self, session_factory: async_sessionmaker, config: LLMConfig | None = None) -> None:
        self._session_factory = session_factory

        if config is not None:
            # Legacy / test path: single LLM for all roles
            llm = config.build_chat_model()
            self._executor_llm = llm
            self._reflector_llm = llm
            self._compactor_llm = llm
            self._reflector_is_cloud = False
        else:
            executor_policy = RoutingPolicy.from_env(LLMRole.EXECUTOR)
            reflector_policy = RoutingPolicy.from_env(LLMRole.REFLECTOR)
            compactor_policy = RoutingPolicy.from_env(LLMRole.COMPACTOR)

            self._executor_llm = executor_policy.build_chat_model()
            self._reflector_llm = reflector_policy.build_chat_model()
            self._compactor_llm = compactor_policy.build_chat_model()
            self._reflector_is_cloud = reflector_policy.destination == "cloud"

        # Backward-compat alias used by tests and tool helpers
        self._llm = self._executor_llm

        self._reflector = ReflectionNode(llm=self._reflector_llm)
        # Local fallback reflector — used when cloud PII scan raises
        self._local_reflector = ReflectionNode(llm=self._executor_llm)

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    @abstractmethod
    def _build_tools(self, owner_id: str) -> list:
        """Return LangChain-compatible tools for this agent's domain.

        owner_id must be bound server-side in each tool's closure so the LLM
        cannot substitute a different owner's UUID via prompt injection.
        """

    def _make_tool_bound(self, fn, owner_id: str) -> Any:
        """Return an async callable that opens a fresh session and enforces owner_id.

        - Fresh session per call prevents concurrent SQLAlchemy state corruption.
        - owner_id is supplied by the server; any value the LLM passes is discarded.
        """
        sf = self._session_factory

        async def _bound(**kwargs):
            kwargs.pop("owner_id", None)  # discard any LLM-supplied value
            async with sf() as session:
                return (await fn(session=session, owner_id=owner_id, **kwargs)).to_llm_str()

        return _bound

    def _system_prompt(self, user_profile: UserProfile) -> str:
        """Override to inject domain-specific instructions."""
        return (
            f"You are Artha, a personal finance assistant for {user_profile.name}. "
            f"You specialise in {', '.join(self.CAPABILITIES)} analysis. "
            "Use tools to retrieve real data — never guess amounts.\n\n"
            f"User profile: owner_id={user_profile.owner_id} "
            f"income={user_profile.total_monthly_income_paise}p/mo "
            f"risk={user_profile.risk_appetite}\n\n"
            "Response rules:\n"
            "- Default date range: current calendar month unless the user specifies otherwise.\n"
            "- For optional parameters (start_date, end_date, category, account_id, etc.): "
            "only include them if the user specifically requested that filter; otherwise omit them.\n"
            "- Always use the arithmetic tools (convert_amount, calculate_percentage, "
            "calculate_growth, calculate_compound_interest) — never compute amounts inline.\n"
            "- Express amounts in Indian Rupee format (₹X,XX,XXX.XX).\n"
            "- Reference fiscal year (April–March) for annual figures.\n"
            "- If a tool returns no data, explain why and suggest ingesting the relevant document.\n"
            "- Cite data_freshness when the user asks about current balances.\n"
            "- Never reveal raw paise values unless explicitly asked.\n"
            "- Keep answers concise and actionable; lead with the direct answer, then context."
        )

    # ------------------------------------------------------------------
    # Public interface — called by the FastAPI handler
    # ------------------------------------------------------------------

    async def run(self, request: AgentRequest) -> AgentResponse:
        """Execute the agent for *request* and return an envelope response."""
        tm = TokenMap()  # per-request token map — GC'd after this method returns

        # Ensure a top-level Langfuse trace exists for this trace_id when the
        # agent is called directly (i.e. not via the orchestrator, which normally
        # creates the trace first). Langfuse dedupes on id so this is safe.
        create_trace(
            trace_id=str(request.trace_id),
            name=f"{self.AGENT_ID}.run",
            user_id=str(request.user_profile.owner_id),
            input={"query": request.query[:120]},
            metadata={"agent_id": self.AGENT_ID},
        )

        with start_span(f"{self.AGENT_ID}.run", {"trace_id": str(request.trace_id)}):
            log.info(
                "agent.run.start",
                agent_id=self.AGENT_ID,
                trace_id=str(request.trace_id),
                query=request.query[:120],
            )
            result, confidence, risk_level, reasoning, warnings, tool_freshness, tools_used = (
                await self._execute(request, tm)
            )

            # Detokenise final answer if reflector was cloud (tokens may appear in output)
            if self._reflector_is_cloud and result.get("answer"):
                result = {**result, "answer": default_anonymiser.detokenise_answer(result["answer"], tm)}

            data_freshness_hours = _compute_freshness_hours(tool_freshness)

            response = AgentResponse(
                agent_id=self.AGENT_ID,
                schema_version="1.0",
                trace_id=request.trace_id,
                data_tier=_tier_from_freshness(data_freshness_hours),
                data_freshness_hours=data_freshness_hours,
                result=result,
                confidence=confidence,
                risk_level=risk_level,
                reasoning=reasoning,
                warnings=warnings,
                tools_used=tools_used,
            )
            log.info(
                "agent.run.complete",
                agent_id=self.AGENT_ID,
                trace_id=str(request.trace_id),
                confidence=confidence,
                risk_level=risk_level,
                reflector_cloud=self._reflector_is_cloud,
            )
            return response

    # ------------------------------------------------------------------
    # Internal execution — executor → reflect loop
    # ------------------------------------------------------------------

    async def _execute(
        self, request: AgentRequest, tm: TokenMap
    ) -> tuple[dict[str, Any], float, RiskLevel, str, list[str], list[datetime], list[str]]:
        owner_id = str(request.user_profile.owner_id)
        graph = self._build_graph(owner_id)
        system_msg = SystemMessage(content=self._system_prompt(request.user_profile))
        human_msg = HumanMessage(content=request.query)

        messages = [system_msg, human_msg]

        best_result: dict[str, Any] = {}
        best_confidence: float = 0.0
        best_reasoning: str = ""
        all_warnings: list[str] = []
        tool_freshness: list[datetime] = []
        all_tools_used: list[str] = []
        all_tool_outputs: list[str] = []  # raw tool result strings for grounding check

        _lf_meta = {"agent_id": self.AGENT_ID, "query_preview": request.query[:80]}
        _lf_kwargs = dict(
            trace_id=str(request.trace_id),
            user_id=str(request.user_profile.owner_id),
            metadata=_lf_meta,
        )
        compactor_handler = get_callback_handler(**_lf_kwargs, node_name="compactor")
        compactor_callbacks = [compactor_handler] if compactor_handler is not None else []

        # Per-iteration handlers are created inside the loop so each iteration's
        # iteration number appears in the span metadata.
        prev_confidence: float | None = None

        for iteration in range(_MAX_REFLECT + 1):
            # Skip compactor LLM call entirely when the message list is short —
            # avoids a wasted ainvoke and an empty Langfuse span.
            from services.agent.context import CONTEXT_WINDOW_THRESHOLD  # noqa: PLC0415
            if len(messages) > CONTEXT_WINDOW_THRESHOLD:
                messages, _ = await compact_messages(messages, self._compactor_llm)

            iter_meta = {**_lf_meta, "iteration": iteration}
            executor_handler = get_callback_handler(
                trace_id=str(request.trace_id),
                user_id=str(request.user_profile.owner_id),
                metadata=iter_meta,
                node_name=f"executor#iter{iteration}",
            )
            reflector_handler = get_callback_handler(
                trace_id=str(request.trace_id),
                user_id=str(request.user_profile.owner_id),
                metadata=iter_meta,
                node_name=f"reflector#iter{iteration}",
            )
            executor_callbacks = [executor_handler] if executor_handler is not None else []
            reflector_callbacks = [reflector_handler] if reflector_handler is not None else []

            graph_state = await graph.ainvoke(
                {"messages": messages},
                config={"recursion_limit": _RECURSION_LIMIT, "callbacks": executor_callbacks},
            )

            final_messages = graph_state["messages"]
            last_ai: AIMessage | None = next(
                (m for m in reversed(final_messages) if isinstance(m, AIMessage)), None
            )
            raw_answer = _THINK_RE.sub("", last_ai.content if last_ai else "").strip()

            tool_freshness.extend(_extract_freshness(final_messages))
            all_tools_used.extend(_extract_tool_names(final_messages))
            all_tool_outputs.extend(_extract_tool_outputs(final_messages))

            # Choose reflector and messages — scrub PII if cloud
            reflector, reflect_messages = self._prepare_reflection(final_messages, tm)

            reflection_state = await reflector.acall(
                {
                    "messages": reflect_messages,
                    "reflect_count": iteration,
                },
                callbacks=reflector_callbacks,
            )
            confidence = reflection_state["confidence_score"]
            notes = reflection_state.get("reflection_notes", "")

            # Cloud reflector saw anonymised messages — its notes may contain tokens.
            # Detokenise before storing as reasoning or injecting into executor context.
            if self._reflector_is_cloud and notes:
                notes = default_anonymiser.detokenise_answer(notes, tm)

            if confidence >= best_confidence:
                best_confidence = confidence
                best_reasoning = notes
                best_result = {"answer": raw_answer}

            # Close per-iteration spans with their output so results are visible
            # in Langfuse without drilling into child generations.
            end_callback_span(executor_handler, output={"answer": raw_answer[:500]})
            end_callback_span(reflector_handler, output={"confidence": confidence, "notes": notes[:200]})

            if confidence >= _REFLECT_THRESHOLD:
                break

            # Early-exit when confidence is decreasing — further reflection
            # is unlikely to help and only burns tokens.
            if prev_confidence is not None and confidence < prev_confidence:
                log.info(
                    "agent.reflect.early_exit",
                    agent_id=self.AGENT_ID,
                    iteration=iteration,
                    prev_confidence=prev_confidence,
                    confidence=confidence,
                )
                break

            prev_confidence = confidence

            if iteration < _MAX_REFLECT:
                log.info(
                    "agent.reflect.rerun",
                    agent_id=self.AGENT_ID,
                    iteration=iteration + 1,
                    confidence=confidence,
                )
                messages = final_messages + [
                    HumanMessage(
                        content=(
                            f"Your answer had confidence {confidence:.2f}. "
                            f"Issues: {notes or 'none'}. "
                            "Please refine your analysis."
                        )
                    )
                ]

        end_callback_span(compactor_handler)

        # Numeric grounding check — cap confidence if answer cites ₹ figures
        # that cannot be traced to any tool output (possible hallucination).
        answer_text = best_result.get("answer", "")
        is_grounded, ungrounded = check_answer_grounding(answer_text, all_tool_outputs)
        if not is_grounded:
            ungrounded_rupees = [f"₹{p / 100:,.0f}" for p in ungrounded]
            warning = (
                f"Answer may contain unverified amounts: {', '.join(ungrounded_rupees)}. "
                "Please verify against your source documents."
            )
            all_warnings.append(warning)
            best_confidence = min(best_confidence, 0.5)
            log.warning(
                "agent.grounding.unverified",
                agent_id=self.AGENT_ID,
                ungrounded=ungrounded_rupees,
            )

        # Attach confidence as a scored metric on the Langfuse trace so runs can
        # be filtered/sliced by agent confidence in the dashboard.
        score_trace(str(request.trace_id), name=f"{self.AGENT_ID}.confidence", value=best_confidence)

        risk_level = _risk_from_confidence(best_confidence)
        # Flush is intentionally omitted here — the orchestrator calls flush()
        # once after all agents complete, avoiding a blocking sync call per agent.
        tools_used = list(dict.fromkeys(all_tools_used))  # deduplicate, preserve order
        return best_result, best_confidence, risk_level, best_reasoning, all_warnings, tool_freshness, tools_used

    def _prepare_reflection(
        self, messages: list, tm: TokenMap
    ) -> tuple[ReflectionNode, list]:
        """
        Return (reflector, messages_to_use).

        If reflector is cloud:
          1. Scrub messages with anonymiser.
          2. Run PII pre-flight scan on scrubbed text.
          3. If scan passes → use cloud reflector + scrubbed messages.
          4. If scan raises → fall back to local reflector + original messages.
        """
        if not self._reflector_is_cloud:
            return self._reflector, messages

        scrubbed = default_anonymiser.scrub_messages(messages, tm)

        # Scan only what actually reaches the cloud LLM.
        # ReflectionNode._evaluate sends: question (first non-profile HumanMessage)
        # + draft_answer (last AIMessage string content). Everything else (tool
        # results, intermediate AI tool-call messages) never leaves the container.
        from langchain_core.messages import AIMessage as _AIMessage, HumanMessage as _HMSG
        _cloud_question = ""
        _cloud_draft = ""
        for m in scrubbed:
            if isinstance(m, _HMSG) and not _cloud_question:
                q = m.content if isinstance(m.content, str) else ""
                if q.startswith("[User profile]") or q.startswith("[owner_id="):
                    continue
                _cloud_question = q
            if isinstance(m, _AIMessage) and isinstance(m.content, str) and m.content:
                _cloud_draft = m.content  # last AI string content = draft answer

        scan_text = f"{_cloud_question} {_cloud_draft}"
        try:
            default_scanner.assert_safe_for_cloud(
                scan_text, context=f"{self.AGENT_ID}.reflector"
            )
            log.debug("agent.reflector.cloud", agent_id=self.AGENT_ID)
            return self._reflector, scrubbed
        except ValueError as exc:
            log.warning(
                "agent.reflector.pii_fallback",
                agent_id=self.AGENT_ID,
                error=str(exc),
            )
            return self._local_reflector, messages

    # ------------------------------------------------------------------
    # Graph construction (inner assistant↔tools loop)
    # ------------------------------------------------------------------

    def _build_graph(self, owner_id: str):
        tools = self._build_tools(owner_id)
        llm_with_tools = self._executor_llm.bind_tools(tools)
        tool_node = ToolNode(tools)

        def assistant(state: MessagesState) -> dict:
            response = llm_with_tools.invoke(state["messages"])
            return {"messages": [response]}

        def should_continue(state: MessagesState) -> str:
            last = state["messages"][-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                return "tools"
            return END

        g = StateGraph(MessagesState)
        g.add_node("assistant", assistant)
        g.add_node("tools", tool_node)
        g.add_edge(START, "assistant")
        g.add_conditional_edges("assistant", should_continue, {"tools": "tools", END: END})
        g.add_edge("tools", "assistant")
        return g.compile()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_tool_outputs(messages: list) -> list[str]:
    """Collect string content from ToolMessages for grounding checks."""
    from langchain_core.messages import ToolMessage
    return [
        msg.content
        for msg in messages
        if isinstance(msg, ToolMessage) and isinstance(msg.content, str)
    ]


def _extract_tool_names(messages: list) -> list[str]:
    """Collect tool names from AIMessage tool_calls in the message list."""
    names: list[str] = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if name:
                    names.append(name)
    return names


def _extract_freshness(messages: list) -> list[datetime]:
    """Pull data_freshness timestamps from ToolMessage content (JSON)."""
    import json

    freshness: list[datetime] = []
    for msg in messages:
        if hasattr(msg, "content") and isinstance(msg.content, str):
            try:
                data = json.loads(msg.content)
                if "data_freshness" in data:
                    freshness.append(datetime.fromisoformat(data["data_freshness"]))
            except (json.JSONDecodeError, ValueError):
                pass
    return freshness


def _compute_freshness_hours(timestamps: list[datetime]) -> float:
    """Return age in hours of the oldest tool result. 0.0 if no tool was called."""
    if not timestamps:
        return 0.0
    now = datetime.now(timezone.utc)
    oldest = min(timestamps)
    delta = now - oldest.replace(tzinfo=timezone.utc) if oldest.tzinfo is None else now - oldest
    return max(0.0, delta.total_seconds() / 3600)


def _tier_from_freshness(hours: float) -> DataTier:
    from libs.schemas.agent_envelope import DataTier
    if hours < (1 / 60):
        return DataTier.REALTIME
    if hours < 1.0:
        return DataTier.CACHED
    if hours < 24.0:
        return DataTier.STALE
    return DataTier.ESTIMATED


def _risk_from_confidence(confidence: float) -> RiskLevel:
    if confidence >= 0.85:
        return RiskLevel.LOW
    if confidence >= 0.65:
        return RiskLevel.MEDIUM
    if confidence >= 0.40:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL
