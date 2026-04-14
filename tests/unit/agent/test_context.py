"""
Unit tests for services/agent/context.py — message compaction.

No LLM API calls or Docker required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from services.agent.context import (
    CONTEXT_WINDOW_KEEP,
    CONTEXT_WINDOW_THRESHOLD,
    compact_messages,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_llm(summary_text: str = "Prior discussion about grocery spending.") -> MagicMock:
    mock = MagicMock()
    response = MagicMock()
    response.content = summary_text
    mock.ainvoke = AsyncMock(return_value=response)
    return mock


def _msgs(n: int) -> list:
    """Build a list of n alternating HumanMessage / AIMessage."""
    result = []
    for i in range(n):
        if i % 2 == 0:
            result.append(HumanMessage(content=f"Question {i}"))
        else:
            result.append(AIMessage(content=f"Answer {i}"))
    return result


# ── compact_messages ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_compaction_below_threshold():
    msgs = _msgs(CONTEXT_WINDOW_THRESHOLD - 1)
    llm = _make_llm()

    compacted, summary = await compact_messages(msgs, llm)

    assert compacted is msgs  # unchanged list
    assert summary is None
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_no_compaction_at_exact_threshold():
    msgs = _msgs(CONTEXT_WINDOW_THRESHOLD)
    llm = _make_llm()

    compacted, summary = await compact_messages(msgs, llm)

    assert compacted is msgs
    assert summary is None


@pytest.mark.asyncio
async def test_compaction_triggered_above_threshold():
    msgs = _msgs(CONTEXT_WINDOW_THRESHOLD + 5)
    llm = _make_llm("Summary of earlier turns.")

    compacted, summary = await compact_messages(msgs, llm)

    assert summary == "Summary of earlier turns."
    assert len(compacted) == CONTEXT_WINDOW_KEEP + 1  # summary SystemMessage + kept messages


@pytest.mark.asyncio
async def test_compacted_list_starts_with_system_message():
    msgs = _msgs(CONTEXT_WINDOW_THRESHOLD + 2)
    llm = _make_llm("A summary.")

    compacted, _ = await compact_messages(msgs, llm)

    assert isinstance(compacted[0], SystemMessage)
    assert "Prior conversation summary" in compacted[0].content
    assert "A summary." in compacted[0].content


@pytest.mark.asyncio
async def test_compacted_list_ends_with_recent_messages():
    msgs = _msgs(CONTEXT_WINDOW_THRESHOLD + 4)
    llm = _make_llm("Summary.")

    compacted, _ = await compact_messages(msgs, llm)

    # The last CONTEXT_WINDOW_KEEP messages from original should be at the end
    recent_original = msgs[-CONTEXT_WINDOW_KEEP:]
    recent_compacted = compacted[1:]  # skip the summary SystemMessage
    assert len(recent_compacted) == len(recent_original)
    for orig, comp in zip(recent_original, recent_compacted):
        assert orig.content == comp.content


@pytest.mark.asyncio
async def test_existing_summary_passed_to_llm():
    msgs = _msgs(CONTEXT_WINDOW_THRESHOLD + 2)
    llm = _make_llm("New combined summary.")
    prior = "Old summary text."

    _, new_summary = await compact_messages(msgs, llm, existing_summary=prior)

    assert new_summary == "New combined summary."
    # Verify old summary was included in the LLM prompt
    prompt_messages = llm.ainvoke.call_args[0][0]
    human_prompt = next(m for m in prompt_messages if isinstance(m, HumanMessage))
    assert "Old summary text." in human_prompt.content


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_text_concat():
    msgs = _msgs(CONTEXT_WINDOW_THRESHOLD + 2)
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM timeout"))

    compacted, summary = await compact_messages(msgs, llm)

    # Should not raise; fallback summary is a truncated text
    assert isinstance(summary, str)
    assert len(compacted) == CONTEXT_WINDOW_KEEP + 1
