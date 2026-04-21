"""Unit tests for Anonymiser — scrub idempotence, field rules, round-trip."""

import json
import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from libs.privacy.anonymiser import Anonymiser, _bucket_income
from libs.privacy.token_map import TokenMap

anon = Anonymiser()


# ---------------------------------------------------------------------------
# Income bucketing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("paise,expected", [
    (150_000, 0),           # ₹1 500 → bucket 0
    (500_000, 500_000),     # ₹5 000 → bucket ₹5 000
    (4_750_000, 5_000_000), # ₹47 500 → ₹50 000
    (10_000_000, 10_000_000),  # ₹1 00 000 → stays
    (10_200_000, 10_000_000),  # ₹1 02 000 → ₹1 00 000
    (10_300_000, 10_500_000),  # ₹1 03 000 → ₹1 05 000
])
def test_bucket_income(paise, expected):
    assert _bucket_income(paise) == expected


# ---------------------------------------------------------------------------
# Profile context scrubbing
# ---------------------------------------------------------------------------

def test_scrub_profile_context_owner_id():
    tm = TokenMap()
    content = "[User profile] owner_id=550e8400-e29b-41d4-a716-446655440000 income=5000000p/mo risk=moderate"
    scrubbed = anon.scrub_profile_context(content, tm)
    assert "550e8400-e29b-41d4-a716-446655440000" not in scrubbed
    assert "user_" in scrubbed


def test_scrub_profile_context_income_bucketed():
    tm = TokenMap()
    content = "[User profile] owner_id=abc income=4750000p/mo risk=moderate"
    scrubbed = anon.scrub_profile_context(content, tm)
    # ₹47 500 → ₹50 000 = 5 000 000 paise
    assert "5000000p" in scrubbed
    assert "4750000p" not in scrubbed


# ---------------------------------------------------------------------------
# System prompt scrubbing
# ---------------------------------------------------------------------------

def test_scrub_system_prompt_name():
    tm = TokenMap()
    content = "You are Artha, a personal finance assistant for Ravi Kumar. You specialise in cashflow."
    scrubbed = anon.scrub_system_prompt(content, tm)
    assert "Ravi Kumar" not in scrubbed
    assert "user_" in scrubbed
    token = tm.forward["Ravi Kumar"]
    assert token in scrubbed


# ---------------------------------------------------------------------------
# Tool result JSON scrubbing
# ---------------------------------------------------------------------------

def test_scrub_tool_result_drops_description():
    tm = TokenMap()
    data = {"amount": 100000, "description": "HDFC BANK UPI transfer to Ravi"}
    scrubbed = json.loads(anon.scrub_tool_result_json(json.dumps(data), tm))
    assert scrubbed["description"] == "[redacted]"
    assert scrubbed["amount"] == 100000


def test_scrub_tool_result_merchant_to_category():
    tm = TokenMap()
    data = {"counterparty_name": "SWIGGY ORDER 12345", "amount": 35000}
    scrubbed = json.loads(anon.scrub_tool_result_json(json.dumps(data), tm))
    assert scrubbed["counterparty_name"] == "food_delivery"


def test_scrub_tool_result_unknown_merchant_tokenised():
    tm = TokenMap()
    data = {"counterparty_name": "EXOTIC BESPOKE STORE", "amount": 5000}
    scrubbed = json.loads(anon.scrub_tool_result_json(json.dumps(data), tm))
    assert scrubbed["counterparty_name"].startswith("merchant_")


def test_scrub_tool_result_pan_in_text():
    tm = TokenMap()
    data = {"answer": "User PAN is ABCDE1234F, balance ₹10,000"}
    scrubbed = json.loads(anon.scrub_tool_result_json(json.dumps(data), tm))
    assert "ABCDE1234F" not in scrubbed["answer"]
    assert "pan_redacted" in scrubbed["answer"]


def test_scrub_tool_result_explicit_pan_field():
    tm = TokenMap()
    data = {"pan": "ABCDE1234F", "name": "Ravi Kumar"}
    scrubbed = json.loads(anon.scrub_tool_result_json(json.dumps(data), tm))
    assert scrubbed["pan"] == "[pan_redacted]"
    assert scrubbed["name"].startswith("user_")


# ---------------------------------------------------------------------------
# Message-list scrubbing
# ---------------------------------------------------------------------------

def test_scrub_messages_system_and_profile():
    tm = TokenMap()
    messages = [
        SystemMessage(content="You are Artha, a personal finance assistant for Ravi Kumar."),
        HumanMessage(content="[User profile] owner_id=550e8400-e29b-41d4-a716-446655440000 income=5000000p/mo risk=moderate"),
        HumanMessage(content="What is my net worth?"),
    ]
    scrubbed = anon.scrub_messages(messages, tm)
    assert "Ravi Kumar" not in scrubbed[0].content
    assert "550e8400" not in scrubbed[1].content
    assert scrubbed[2].content == "What is my net worth?"  # query untouched


# ---------------------------------------------------------------------------
# Detokenisation round-trip
# ---------------------------------------------------------------------------

def test_detokenise_round_trip():
    tm = TokenMap()
    messages = [
        SystemMessage(content="You are Artha, a personal finance assistant for Priya Singh."),
    ]
    anon.scrub_messages(messages, tm)  # populate tm
    token = tm.forward.get("Priya Singh")
    assert token is not None
    answer = f"{token} should increase her emergency fund."
    restored = anon.detokenise_answer(answer, tm)
    assert "Priya Singh" in restored
    assert token not in restored


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------

def test_scrub_idempotent():
    tm = TokenMap()
    data = {"counterparty_name": "SWIGGY", "description": "food order", "amount": 25000}
    first = anon.scrub_tool_result_json(json.dumps(data), tm)
    second = anon.scrub_tool_result_json(first, tm)
    assert first == second
