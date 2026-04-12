"""
Unit tests for libs/tax_rules/fiscal_year.py
"""

import pytest
from datetime import date

from libs.tax_rules.fiscal_year import get_fiscal_year, fiscal_year_range


class TestGetFiscalYear:
    def test_april_start(self):
        assert get_fiscal_year(date(2024, 4, 1)) == "2024-25"

    def test_march_end(self):
        assert get_fiscal_year(date(2025, 3, 31)) == "2024-25"

    def test_january_mid_year(self):
        assert get_fiscal_year(date(2025, 1, 15)) == "2024-25"

    def test_april_new_year(self):
        assert get_fiscal_year(date(2025, 4, 1)) == "2025-26"

    def test_december_first_half(self):
        assert get_fiscal_year(date(2024, 12, 31)) == "2024-25"

    def test_year_2099(self):
        # Edge case: century boundary
        assert get_fiscal_year(date(2099, 6, 1)) == "2099-00"

    def test_format_two_digit_end(self):
        result = get_fiscal_year(date(2024, 7, 1))
        parts = result.split("-")
        assert len(parts) == 2
        assert len(parts[1]) == 2

    def test_fy_2023_24(self):
        assert get_fiscal_year(date(2023, 5, 1)) == "2023-24"
        assert get_fiscal_year(date(2024, 3, 15)) == "2023-24"


class TestFiscalYearRange:
    def test_2024_25(self):
        start, end = fiscal_year_range("2024-25")
        assert start == date(2024, 4, 1)
        assert end == date(2025, 3, 31)

    def test_2023_24(self):
        start, end = fiscal_year_range("2023-24")
        assert start == date(2023, 4, 1)
        assert end == date(2024, 3, 31)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            fiscal_year_range("2024")

    def test_invalid_chars_raises(self):
        with pytest.raises(ValueError):
            fiscal_year_range("XXXX-YY")

    def test_round_trip_with_get_fiscal_year(self):
        d = date(2024, 9, 15)
        fy = get_fiscal_year(d)
        start, end = fiscal_year_range(fy)
        assert start <= d <= end
