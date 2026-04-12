"""
Unit tests for libs/schemas/money.py

Tests cover:
  - Basic INR parsing (plain integers and decimals)
  - Indian number format with commas (1,00,000)
  - ₹ symbol stripping
  - Dr/Cr suffix interpretation
  - Negative values
  - Fractional paise rounding
  - format_inr round-trip
  - Error cases
"""

import pytest

from libs.schemas.money import format_inr, parse_inr_to_paise


class TestParseInrToPaise:
    def test_plain_integer(self):
        assert parse_inr_to_paise("500") == 50000

    def test_plain_decimal(self):
        assert parse_inr_to_paise("500.00") == 50000

    def test_decimal_paise(self):
        assert parse_inr_to_paise("500.50") == 50050

    def test_indian_format_lakh(self):
        assert parse_inr_to_paise("1,00,000") == 10000000

    def test_indian_format_crore(self):
        assert parse_inr_to_paise("1,00,00,000") == 1000000000

    def test_indian_format_with_decimal(self):
        assert parse_inr_to_paise("1,00,000.50") == 10000050

    def test_rupee_symbol_stripped(self):
        assert parse_inr_to_paise("₹ 5,00,000") == 50000000

    def test_rupee_symbol_no_space(self):
        assert parse_inr_to_paise("₹500.00") == 50000

    def test_negative_value(self):
        assert parse_inr_to_paise("-1,234.56") == -123456

    def test_dr_suffix_makes_negative(self):
        # "Dr" suffix = debit = negative
        assert parse_inr_to_paise("500.00 Dr") == -50000

    def test_cr_suffix_is_positive(self):
        assert parse_inr_to_paise("500.00 CR") == 50000

    def test_zero(self):
        assert parse_inr_to_paise("0") == 0

    def test_single_digit_fraction(self):
        # "500.5" → 500.50 → 50050 paise
        assert parse_inr_to_paise("500.5") == 50050

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_inr_to_paise("")

    def test_non_string_raises(self):
        with pytest.raises(ValueError):
            parse_inr_to_paise(None)  # type: ignore

    def test_garbage_string_raises(self):
        with pytest.raises(ValueError):
            parse_inr_to_paise("not-a-number")

    def test_unicode_minus_sign(self):
        # Unicode minus (−, U+2212) should work
        assert parse_inr_to_paise("−500.00") < 0


class TestFormatInr:
    def test_simple_rupees(self):
        assert format_inr(50000) == "₹500.00"

    def test_lakh(self):
        assert format_inr(10000000) == "₹1,00,000.00"

    def test_crore(self):
        result = format_inr(1000000000)
        assert "1,00,00,000" in result

    def test_paise_part(self):
        assert format_inr(50050) == "₹500.50"

    def test_negative(self):
        result = format_inr(-50000)
        assert result.startswith("-₹")
        assert "500.00" in result

    def test_zero(self):
        assert format_inr(0) == "₹0.00"

    def test_non_int_raises(self):
        with pytest.raises(TypeError):
            format_inr(500.0)  # type: ignore

    def test_round_trip(self):
        original = 12345678
        formatted = format_inr(original)
        parsed = parse_inr_to_paise(formatted)
        assert parsed == original
