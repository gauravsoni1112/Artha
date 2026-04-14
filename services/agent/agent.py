"""
Phase 2 — Single-Agent Assistant (LangGraph).

Graph topology (single node, expandable in Phase 3):

  START → assistant → [tool_node] → assistant → END

The assistant node calls the LLM with bound tools. If the LLM emits a
tool_call, LangGraph routes to ToolNode which executes the tool and
returns the observation back to the assistant. This continues until
the LLM emits a plain text message (no tool calls).

State schema: MessagesState (list of LangChain messages).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import ToolNode
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import AgentRun, ChatSession
from libs.telemetry.tracing import start_span
from services.agent.config import LLMConfig
from services.agent.tools.registry import build_langchain_tools

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are Artha, a personal finance assistant for Indian users.
You have access to the user's financial data via tools. Always:
- Use tools to retrieve real data before answering — never guess amounts.
- Express all amounts in Indian Rupee format (₹X,XX,XXX.XX).
- Reference the fiscal year (April–March) when discussing annual figures.
- If data is unavailable or empty, say so clearly and suggest what to ingest.
- Be concise, factual, and cite the data freshness timestamp when relevant.
- Never reveal raw paise values unless the user explicitly asks.
"""


class ArthaAgent:
    """
    Compiled LangGraph agent for one owner's session.

    Usage:
        agent = ArthaAgent(session=db_session)
        response = await agent.chat(owner_id="...", message="What did I spend on groceries last month?")
    """

    def __init__(self, session: AsyncSession, config: LLMConfig | None = None) -> None:
        self._session = session
        self._config = config or LLMConfig.from_env()
        self._graph = self._build_graph()

    def _build_graph(self):
        tools = build_langchain_tools(self._session)
        llm = self._config.build_chat_model()
        llm_with_tools = llm.bind_tools(tools)

        tool_node = ToolNode(tools)

        def assistant(state: MessagesState) -> dict:
            messages = state["messages"]
            # Prepend system prompt on first call only
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=_SYSTEM_PROMPT)] + messages
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}

        def should_continue(state: MessagesState) -> str:
            last = state["messages"][-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                return "tools"
            return END

        graph = StateGraph(MessagesState)
        graph.add_node("assistant", assistant)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "assistant")
        graph.add_conditional_edges("assistant", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "assistant")

        self._recursion_limit = int(os.getenv("AGENT_MAX_ITERATIONS", "10"))
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
                "response": str,          # final LLM answer
                "tool_calls": list[str],  # names of tools invoked
                "messages": list,         # full message trace (for debugging)
                "session_id": str,        # UUID of the session
                "run_id": str,            # UUID of this agent run
            }
        """
        started_at = datetime.now(timezone.utc)

        with start_span("agent.chat", {"owner_id": owner_id, "session_id": session_id}):
            log.info("agent.graph.start", owner_id=owner_id, session_id=session_id)

            # Inject owner_id into the message so tools can use it without exposing
            # it to the LLM as a separate field.
            augmented = f"[owner_id={owner_id}] {message}"
            initial_state = {"messages": [HumanMessage(content=augmented)]}

            result = await self._graph.ainvoke(
                initial_state,
                config={"recursion_limit": self._recursion_limit},
            )

            messages = result["messages"]
            final_msg = messages[-1]
            response_text = final_msg.content if hasattr(final_msg, "content") else str(final_msg)

            tool_calls = [
                tc["name"]
                for m in messages
                if hasattr(m, "tool_calls") and m.tool_calls
                for tc in m.tool_calls
            ]

            messages_trace = [m.model_dump() if hasattr(m, "model_dump") else str(m) for m in messages]

            log.info(
                "agent.graph.complete",
                owner_id=owner_id,
                tool_calls=tool_calls,
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
            started_at=started_at,
        )

        return {
            "response": response_text,
            "tool_calls": tool_calls,
            "messages": messages_trace,
            "session_id": sess_id,
            "run_id": run_id,
        }

    async def _persist_run(
        self,
        owner_id: str,
        session_id: str | None,
        user_message: str,
        response_text: str,
        tool_calls: list[str],
        messages_trace: list,
        started_at: datetime,
    ) -> tuple[str, str]:
        """
        Persist this conversation turn to the database.

        Returns:
            (session_id, run_id) as strings
        """
        owner_uuid = uuid.UUID(owner_id)

        # Resolve or create session
        if session_id:
            sess_uuid = uuid.UUID(session_id)
            chat_session = await self._session.get(ChatSession, sess_uuid)
            if chat_session is None:
                log.error("agent.persist.session_not_found", session_id=session_id)
                raise ValueError(f"Session {session_id} not found")
            # Count existing turns to set turn_index
            count_stmt = select(sqlfunc.count()).select_from(AgentRun).where(AgentRun.session_id == sess_uuid)
            turn_index = (await self._session.scalar(count_stmt)) or 0
        else:
            # Create new session from first message
            chat_session = ChatSession(
                owner_id=owner_uuid,
                title=user_message[:80],  # First 80 chars
                status="ACTIVE",
            )
            self._session.add(chat_session)
            await self._session.flush()
            turn_index = 0

        # Create agent run record
        run = AgentRun(
            session_id=chat_session.id,
            owner_id=owner_uuid,
            user_message=user_message,
            assistant_response=response_text,
            tool_calls=tool_calls,
            messages_trace=messages_trace,
            turn_index=turn_index,
            status="OK",
            error_message=None,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )
        self._session.add(run)
        await self._session.commit()

        log.info(
            "agent.persist.complete",
            owner_id=owner_id,
            session_id=str(chat_session.id),
            run_id=str(run.id),
        )

        return str(chat_session.id), str(run.id)
