"""Unit tests for services/agent/grounding.py — numeric grounding check."""

from __future__ import annotations

import pytest

from services.agent.grounding import check_answer_grounding, extract_inr_amounts


# ── extract_inr_amounts ────────────────────────────────────────────────────────

def test_extract_plain_rupee():
    assert extract_inr_amounts("You spent ₹5000") == {500000}


def test_extract_indian_formatted():
    assert extract_inr_amounts("Balance: ₹1,00,000") == {10000000}


def test_extract_with_paise():
    assert extract_inr_amounts("₹1,234.50") == {123450}


def test_extract_multiple_amounts():
    text = "Income ₹50,000 and expenses ₹20,000"
    assert extract_inr_amounts(text) == {5000000, 2000000}


def test_extract_ignores_sub_rupee():
    # ₹0.50 → 50 paise — below ₹1 threshold, should be excluded
    assert extract_inr_amounts("Fee: ₹0.50") == set()


def test_extract_no_amounts():
    assert extract_inr_amounts("No rupee figures here") == set()


def test_extract_with_space_after_symbol():
    assert extract_inr_amounts("₹ 5,000") == {500000}


def test_extract_large_crore():
    assert extract_inr_amounts("Net worth ₹1,00,00,000") == {1000000000}


# ── check_answer_grounding — grounded cases ───────────────────────────────────

def test_grounded_exact_match():
    answer = "Your balance is ₹50,000."
    tool_outputs = ["account balance: ₹50,000"]
    is_grounded, ungrounded = check_answer_grounding(answer, tool_outputs)
    assert is_grounded is True
    assert ungrounded == []


def test_grounded_within_tolerance():
    # ₹50,000 vs ₹50,000.50 — within ±₹1
    answer = "Balance ₹50,000"
    tool_outputs = ["balance_paise=5000050 (₹50,000.50)"]
    is_grounded, ungrounded = check_answer_grounding(answer, tool_outputs)
    assert is_grounded is True


def test_grounded_no_amounts_in_answer():
    answer = "No specific figures available."
    tool_outputs = ["₹10,000 from groceries"]
    is_grounded, ungrounded = check_answer_grounding(answer, tool_outputs)
    assert is_grounded is True
    assert ungrounded == []


def test_grounded_multiple_amounts_all_present():
    answer = "Income ₹1,00,000, expenses ₹40,000, savings ₹60,000."
    tool_outputs = [
        "total_income=₹1,00,000",
        "total_expenses=₹40,000",
        "net_savings=₹60,000",
    ]
    is_grounded, ungrounded = check_answer_grounding(answer, tool_outputs)
    assert is_grounded is True


# ── check_answer_grounding — ungrounded cases ─────────────────────────────────

def test_ungrounded_hallucinated_amount():
    answer = "Your savings are ₹2,00,000."
    tool_outputs = ["balance: ₹50,000"]
    is_grounded, ungrounded = check_answer_grounding(answer, tool_outputs)
    assert is_grounded is False
    assert 20000000 in ungrounded  # ₹2,00,000 = 20000000 paise


def test_ungrounded_partial():
    # ₹50,000 is in tool output but ₹99,999 is hallucinated
    answer = "Groceries ₹50,000 and dining ₹99,999."
    tool_outputs = ["groceries=₹50,000"]
    is_grounded, ungrounded = check_answer_grounding(answer, tool_outputs)
    assert is_grounded is False
    assert 9999900 in ungrounded  # ₹99,999 not in tool output


def test_ungrounded_empty_tool_outputs():
    answer = "You spent ₹10,000."
    is_grounded, ungrounded = check_answer_grounding(answer, [])
    assert is_grounded is False
    assert 1000000 in ungrounded


def test_grounded_amount_appears_in_concatenated_outputs():
    # Amount is in the second tool output
    answer = "Tax paid ₹25,000."
    tool_outputs = ["no_data", "tax_amount=₹25,000"]
    is_grounded, ungrounded = check_answer_grounding(answer, tool_outputs)
    assert is_grounded is True
