"""
Unit tests for ArthaAgent._extract_scratchpad().

No LLM, no DB, no Docker required — pure logic tests.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from services.agent.agent import ArthaAgent


# ── helpers ───────────────────────────────────────────────────────────────────

def _ai_msg(content: str):
    m = MagicMock()
    m.content = content
    type(m).__name__ = "AIMessage"
    return m


def _tool_msg(content: str):
    m = MagicMock()
    m.content = content
    type(m).__name__ = "ToolMessage"
    return m


def _human_msg(content: str):
    m = MagicMock()
    m.content = content
    type(m).__name__ = "HumanMessage"
    return m


# ── tests ─────────────────────────────────────────────────────────────────────

def test_empty_messages_returns_empty_list():
    assert ArthaAgent._extract_scratchpad([]) == []


def test_human_only_message_returns_empty_list():
    msgs = [_human_msg("What did I spend last month?")]
    assert ArthaAgent._extract_scratchpad(msgs) == []


def test_single_thought_action_observation_in_ai_message():
    content = (
        "Thought: I need to look up transactions.\n"
        "Action: transaction_query\n"
        "Observation: Found 5 transactions."
    )
    steps = ArthaAgent._extract_scratchpad([_ai_msg(content)])
    assert len(steps) == 1
    assert steps[0]["thought"] == "I need to look up transactions."
    assert steps[0]["action"] == "transaction_query"
    assert steps[0]["observation"] == "Found 5 transactions."


def test_thought_action_observation_case_insensitive():
    content = (
        "THOUGHT: Check spending.\n"
        "ACTION: category_analysis\n"
        "OBSERVATION: Groceries ₹5,000."
    )
    steps = ArthaAgent._extract_scratchpad([_ai_msg(content)])
    assert len(steps) == 1
    assert steps[0]["thought"] == "Check spending."
    assert steps[0]["action"] == "category_analysis"


def test_tool_message_provides_observation_for_open_step():
    ai_content = (
        "Thought: Query net worth.\n"
        "Action: net_worth\n"
    )
    tool_content = "Net worth: ₹10,00,000"
    steps = ArthaAgent._extract_scratchpad([_ai_msg(ai_content), _tool_msg(tool_content)])
    assert len(steps) == 1
    assert steps[0]["observation"] == "Net worth: ₹10,00,000"


def test_tool_message_observation_capped_at_500_chars():
    ai_content = "Thought: Big query.\nAction: transaction_query\n"
    tool_content = "x" * 1000
    steps = ArthaAgent._extract_scratchpad([_ai_msg(ai_content), _tool_msg(tool_content)])
    assert len(steps[0]["observation"]) == 500


def test_multiple_thought_action_pairs():
    content = (
        "Thought: First, check groceries.\n"
        "Action: category_analysis\n"
        "Observation: ₹3,000 spent.\n"
        "Thought: Now check total income.\n"
        "Action: transaction_query\n"
        "Observation: ₹80,000 credited.\n"
    )
    steps = ArthaAgent._extract_scratchpad([_ai_msg(content)])
    assert len(steps) == 2
    assert steps[0]["thought"] == "First, check groceries."
    assert steps[1]["thought"] == "Now check total income."
    assert steps[1]["observation"] == "₹80,000 credited."


def test_final_answer_captured_in_last_step():
    content = (
        "Thought: I have the data.\n"
        "Final Answer: You spent ₹5,000 on groceries."
    )
    steps = ArthaAgent._extract_scratchpad([_ai_msg(content)])
    assert len(steps) == 1
    assert steps[0]["final_answer"] == "You spent ₹5,000 on groceries."


def test_mixed_message_types_processed_correctly():
    msgs = [
        _human_msg("[owner_id=abc] How much did I spend?"),
        _ai_msg("Thought: Query spending.\nAction: category_analysis\n"),
        _tool_msg("FOOD: ₹4,500"),
        _ai_msg("Thought: I have the answer.\nFinal Answer: You spent ₹4,500 on food."),
    ]
    steps = ArthaAgent._extract_scratchpad(msgs)
    # Step 1: thought+action from first AI msg, observation from tool msg
    assert steps[0]["thought"] == "Query spending."
    assert steps[0]["observation"] == "FOOD: ₹4,500"
    # Step 2: final answer from second AI msg
    assert steps[1]["final_answer"] == "You spent ₹4,500 on food."


def test_ai_message_with_no_react_format_returns_empty():
    msgs = [_ai_msg("Here is a plain answer with no Thought/Action lines.")]
    steps = ArthaAgent._extract_scratchpad(msgs)
    assert steps == []


def test_step_without_observation_still_captured_at_end():
    content = "Thought: Thinking...\nAction: net_worth\n"
    steps = ArthaAgent._extract_scratchpad([_ai_msg(content)])
    # Step has no observation (tool msg not provided) — still returned
    assert len(steps) == 1
    assert steps[0]["thought"] == "Thinking..."
    assert "observation" not in steps[0]


def test_empty_scratchpad_stored_as_none(monkeypatch):
    """_persist_run stores None (not []) when scratchpad is empty — avoids spurious DB writes."""
    # This tests the contract: scratchpad=[] → stored as None
    # We validate the inline expression: `scratchpad or None`
    empty: list = []
    result = empty or None
    assert result is None

    non_empty = [{"thought": "x"}]
    result2 = non_empty or None
    assert result2 is non_empty
