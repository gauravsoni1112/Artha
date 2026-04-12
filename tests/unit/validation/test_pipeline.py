"""
Unit tests for services/validation/pipeline.py

Tests cover all 4 stages:
  SCHEMA   — missing required fields
  RANGE    — future dates, zero amounts, implausible amounts
  ANOMALY  — >2.5x rolling average spike detection
  LOCALE   — Indian number format parsing

Uses InMemorySpendHistory for the AnomalyDetector.
"""

import uuid
from datetime import date, timedelta

import pytest

from services.validation.models import RawTransaction
from services.validation.pipeline import InMemorySpendHistory, ValidationPipeline


def _make_valid_tx(**kwargs) -> RawTransaction:
    """Create a minimal valid RawTransaction."""
    defaults = {
        "owner_id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "transaction_date": date(2024, 6, 15),
        "raw_date_text": "15/06/2024",
        "raw_amount_text": "1,000.00",
        "transaction_type": "DEBIT",
        "raw_description": "NEFT Transfer",
        "category": "TRANSFER",
    }
    defaults.update(kwargs)
    return RawTransaction(**defaults)


@pytest.fixture
def pipeline() -> ValidationPipeline:
    return ValidationPipeline(spend_history=InMemorySpendHistory())


# ── Stage 1: SCHEMA ──────────────────────────────────────────────────────────

class TestSchemaValidation:
    def test_valid_record_passes(self, pipeline):
        result = pipeline.run(_make_valid_tx())
        assert result.passed

    def test_missing_amount_fails(self, pipeline):
        tx = _make_valid_tx(raw_amount_text="")
        result = pipeline.run(tx)
        assert not result.passed
        assert result.failed_stage == "SCHEMA"

    def test_missing_date_and_raw_date_fails(self, pipeline):
        tx = _make_valid_tx(transaction_date=None, raw_date_text="")
        result = pipeline.run(tx)
        assert not result.passed
        assert result.failed_stage == "SCHEMA"

    def test_invalid_transaction_type_fails(self, pipeline):
        tx = _make_valid_tx(transaction_type="INVALID")
        result = pipeline.run(tx)
        assert not result.passed
        assert result.failed_stage == "SCHEMA"

    def test_missing_description_fails(self, pipeline):
        tx = _make_valid_tx(raw_description="", description="")
        result = pipeline.run(tx)
        assert not result.passed
        assert result.failed_stage == "SCHEMA"


# ── Stage 2: RANGE ───────────────────────────────────────────────────────────

class TestRangeValidation:
    def test_future_date_fails(self, pipeline):
        future_date = date.today() + timedelta(days=1)
        tx = _make_valid_tx(transaction_date=future_date)
        result = pipeline.run(tx)
        assert not result.passed
        assert result.failed_stage == "RANGE"
        assert "Future" in result.errors[0]

    def test_today_date_passes(self, pipeline):
        tx = _make_valid_tx(transaction_date=date.today())
        result = pipeline.run(tx)
        assert result.passed

    def test_salary_must_be_credit(self, pipeline):
        # Salary with DEBIT type → should pass range (amount_paise not set yet at range stage)
        # But salary with amount_paise set and <= 0 should fail
        tx = _make_valid_tx(category="SALARY", amount_paise=-100, transaction_type="DEBIT")
        result = pipeline.run(tx)
        assert not result.passed
        assert result.failed_stage == "RANGE"

    def test_zero_amount_fails(self, pipeline):
        tx = _make_valid_tx(amount_paise=0)
        result = pipeline.run(tx)
        assert not result.passed
        assert result.failed_stage == "RANGE"

    def test_implausible_amount_fails(self, pipeline):
        # > 10 Cr
        tx = _make_valid_tx(amount_paise=1_100_000_000_00)  # 11 Cr
        result = pipeline.run(tx)
        assert not result.passed
        assert result.failed_stage == "RANGE"

    def test_non_inr_currency_fails(self, pipeline):
        tx = _make_valid_tx(currency="USD")
        result = pipeline.run(tx)
        assert not result.passed
        assert result.failed_stage == "RANGE"


# ── Stage 3: ANOMALY ─────────────────────────────────────────────────────────

class TestAnomalyDetection:
    def test_no_history_passes(self, pipeline):
        # No history → no anomaly flag
        tx = _make_valid_tx(amount_paise=1_000_00, category="GROCERIES")
        result = pipeline.run(tx)
        assert result.passed

    def test_within_threshold_passes(self):
        history = InMemorySpendHistory()
        owner_id = uuid.uuid4()
        history.set(str(owner_id), "GROCERIES", 1_000_00)  # 90-day avg: ₹1000
        pipeline = ValidationPipeline(spend_history=history)

        # 2.4× average → should pass
        tx = _make_valid_tx(
            owner_id=owner_id,
            amount_paise=2_400_00,  # ₹2400
            category="GROCERIES",
        )
        result = pipeline.run(tx)
        assert result.passed

    def test_exceeds_threshold_quarantined(self):
        history = InMemorySpendHistory()
        owner_id = uuid.uuid4()
        history.set(str(owner_id), "GROCERIES", 1_000_00)  # avg: ₹1000
        pipeline = ValidationPipeline(spend_history=history)

        # 3.0× average → should fail
        tx = _make_valid_tx(
            owner_id=owner_id,
            amount_paise=3_000_00,  # ₹3000
            category="GROCERIES",
        )
        result = pipeline.run(tx)
        assert not result.passed
        assert result.failed_stage == "ANOMALY"
        assert "Anomaly" in result.errors[0]

    def test_zero_average_skips_anomaly(self):
        history = InMemorySpendHistory()
        owner_id = uuid.uuid4()
        history.set(str(owner_id), "GROCERIES", 0)  # zero avg → no anomaly check
        pipeline = ValidationPipeline(spend_history=history)

        tx = _make_valid_tx(owner_id=owner_id, amount_paise=999_999_99, category="GROCERIES")
        result = pipeline.run(tx)
        assert result.passed


# ── Stage 4: LOCALE ──────────────────────────────────────────────────────────

class TestLocaleNormalisation:
    def test_indian_format_parsed(self, pipeline):
        tx = _make_valid_tx(raw_amount_text="1,00,000.00", transaction_type="CREDIT")
        result = pipeline.run(tx)
        assert result.passed
        assert result.record.amount_paise == 10000000

    def test_debit_makes_negative(self, pipeline):
        tx = _make_valid_tx(raw_amount_text="500.00", transaction_type="DEBIT")
        result = pipeline.run(tx)
        assert result.passed
        assert result.record.amount_paise == -50000

    def test_credit_is_positive(self, pipeline):
        tx = _make_valid_tx(raw_amount_text="500.00", transaction_type="CREDIT")
        result = pipeline.run(tx)
        assert result.passed
        assert result.record.amount_paise == 50000

    def test_dr_suffix_in_amount(self, pipeline):
        tx = _make_valid_tx(raw_amount_text="250.00 Dr", transaction_type="DEBIT")
        result = pipeline.run(tx)
        assert result.passed
        assert result.record.amount_paise == -25000

    def test_invalid_amount_quarantined(self, pipeline):
        tx = _make_valid_tx(raw_amount_text="not-a-number")
        result = pipeline.run(tx)
        assert not result.passed
        assert result.failed_stage == "LOCALE"

    def test_amount_paise_already_set_skips_locale(self, pipeline):
        # If amount_paise is pre-set (structured API source), LOCALE stage is skipped
        tx = _make_valid_tx(amount_paise=75000, raw_amount_text="")
        # raw_amount_text is empty, but amount_paise is set → LocaleNormalizer skips
        # (But SchemaValidator would fail on empty raw_amount_text — pre-set the amount
        #  via a valid raw_amount_text to not fail stage 1)
        tx2 = _make_valid_tx(amount_paise=75000, raw_amount_text="750.00")
        result = pipeline.run(tx2)
        assert result.passed
        # amount_paise was pre-set → LocaleNormalizer should NOT overwrite it
        assert result.record.amount_paise == 75000


# ── Full pipeline integration ─────────────────────────────────────────────────

class TestFullPipeline:
    def test_clean_salary_credit_passes(self, pipeline):
        tx = _make_valid_tx(
            transaction_date=date(2024, 4, 30),
            raw_amount_text="1,00,000.00",
            transaction_type="CREDIT",
            category="SALARY",
            raw_description="SALARY CREDIT - ACME CORP",
        )
        result = pipeline.run(tx)
        assert result.passed
        assert result.record.amount_paise == 10000000
        assert result.record.transaction_type == "CREDIT"

    def test_error_list_populated_on_failure(self, pipeline):
        tx = _make_valid_tx(raw_amount_text="")
        result = pipeline.run(tx)
        assert not result.passed
        assert len(result.errors) > 0
        assert isinstance(result.errors[0], str)
