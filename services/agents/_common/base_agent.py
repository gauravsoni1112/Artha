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
"""

from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import ToolNode
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.agent_envelope import AgentRequest, AgentResponse, DataTier, RiskLevel
from libs.schemas.user_profile import UserProfile
from libs.telemetry.tracing import start_span
from services.agent.config import LLMConfig
from services.agent.context import compact_messages
from services.agent.planner import PlannerNode
from services.agent.reflection import ReflectionNode
from services.agents._common.agent_config import agent_llm_config

log = structlog.get_logger(__name__)

# How many reflection iterations before we give up and return best effort
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

    def __init__(self, session: AsyncSession, config: LLMConfig | None = None) -> None:
        self._session = session
        self._config = config or agent_llm_config(self.AGENT_ID)
        self._llm = self._config.build_chat_model()
        self._planner = PlannerNode(llm=self._llm)
        self._reflector = ReflectionNode(llm=self._llm)
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    @abstractmethod
    def _build_tools(self) -> list:
        """Return LangChain-compatible tools for this agent's domain."""

    def _system_prompt(self, user_profile: UserProfile) -> str:
        """Override to inject domain-specific instructions."""
        return (
            f"You are Artha, a personal finance assistant for {user_profile.name}. "
            f"You specialise in {', '.join(self.CAPABILITIES)} analysis. "
            "Use tools to retrieve real data — never guess amounts. "
            "Express amounts in Indian Rupee format (₹X,XX,XXX.XX). "
            "Reference fiscal year (April–March) for annual figures. "
            "Never reveal raw paise values unless explicitly asked."
        )

    # ------------------------------------------------------------------
    # Public interface — called by the FastAPI handler
    # ------------------------------------------------------------------

    async def run(self, request: AgentRequest) -> AgentResponse:
        """Execute the agent for *request* and return an envelope response."""
        with start_span(f"{self.AGENT_ID}.run", {"trace_id": str(request.trace_id)}):
            log.info(
                "agent.run.start",
                agent_id=self.AGENT_ID,
                trace_id=str(request.trace_id),
                query=request.query[:120],
            )
            result, confidence, risk_level, reasoning, warnings, tool_freshness = (
                await self._execute(request)
            )

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
            )
            log.info(
                "agent.run.complete",
                agent_id=self.AGENT_ID,
                trace_id=str(request.trace_id),
                confidence=confidence,
                risk_level=risk_level,
            )
            return response

    # ------------------------------------------------------------------
    # Internal execution — planner → executor → reflect loop
    # ------------------------------------------------------------------

    async def _execute(
        self, request: AgentRequest
    ) -> tuple[dict[str, Any], float, RiskLevel, str, list[str], list[datetime]]:
        system_msg = SystemMessage(content=self._system_prompt(request.user_profile))
        human_msg = HumanMessage(content=request.query)

        # Inject profile context so tools don't need to query it themselves
        profile_context = HumanMessage(
            content=(
                f"[User profile] owner_id={request.user_profile.owner_id} "
                f"income={request.user_profile.total_monthly_income_paise}p/mo "
                f"risk={request.user_profile.risk_appetite}"
            )
        )

        messages = [system_msg, profile_context, human_msg]

        best_result: dict[str, Any] = {}
        best_confidence: float = 0.0
        best_reasoning: str = ""
        all_warnings: list[str] = []
        tool_freshness: list[datetime] = []

        for iteration in range(_MAX_REFLECT + 1):
            messages, _ = await compact_messages(messages, self._llm)

            graph_state = await self._graph.ainvoke(
                {"messages": messages},
                config={"recursion_limit": _RECURSION_LIMIT},
            )

            final_messages = graph_state["messages"]
            last_ai: AIMessage | None = next(
                (m for m in reversed(final_messages) if isinstance(m, AIMessage)), None
            )
            raw_answer = last_ai.content if last_ai else ""

            # Collect tool freshness timestamps from ToolResults embedded in messages
            tool_freshness.extend(_extract_freshness(final_messages))

            # Reflect — acall takes a state dict, returns a state dict
            reflection_state = await self._reflector.acall({
                "messages": final_messages,
                "reflect_count": iteration,
            })
            confidence = reflection_state["confidence_score"]
            notes = reflection_state.get("reflection_notes", "")

            if confidence >= best_confidence:
                best_confidence = confidence
                best_reasoning = notes
                best_result = {"answer": raw_answer}

            if confidence >= _REFLECT_THRESHOLD:
                break

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

        risk_level = _risk_from_confidence(best_confidence)
        return best_result, best_confidence, risk_level, best_reasoning, all_warnings, tool_freshness

    # ------------------------------------------------------------------
    # Graph construction (inner assistant↔tools loop)
    # ------------------------------------------------------------------

    def _build_graph(self):
        tools = self._build_tools()
        llm_with_tools = self._llm.bind_tools(tools)
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
    if hours < (1 / 60):   # < 1 minute
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
