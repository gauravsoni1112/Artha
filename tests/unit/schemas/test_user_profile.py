"""Unit tests for UserProfile."""

import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from libs.schemas.user_profile import EMI, FinancialGoal, IncomeSource, UserProfile


def _minimal_profile(**kwargs) -> UserProfile:
    defaults = dict(owner_id=uuid.uuid4(), name="Test User")
    defaults.update(kwargs)
    return UserProfile(**defaults)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_minimal_profile_defaults():
    p = _minimal_profile()
    assert p.income_sources == []
    assert p.emis == []
    assert p.goals == []
    assert p.risk_appetite == "moderate"
    assert p.is_family_scope is False
    assert p.total_monthly_income_paise == 0


def test_full_profile_roundtrip():
    goal_id = uuid.uuid4()
    p = UserProfile(
        owner_id=uuid.uuid4(),
        name="Riya",
        income_sources=[IncomeSource(label="Salary", monthly_paise=500_000_00)],
        total_monthly_income_paise=500_000_00,
        emis=[EMI(label="Home Loan", monthly_paise=30_000_00, remaining_months=180)],
        goals=[
            FinancialGoal(
                goal_id=goal_id,
                label="Emergency Fund",
                target_paise=600_000_00,
                current_paise=200_000_00,
                target_date=date(2026, 12, 31),
            )
        ],
        risk_appetite="aggressive",
        age=32,
    )
    data = p.model_dump()
    restored = UserProfile.model_validate(data)
    assert restored.name == "Riya"
    assert restored.goals[0].goal_id == goal_id


# ---------------------------------------------------------------------------
# risk_appetite validation
# ---------------------------------------------------------------------------


def test_valid_risk_appetites():
    for v in ("conservative", "moderate", "aggressive"):
        p = _minimal_profile(risk_appetite=v)
        assert p.risk_appetite == v


def test_invalid_risk_appetite_raises():
    with pytest.raises(ValidationError, match="risk_appetite"):
        _minimal_profile(risk_appetite="reckless")


# ---------------------------------------------------------------------------
# Computed properties
# ---------------------------------------------------------------------------


def test_total_monthly_emi_paise():
    p = _minimal_profile(
        emis=[
            EMI(label="Car", monthly_paise=10_000_00, remaining_months=24),
            EMI(label="Home", monthly_paise=30_000_00, remaining_months=200),
        ]
    )
    assert p.total_monthly_emi_paise == 40_000_00


def test_debt_to_income_ratio():
    p = _minimal_profile(
        total_monthly_income_paise=100_000_00,
        emis=[EMI(label="Loan", monthly_paise=30_000_00, remaining_months=12)],
    )
    assert p.debt_to_income_ratio == pytest.approx(0.30)


def test_debt_to_income_ratio_zero_income():
    p = _minimal_profile(
        total_monthly_income_paise=0,
        emis=[EMI(label="Loan", monthly_paise=10_000_00, remaining_months=6)],
    )
    assert p.debt_to_income_ratio is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_negative_monthly_paise_rejected():
    with pytest.raises(ValidationError):
        IncomeSource(label="Bad", monthly_paise=-1)


def test_age_bounds():
    _minimal_profile(age=0)
    _minimal_profile(age=120)
    with pytest.raises(ValidationError):
        _minimal_profile(age=121)
    with pytest.raises(ValidationError):
        _minimal_profile(age=-1)
