"""
Phase 3 — Context window management (message compaction).

When a conversation exceeds CONTEXT_WINDOW_THRESHOLD messages, earlier turns
are summarised into a single SystemMessage summary so the LLM context stays
manageable without losing conversational history.

Algorithm:
  1. If len(messages) <= threshold → return messages unchanged.
  2. Take all messages except the last CONTEXT_WINDOW_KEEP recent ones.
  3. Ask the LLM to summarise those earlier messages in one paragraph.
  4. Return: [SystemMessage("<prior summary>"), ...last N messages]
  5. Persist the summary text in ChatSession.summary.

The summary is injected at the top so the LLM knows prior context without
re-reading every old message.
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

log = structlog.get_logger(__name__)

# Number of messages that triggers compaction
CONTEXT_WINDOW_THRESHOLD: int = int(os.getenv("CONTEXT_WINDOW_THRESHOLD", "20"))
# How many recent messages to keep verbatim after compaction
CONTEXT_WINDOW_KEEP: int = int(os.getenv("CONTEXT_WINDOW_KEEP", "6"))

_SUMMARISE_SYSTEM = """\
You are summarising a financial assistant conversation for context compression.
Write a concise paragraph (3–6 sentences) capturing the key facts discussed:
which financial data was queried, what amounts were mentioned, and any
decisions or observations the user made.  Do NOT include greetings or filler.
Output only the summary paragraph, nothing else.
"""


async def compact_messages(
    messages: list,
    llm: Any,
    existing_summary: str | None = None,
) -> tuple[list, str | None]:
    """
    Compact the message list if it exceeds the threshold.

    Args:
        messages:         Current message list.
        llm:              LangChain-compatible chat model.
        existing_summary: Prior summary stored on ChatSession (if any).

    Returns:
        (compacted_messages, new_summary_text | None)
        new_summary_text is None when no compaction occurred.
    """
    if len(messages) <= CONTEXT_WINDOW_THRESHOLD:
        return messages, None

    keep = CONTEXT_WINDOW_KEEP
    to_summarise = messages[:-keep] if keep else messages
    recent = messages[-keep:] if keep else []

    summary_text = await _summarise(to_summarise, llm, existing_summary)
    log.info(
        "context.compacted",
        original_len=len(messages),
        kept=len(recent),
        summary_len=len(summary_text),
    )

    compacted = [SystemMessage(content=f"[Prior conversation summary]\n{summary_text}")] + recent
    return compacted, summary_text


async def _summarise(messages: list, llm: Any, prior_summary: str | None) -> str:
    """Ask the LLM to produce a paragraph summary of the given messages."""
    # Build a text representation of the messages to summarise
    lines = []
    if prior_summary:
        lines.append(f"Previous summary: {prior_summary}\n")
    for m in messages:
        role = type(m).__name__.replace("Message", "").lower()
        content = getattr(m, "content", str(m))
        if isinstance(content, str):
            lines.append(f"{role}: {content[:300]}")  # cap per-message length

    conversation_text = "\n".join(lines)

    prompt = [
        SystemMessage(content=_SUMMARISE_SYSTEM),
        HumanMessage(content=f"Conversation to summarise:\n\n{conversation_text}"),
    ]

    try:
        response = await llm.ainvoke(prompt)
        return response.content.strip()
    except Exception as exc:
        log.warning("context.summarise_failed", error=str(exc))
        # Fallback: plain text concatenation capped at 500 chars
        return conversation_text[:500]
