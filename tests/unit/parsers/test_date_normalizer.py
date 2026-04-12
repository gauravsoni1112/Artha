"""Unit tests for date normalizer."""

from datetime import date
import pytest

from services.ingestion.normalizers.date_normalizer import parse_date, parse_date_strict


class TestParseDateFormats:
    def test_dd_mm_yyyy_slash(self):
        assert parse_date("15/03/2024") == date(2024, 3, 15)

    def test_dd_mm_yyyy_dash(self):
        assert parse_date("15-03-2024") == date(2024, 3, 15)

    def test_dd_mon_yyyy(self):
        assert parse_date("15-Mar-2024") == date(2024, 3, 15)

    def test_dd_mon_yy(self):
        assert parse_date("15-Mar-24") == date(2024, 3, 15)

    def test_iso_format(self):
        assert parse_date("2024-03-15") == date(2024, 3, 15)

    def test_dd_mmm_yyyy_space(self):
        assert parse_date("15 Mar 2024") == date(2024, 3, 15)

    def test_dd_dot_mm_dot_yyyy(self):
        assert parse_date("15.03.2024") == date(2024, 3, 15)

    def test_empty_returns_none(self):
        assert parse_date("") is None

    def test_none_returns_none(self):
        assert parse_date(None) is None  # type: ignore

    def test_garbage_returns_none(self):
        assert parse_date("not-a-date") is None

    def test_strict_raises_on_garbage(self):
        with pytest.raises(ValueError):
            parse_date_strict("not-a-date")

    def test_strict_returns_date(self):
        assert parse_date_strict("01/04/2024") == date(2024, 4, 1)


class TestCategoryMapper:
    def test_salary_keyword(self):
        from services.ingestion.normalizers.category_mapper import map_category
        assert map_category("SALARY CREDIT - ACME CORP") == "SALARY"

    def test_grocery_keyword(self):
        from services.ingestion.normalizers.category_mapper import map_category
        assert map_category("BigBasket grocery order") == "GROCERIES"

    def test_emi_keyword(self):
        from services.ingestion.normalizers.category_mapper import map_category
        assert map_category("EMI HDFC HOME LOAN") == "EMI"

    def test_unknown_description(self):
        from services.ingestion.normalizers.category_mapper import map_category
        assert map_category("xyzzy random vendor") == "UNKNOWN"

    def test_case_insensitive(self):
        from services.ingestion.normalizers.category_mapper import map_category
        assert map_category("salary payment") == "SALARY"
        assert map_category("SALARY PAYMENT") == "SALARY"
