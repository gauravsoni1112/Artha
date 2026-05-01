"""
Phase 3 — Multi-Step Reasoning Agent (LangGraph).

Graph topology:

  START → planner → executor_loop → END

- planner: decomposes the user question into an ordered Plan (list of steps).
- executor_loop: iterates over plan steps, running the assistant↔tools
  sub-graph per step, collecting observations, then synthesises a final answer.

The assistant↔tools inner loop is unchanged from Phase 2:
  assistant → [tool_node] → assistant → (repeat until no tool calls)

State schema: PlanState (extends MessagesState with plan + step observations).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import ToolNode
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing_extensions import TypedDict

from libs.schemas.db_models import AgentRun, ChatSession
from libs.telemetry.tracing import start_span
from services.agent.config import LLMConfig
from services.agent.context import compact_messages
from services.agent.planner import Plan, PlannerNode
from services.agent.reflection import ReflectionNode
from services.agent.tools.registry import build_langchain_tools

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are Artha, a personal finance advisor for Indian users. You are warm,
precise, and always cite real data from tools — never guess amounts.

## Tool Selection Guide

**Step 1 — Account Discovery (always call first for account-specific queries)**
- fetch_accounts: List all accounts (bank, credit card, investment). Call this
  before transaction_query if the user mentions a specific account by name.

**Step 2 — Spending & Transactions**
- transaction_query: Fetch individual transactions. Use for listing recent
  transactions or when the user asks for specific entries.
- category_analysis: Aggregate spending by category. Prefer over transaction_query
  when the user asks "how much did I spend on X" or wants a breakdown.
- spending_trend: Month-by-month trend for one or all categories. Use when the
  user asks "is my spending going up?" or wants a trend/comparison.
- budget_comparison: Actual vs budget. Use when the user asks about budgets.
- upcoming_expenses: Predicted recurring bills. Use for "what bills are coming?".

**Step 3 — Wealth & Portfolio**
- net_worth: Total assets minus liabilities. Use for "what is my net worth?".
- portfolio_value: Investment portfolio by asset class. Use for mutual funds,
  equities, etc.
- tax_summary: Capital gains and taxable events. Use for "what are my taxes?".

**Step 4 — Planning & Risk**
- goal_progress: Progress toward savings goals. Use when user asks about goals.
- emergency_fund_months: How many months of expenses are covered. Use for
  "do I have an emergency fund?" queries.
- asset_concentration: Portfolio concentration risk. Use for diversification
  questions.
- debt_to_income: DTI ratio from transaction history. Use for "how much debt
  do I have?" queries.
- insurance_coverage_gap: Estimated coverage shortfall. Use for insurance queries.

**Step 5 — Arithmetic (mandatory — never compute inline)**
- convert_amount: Convert between paise/rupee/lakh/crore.
- calculate_percentage: Compute a percentage of an amount.
- calculate_growth: Growth rate between two amounts.
- calculate_compound_interest: Compound interest / future value.

## Response Rules
- Default date range: current calendar month unless the user specifies otherwise.
- Always use the arithmetic tools (convert_amount, calculate_percentage,
  calculate_growth, calculate_compound_interest) — never compute amounts inline.
- Express amounts as ₹X,XX,XXX.XX (Indian format). Never show raw paise unless asked.
- Reference fiscal year (April–March) for annual figures.
- If a tool returns no data, explain why and suggest ingesting the relevant document.
- Cite data_freshness timestamp when the user asks about current balances.
- Keep answers concise and actionable; lead with the direct answer, then context.
"""


class ArthaAgent:
    """
    Compiled LangGraph agent for one owner's session.

    Usage:
        agent = ArthaAgent(session=db_session)
        response = await agent.chat(owner_id="...", message="What did I spend on groceries last month?")
    """

    def __init__(
        self,
        session_factory: async_sessionmaker | None = None,
        config: LLMConfig | None = None,
        *,
        session: AsyncSession | None = None,
    ) -> None:
        if session_factory is not None:
            self._session_factory = session_factory
        elif session is not None:
            # Legacy path — wrap a single session so async-with callers work.
            # Only safe for sequential DB access (integration tests / single-turn use).
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _wrap():
                yield session

            self._session_factory = _wrap
        else:
            raise ValueError("Either session_factory or session must be provided")

        self._config = config or LLMConfig.from_env()

    def _build_graph(self, owner_id: str):
        tools = build_langchain_tools(self._session_factory, owner_id)
        llm = self._config.build_chat_model()
        llm_with_tools = llm.bind_tools(tools)
        tool_node = ToolNode(tools)
        self._recursion_limit = int(os.getenv("AGENT_MAX_ITERATIONS", "10"))
        self._planner = PlannerNode(llm=llm)
        self._reflector = ReflectionNode(llm=llm)

        # ── inner assistant↔tools loop (unchanged from Phase 2) ──────────
        def assistant(state: MessagesState) -> dict:
            messages = state["messages"]
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=_SYSTEM_PROMPT)] + messages
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}

        def should_continue(state: MessagesState) -> str:
            last = state["messages"][-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                return "tools"
            return END

        inner = StateGraph(MessagesState)
        inner.add_node("assistant", assistant)
        inner.add_node("tools", tool_node)
        inner.add_edge(START, "assistant")
        inner.add_conditional_edges("assistant", should_continue, {"tools": "tools", END: END})
        inner.add_edge("tools", "assistant")
        inner_graph = inner.compile()

        # ── PlanState — outer graph state ─────────────────────────────────
        class PlanState(TypedDict):
            messages: list
            plan: Plan | None
            step_observations: list[str]   # one entry per executed plan step
            confidence_score: float | None
            reflection_notes: str | None
            needs_rerun: bool
            reflect_count: int

        # ── planner node ──────────────────────────────────────────────────
        async def planner_node(state: PlanState) -> dict:
            result = await self._planner.acall(state)
            return {"plan": result["plan"], "step_observations": []}

        # ── executor_loop node ────────────────────────────────────────────
        async def executor_loop(state: PlanState) -> dict:
            plan: Plan = state["plan"]
            original_messages = state["messages"]
            observations: list[str] = list(state.get("step_observations") or [])

            # Execute each plan step through the inner assistant↔tools loop
            for step in plan.steps:
                step_state = {"messages": [HumanMessage(content=step)]}
                step_result = await inner_graph.ainvoke(
                    step_state,
                    config={"recursion_limit": self._recursion_limit},
                )
                last = step_result["messages"][-1]
                obs = last.content if hasattr(last, "content") else str(last)
                observations.append(f"[Step: {step}]\n{obs}")
                log.debug("executor_loop.step_done", step=step, obs_len=len(obs))

            # If multi-step, synthesise a final answer from all observations
            if len(plan.steps) > 1:
                synthesis_prompt = (
                    "Based on the following step-by-step observations, "
                    "provide a concise final answer to the original question.\n\n"
                    + "\n\n".join(observations)
                    + f"\n\nOriginal question: {original_messages[-1].content if original_messages else ''}"
                )
                synth_state = {"messages": [HumanMessage(content=synthesis_prompt)]}
                synth_result = await inner_graph.ainvoke(
                    synth_state,
                    config={"recursion_limit": self._recursion_limit},
                )
                final_messages = list(original_messages) + synth_result["messages"]
            else:
                # Single step — use inner graph messages directly
                final_messages = list(original_messages) + step_result["messages"]  # type: ignore[possibly-undefined]

            return {"messages": final_messages, "step_observations": observations}

        # ── reflection node ───────────────────────────────────────────────
        async def reflect_node(state: PlanState) -> dict:
            return await self._reflector.acall(state)

        def after_reflect(state) -> str:
            """Route back to executor if low confidence and iterations remain."""
            if state.get("needs_rerun"):
                return "executor_loop"
            return END

        # ── outer graph ───────────────────────────────────────────────────
        graph = StateGraph(PlanState)
        graph.add_node("planner", planner_node)
        graph.add_node("executor_loop", executor_loop)
        graph.add_node("reflect", reflect_node)
        graph.add_edge(START, "planner")
        graph.add_edge("planner", "executor_loop")
        graph.add_edge("executor_loop", "reflect")
        graph.add_conditional_edges("reflect", after_reflect, {"executor_loop": "executor_loop", END: END})

        return graph.compile()

    async def chat(self, owner_id: str, message: str, session_id: str | None = None) -> dict[str, Any]:
        """
        Run a single user message through the agent graph.

        Args:
            owner_id: UUID string of the owner
            message: Natural language question
            session_id: Optional UUID string for continuing a conversation

        Returns:
            {
                "response": str,               # final LLM answer
                "tool_calls": list[str],       # names of tools invoked
                "messages": list,              # full message trace (for debugging)
                "session_id": str,             # UUID of the session
                "run_id": str,                 # UUID of this agent run
                "plan": Plan | None,           # decomposed plan (Phase 3)
                "step_observations": list[str] # per-step answers (Phase 3)
            }
        """
        started_at = datetime.now(timezone.utc)

        with start_span("agent.chat", {"owner_id": owner_id, "session_id": session_id}):
            log.info("agent.graph.start", owner_id=owner_id, session_id=session_id)

            graph = self._build_graph(owner_id)

            # Load prior session messages for multi-turn context + compact if needed
            prior_messages, new_summary = await self._load_and_compact_context(
                session_id=session_id,
                llm=self._planner._llm,
            )

            initial_messages = prior_messages + [HumanMessage(content=message)]
            initial_state = {
                "messages": initial_messages,
                "plan": None,
                "step_observations": [],
                "confidence_score": None,
                "reflection_notes": None,
                "needs_rerun": False,
                "reflect_count": 0,
            }

            result = await graph.ainvoke(
                initial_state,
                config={"recursion_limit": self._recursion_limit},
            )

            messages = result["messages"]
            plan: Plan | None = result.get("plan")
            step_observations: list[str] = result.get("step_observations") or []
            confidence_score: float | None = result.get("confidence_score")
            reflection_notes: str | None = result.get("reflection_notes")

            final_msg = messages[-1]
            response_text = final_msg.content if hasattr(final_msg, "content") else str(final_msg)

            tool_calls = [
                tc["name"]
                for m in messages
                if hasattr(m, "tool_calls") and m.tool_calls
                for tc in m.tool_calls
            ]

            messages_trace = [m.model_dump() if hasattr(m, "model_dump") else str(m) for m in messages]
            scratchpad = self._extract_scratchpad(messages)

            log.info(
                "agent.graph.complete",
                owner_id=owner_id,
                tool_calls=tool_calls,
                plan_steps=len(plan.steps) if plan else 1,
                confidence=confidence_score,
                response_len=len(response_text),
            )

        # Persist the conversation turn
        sess_id, run_id = await self._persist_run(
            owner_id=owner_id,
            session_id=session_id,
            user_message=message,
            response_text=response_text,
            tool_calls=tool_calls,
            messages_trace=messages_trace,
            scratchpad=scratchpad,
            confidence_score=confidence_score,
            reflection_notes=reflection_notes,
            context_summary=new_summary,
            started_at=started_at,
        )

        return {
            "response": response_text,
            "tool_calls": tool_calls,
            "messages": messages_trace,
            "scratchpad": scratchpad,
            "session_id": sess_id,
            "run_id": run_id,
            "plan": plan,
            "step_observations": step_observations,
            "confidence_score": confidence_score,
            "reflection_notes": reflection_notes,
        }

    async def _load_and_compact_context(
        self,
        session_id: str | None,
        llm: Any,
    ) -> tuple[list, str | None]:
        """
        Load prior conversation messages from session history and compact if needed.

        For Phase 3, we keep this lightweight: if session_id is provided and the
        session has a stored summary, we inject it as a SystemMessage prefix.
        Full message replay from DB is reserved for a future turn; here we use
        the stored summary as the prior context token.

        Returns:
            (prior_messages, new_summary | None)
        """
        if not session_id:
            return [], None

        try:
            sess_uuid = uuid.UUID(session_id)
            async with self._session_factory() as db:
                chat_session = await db.get(ChatSession, sess_uuid)
            if chat_session is None:
                return [], None

            prior: list = []
            if chat_session.summary:
                prior = [SystemMessage(content=f"[Prior conversation summary]\n{chat_session.summary}")]

            # compact_messages only triggers if we exceed threshold; with just a
            # summary SystemMessage it won't trigger — that's the intended behaviour.
            compacted, new_summary = await compact_messages(prior, llm, chat_session.summary)
            return compacted, new_summary
        except Exception as exc:
            log.warning("agent.context.load_failed", error=str(exc))
            return [], None

    @staticmethod
    def _extract_scratchpad(messages: list) -> list[dict]:
        """
        Parse Thought:/Action:/Observation: blocks from AI message content.

        Returns a list of step dicts, e.g.:
            [{"thought": "I need to query...", "action": "transaction_query", "observation": "..."}]

        Only AI messages (those with a ``content`` str) are scanned.
        Tool messages provide the observation for the preceding action.
        """
        steps: list[dict] = []
        current: dict = {}

        for msg in messages:
            content = getattr(msg, "content", None)
            if not isinstance(content, str):
                continue

            msg_type = type(msg).__name__.lower()  # humanmessage / aimessage / toolmessage

            if "aimessage" in msg_type or "ai" in msg_type:
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.lower().startswith("thought:"):
                        # Start a new step
                        if current:
                            steps.append(current)
                        current = {"thought": stripped[len("thought:"):].strip()}
                    elif stripped.lower().startswith("action:"):
                        current["action"] = stripped[len("action:"):].strip()
                    elif stripped.lower().startswith("observation:"):
                        current["observation"] = stripped[len("observation:"):].strip()
                        steps.append(current)
                        current = {}
                    elif stripped.lower().startswith("final answer:"):
                        current["final_answer"] = stripped[len("final answer:"):].strip()

            elif "toolmessage" in msg_type or "tool" in msg_type:
                # Tool result provides the observation for the last open step
                if current and "observation" not in current:
                    current["observation"] = content[:500]  # cap length
                    steps.append(current)
                    current = {}

        if current:
            steps.append(current)

        return steps

    async def _persist_run(
        self,
        owner_id: str,
        session_id: str | None,
        user_message: str,
        response_text: str,
        tool_calls: list[str],
        messages_trace: list,
        scratchpad: list[dict],
        confidence_score: float | None,
        reflection_notes: str | None,
        context_summary: str | None,
        started_at: datetime,
    ) -> tuple[str, str]:
        """
        Persist this conversation turn to the database.

        Returns:
            (session_id, run_id) as strings
        """
        owner_uuid = uuid.UUID(owner_id)

        async with self._session_factory() as db:
            # Resolve or create session
            if session_id:
                sess_uuid = uuid.UUID(session_id)
                chat_session = await db.get(ChatSession, sess_uuid)
                if chat_session is None:
                    log.error("agent.persist.session_not_found", session_id=session_id)
                    raise ValueError(f"Session {session_id} not found")
                # Count existing turns to set turn_index
                count_stmt = select(sqlfunc.count()).select_from(AgentRun).where(AgentRun.session_id == sess_uuid)
                turn_index = (await db.scalar(count_stmt)) or 0
                # Persist compaction summary if produced this turn
                if context_summary:
                    chat_session.summary = context_summary
            else:
                # Create new session from first message
                chat_session = ChatSession(
                    owner_id=owner_uuid,
                    title=user_message[:80],  # First 80 chars
                    status="ACTIVE",
                )
                db.add(chat_session)
                await db.flush()
                turn_index = 0

            # Create agent run record
            run = AgentRun(
                session_id=chat_session.id,
                owner_id=owner_uuid,
                user_message=user_message,
                assistant_response=response_text,
                tool_calls=tool_calls,
                messages_trace=messages_trace,
                scratchpad=scratchpad or None,
                confidence_score=confidence_score,
                reflection_notes=reflection_notes,
                turn_index=turn_index,
                status="OK",
                error_message=None,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
            db.add(run)
            await db.commit()

        log.info(
            "agent.persist.complete",
            owner_id=owner_id,
            session_id=str(chat_session.id),
            run_id=str(run.id),
        )

        return str(chat_session.id), str(run.id)
