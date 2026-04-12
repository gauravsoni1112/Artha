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

import uuid
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import ToolNode
from sqlalchemy.ext.asyncio import AsyncSession

from services.agent.config import LLMConfig
from services.agent.tools.registry import build_langchain_tools

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

        return graph.compile()

    async def chat(self, owner_id: str, message: str) -> dict[str, Any]:
        """
        Run a single user message through the agent graph.

        Returns:
            {
                "response": str,          # final LLM answer
                "tool_calls": list[str],  # names of tools invoked
                "messages": list,         # full message trace (for debugging)
            }
        """
        # Inject owner_id into the message so tools can use it without exposing
        # it to the LLM as a separate field.
        augmented = f"[owner_id={owner_id}] {message}"
        initial_state = {"messages": [HumanMessage(content=augmented)]}

        result = await self._graph.ainvoke(initial_state)

        messages = result["messages"]
        final_msg = messages[-1]
        response_text = final_msg.content if hasattr(final_msg, "content") else str(final_msg)

        tool_calls = [
            m.tool_calls[0]["name"]
            for m in messages
            if hasattr(m, "tool_calls") and m.tool_calls
        ]

        return {
            "response": response_text,
            "tool_calls": tool_calls,
            "messages": [m.model_dump() if hasattr(m, "model_dump") else str(m) for m in messages],
        }
