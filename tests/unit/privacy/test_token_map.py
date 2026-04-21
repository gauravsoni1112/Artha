"""Unit tests for TokenMap — deterministic tokens, round-trip detokenisation."""

import pytest
from libs.privacy.token_map import TokenMap


def test_tokenise_name_deterministic():
    tm = TokenMap()
    t1 = tm.tokenise_name("Ravi Kumar")
    t2 = tm.tokenise_name("Ravi Kumar")
    assert t1 == t2
    assert t1.startswith("user_")


def test_tokenise_name_different_names():
    tm = TokenMap()
    assert tm.tokenise_name("Ravi Kumar") != tm.tokenise_name("Priya Singh")


def test_tokenise_merchant_deterministic():
    tm = TokenMap()
    t1 = tm.tokenise_merchant("UNKNOWN SHOP")
    t2 = tm.tokenise_merchant("UNKNOWN SHOP")
    assert t1 == t2
    assert t1.startswith("merchant_")


def test_detokenise_round_trip():
    tm = TokenMap()
    token = tm.tokenise_name("Ravi Kumar")
    result = tm.detokenise(f"{token} should increase his SIP")
    assert result == "Ravi Kumar should increase his SIP"


def test_detokenise_multiple_tokens():
    tm = TokenMap()
    t_name = tm.tokenise_name("Ravi Kumar")
    t_merchant = tm.tokenise_merchant("EXOTIC STORE")
    text = f"{t_name} spent at {t_merchant} last month"
    assert tm.detokenise(text) == "Ravi Kumar spent at EXOTIC STORE last month"


def test_empty_value_passthrough():
    tm = TokenMap()
    assert tm.tokenise_name("") == ""
    assert tm.tokenise_name("  ") == "  "


def test_detokenise_regex_safe():
    tm = TokenMap()
    token = tm.tokenise_name("Priya Singh")
    prose = f"We recommend {token} increases her SIP by ₹2,000."
    assert "Priya Singh" in tm.detokenise_regex(prose)
