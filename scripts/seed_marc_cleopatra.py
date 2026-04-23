"""
Seed dummy data for Marc Antony (aggressive risk) and Cleopatra (moderate risk).

Family structure:
  Marc Antony  — PRIMARY  (owner_id = 22222222-2222-2222-2222-222222222222, PIN: 5678)
  Cleopatra    — SPOUSE   (owner_id = 33333333-3333-3333-3333-333333333333, PIN: 9012)

Populates for each owner:
  - Owner + PIN
  - 4 Accounts at different banks
  - UserProfile + UserProfileScope
  - 4 Financial Goals
  - 24 months of transactions (FY 2024-25 + FY 2025-26)
  - Holdings appropriate to risk profile
  - TaxData: FY 2023-24 (filed) + FY 2024-25 (filed) + FY 2025-26 (in progress)
  - FamilyMembership rows (Marc=PRIMARY, Cleopatra=SPOUSE)

Run from repo root:
    python scripts/seed_marc_cleopatra.py
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import AsyncSessionLocal
from api.deps import hash_pin
from libs.schemas.db_models import (
    Account,
    FamilyMembership,
    FinancialGoal,
    Holding,
    Owner,
    TaxData,
    Transaction,
    UserProfile,
    UserProfileScope,
)

# ---------------------------------------------------------------------------
# Constants — Marc Antony
# ---------------------------------------------------------------------------

MARC_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
MARC_PIN = "5678"

MARC_HDFC_SAV_ID   = uuid.UUID("aaaaaaaa-2222-2222-2222-222222222222")
MARC_SBI_SAV_ID    = uuid.UUID("bbbbbbbb-2222-2222-2222-222222222222")
MARC_AXIS_CC_ID    = uuid.UUID("cccccccc-2222-2222-2222-222222222222")
MARC_ZERODHA_ID    = uuid.UUID("dddddddd-2222-2222-2222-222222222222")  # DEMAT

# ---------------------------------------------------------------------------
# Constants — Cleopatra
# ---------------------------------------------------------------------------

CLEO_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
CLEO_PIN = "9012"

CLEO_ICICI_SAV_ID  = uuid.UUID("aaaaaaaa-3333-3333-3333-333333333333")
CLEO_KOTAK_SAV_ID  = uuid.UUID("bbbbbbbb-3333-3333-3333-333333333333")
CLEO_HDFC_CC_ID    = uuid.UUID("cccccccc-3333-3333-3333-333333333333")
CLEO_GROWW_MF_ID   = uuid.UUID("dddddddd-3333-3333-3333-333333333333")  # MF_FOLIO

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sh(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _txn(
    *,
    owner_id: uuid.UUID,
    seed: str,
    account_id: uuid.UUID,
    txn_date: date,
    amount_paise: int,
    txn_type: str,
    category: str,
    description: str,
    merchant: str | None = None,
    fiscal_year: str,
) -> Transaction:
    return Transaction(
        id=uuid.uuid5(owner_id, seed),
        owner_id=owner_id,
        account_id=account_id,
        source_hash=_sh(seed),
        transaction_date=txn_date,
        value_date=txn_date,
        amount_paise=amount_paise,
        transaction_type=txn_type,
        category=category,
        description=description,
        raw_description=description,
        merchant=merchant,
        fiscal_year=fiscal_year,
        currency="INR",
    )


def _fy(d: date) -> str:
    """Return Indian fiscal year string for a given date."""
    if d.month >= 4:
        return f"{d.year}-{str(d.year + 1)[-2:]}"
    return f"{d.year - 1}-{str(d.year)[-2:]}"


# ---------------------------------------------------------------------------
# Marc Antony — Owner + Accounts
# ---------------------------------------------------------------------------

def build_marc_owner() -> Owner:
    return Owner(
        id=MARC_ID,
        name="Marc Antony",
        is_admin=False,
        pin_hash=hash_pin(MARC_PIN),
    )


def build_marc_accounts() -> list[Account]:
    return [
        Account(
            id=MARC_HDFC_SAV_ID,
            owner_id=MARC_ID,
            account_type="SAVINGS",
            institution="HDFC Bank",
            nickname="HDFC Primary Savings",
            is_active=True,
        ),
        Account(
            id=MARC_SBI_SAV_ID,
            owner_id=MARC_ID,
            account_type="SAVINGS",
            institution="State Bank of India",
            nickname="SBI Savings",
            is_active=True,
        ),
        Account(
            id=MARC_AXIS_CC_ID,
            owner_id=MARC_ID,
            account_type="CREDIT_CARD",
            institution="Axis Bank",
            nickname="Axis Magnus CC",
            is_active=True,
        ),
        Account(
            id=MARC_ZERODHA_ID,
            owner_id=MARC_ID,
            account_type="DEMAT",
            institution="Zerodha",
            nickname="Zerodha Demat",
            is_active=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Marc Antony — Profile
# ---------------------------------------------------------------------------

def build_marc_profile() -> UserProfile:
    return UserProfile(
        owner_id=MARC_ID,
        risk_appetite="aggressive",
        age=38,
        is_family_scope=True,
        total_monthly_income_paise=30_00_000_00,   # ₹3,00,000/month
        income_sources_json=[
            {"label": "Salary – TechVentures Ltd", "monthly_paise": 25_00_000_00},
            {"label": "Trading & STCG", "monthly_paise": 5_00_000_00},
        ],
        emis_json=[
            {"label": "Home Loan – HDFC", "monthly_paise": 6_00_000_00},
            {"label": "Car Loan – BMW FS", "monthly_paise": 1_80_000_00},
        ],
        preferences={"theme": "dark", "currency_display": "full"},
    )


# ---------------------------------------------------------------------------
# Marc Antony — Goals
# ---------------------------------------------------------------------------

def build_marc_goals() -> list[FinancialGoal]:
    return [
        FinancialGoal(
            id=uuid.UUID("11111111-aaaa-aaaa-aaaa-222222222222"),
            owner_id=MARC_ID,
            goal_name="Equity Portfolio ₹1 Crore",
            target_amount_paise=1_00_00_00_000_00,  # ₹1,00,00,000
            current_amount_paise=62_50_00_000_00,   # ₹62,50,000 — 62.5%
            target_date=date(2027, 3, 31),
            category="INVESTMENT",
            is_active=True,
        ),
        FinancialGoal(
            id=uuid.UUID("22222222-aaaa-aaaa-aaaa-222222222222"),
            owner_id=MARC_ID,
            goal_name="Second Property Down Payment",
            target_amount_paise=50_00_00_000_00,    # ₹50,00,000
            current_amount_paise=18_00_00_000_00,   # ₹18,00,000 — 36%
            target_date=date(2028, 6, 30),
            category="REAL_ESTATE",
            is_active=True,
        ),
        FinancialGoal(
            id=uuid.UUID("33333333-aaaa-aaaa-aaaa-222222222222"),
            owner_id=MARC_ID,
            goal_name="Family Europe Trip",
            target_amount_paise=8_00_00_000_00,     # ₹8,00,000
            current_amount_paise=5_60_00_000_00,    # ₹5,60,000 — 70%
            target_date=date(2026, 12, 31),
            category="TRAVEL",
            is_active=True,
        ),
        FinancialGoal(
            id=uuid.UUID("44444444-aaaa-aaaa-aaaa-222222222222"),
            owner_id=MARC_ID,
            goal_name="Emergency Fund (12 months)",
            target_amount_paise=36_00_00_000_00,    # ₹36,00,000
            current_amount_paise=36_00_00_000_00,   # 100% — complete
            target_date=date(2025, 3, 31),
            category="SAVINGS",
            is_active=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Marc Antony — Transactions (24 months: Apr 2024 – Apr 2026)
# ---------------------------------------------------------------------------

def build_marc_transactions() -> list[Transaction]:
    txns: list[Transaction] = []

    # Monthly base salary credit + recurring debits for every month
    # Each tuple: (month_offset_from_apr2024, year, month)
    months = [
        (date(2024, m, 1) if m >= 4 else date(2025, m, 1))
        for m in list(range(4, 13)) + list(range(1, 4))
    ]
    months += [
        (date(2025, m, 1) if m >= 4 else date(2026, m, 1))
        for m in list(range(4, 13)) + list(range(1, 4))
    ]
    months += [date(2026, 4, 1)]  # Apr 2026

    def mo(d: date) -> str:
        return d.strftime("%Y%m")

    for d in months:
        fy = _fy(d)
        m = mo(d)

        # Salary
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-sal-{m}",
            account_id=MARC_HDFC_SAV_ID, txn_date=date(d.year, d.month, 1),
            amount_paise=25_00_000_00, txn_type="CREDIT", category="SALARY",
            description=f"TechVentures Salary {d.strftime('%b %Y')}", merchant="TechVentures Ltd",
            fiscal_year=fy))

        # Trading income (variable — aggressive profile)
        trading_amt = 3_00_000_00 + (int(_sh(f"marc-trading-{m}")[:4], 16) % 5_00_000_00)
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-trading-{m}",
            account_id=MARC_HDFC_SAV_ID, txn_date=date(d.year, d.month, 5),
            amount_paise=trading_amt, txn_type="CREDIT", category="INVESTMENT",
            description=f"Zerodha P&L transfer {d.strftime('%b %Y')}", merchant="Zerodha",
            fiscal_year=fy))

        # Home loan EMI
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-homeloan-{m}",
            account_id=MARC_HDFC_SAV_ID, txn_date=date(d.year, d.month, 5),
            amount_paise=6_00_000_00, txn_type="DEBIT", category="EMI",
            description=f"HDFC Home Loan EMI {d.strftime('%b %Y')}", merchant="HDFC Bank",
            fiscal_year=fy))

        # Car loan EMI
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-carloan-{m}",
            account_id=MARC_HDFC_SAV_ID, txn_date=date(d.year, d.month, 6),
            amount_paise=1_80_000_00, txn_type="DEBIT", category="EMI",
            description=f"BMW Financial Services EMI {d.strftime('%b %Y')}", merchant="BMW FS",
            fiscal_year=fy))

        # SIP investments — aggressive: equity-heavy SIPs
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-sip-nifty500-{m}",
            account_id=MARC_HDFC_SAV_ID, txn_date=date(d.year, d.month, 10),
            amount_paise=2_00_000_00, txn_type="DEBIT", category="INVESTMENT",
            description=f"Zerodha SIP – Nifty 500 Index {d.strftime('%b %Y')}", merchant="Zerodha",
            fiscal_year=fy))

        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-sip-smallcap-{m}",
            account_id=MARC_HDFC_SAV_ID, txn_date=date(d.year, d.month, 10),
            amount_paise=1_50_000_00, txn_type="DEBIT", category="INVESTMENT",
            description=f"Zerodha SIP – Small Cap 250 {d.strftime('%b %Y')}", merchant="Zerodha",
            fiscal_year=fy))

        # Rent
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-rent-{m}",
            account_id=MARC_HDFC_SAV_ID, txn_date=date(d.year, d.month, 5),
            amount_paise=5_00_000_00, txn_type="DEBIT", category="RENT",
            description=f"Rent – Prestige Towers {d.strftime('%b %Y')}", merchant="Landlord",
            fiscal_year=fy))

        # Groceries
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-groc-{m}",
            account_id=MARC_AXIS_CC_ID, txn_date=date(d.year, d.month, 8),
            amount_paise=80_000_00, txn_type="DEBIT", category="GROCERIES",
            description=f"BigBasket + Blinkit {d.strftime('%b %Y')}", merchant="BigBasket",
            fiscal_year=fy))

        # Dining
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-dining-{m}",
            account_id=MARC_AXIS_CC_ID, txn_date=date(d.year, d.month, 12),
            amount_paise=60_000_00, txn_type="DEBIT", category="DINING",
            description=f"Restaurants & Zomato {d.strftime('%b %Y')}", merchant="Zomato",
            fiscal_year=fy))

        # Transport
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-transport-{m}",
            account_id=MARC_AXIS_CC_ID, txn_date=date(d.year, d.month, 15),
            amount_paise=25_000_00, txn_type="DEBIT", category="TRANSPORT",
            description=f"Uber + Fuel {d.strftime('%b %Y')}", merchant="Uber",
            fiscal_year=fy))

        # Utilities
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-utils-{m}",
            account_id=MARC_HDFC_SAV_ID, txn_date=date(d.year, d.month, 12),
            amount_paise=12_000_00, txn_type="DEBIT", category="UTILITIES",
            description=f"BESCOM + Airtel {d.strftime('%b %Y')}", merchant="BESCOM",
            fiscal_year=fy))

        # Entertainment
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-ent-{m}",
            account_id=MARC_AXIS_CC_ID, txn_date=date(d.year, d.month, 10),
            amount_paise=8_000_00, txn_type="DEBIT", category="ENTERTAINMENT",
            description=f"OTT subscriptions {d.strftime('%b %Y')}", merchant="Netflix",
            fiscal_year=fy))

        # Insurance premium (annual — only in April)
        if d.month == 4:
            txns.append(_txn(owner_id=MARC_ID, seed=f"marc-insurance-{m}",
                account_id=MARC_HDFC_SAV_ID, txn_date=date(d.year, d.month, 16),
                amount_paise=1_20_000_00, txn_type="DEBIT", category="INSURANCE",
                description=f"HDFC Life Term Premium {d.year}", merchant="HDFC Life",
                fiscal_year=fy))

        # Savings interest
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-interest-{m}",
            account_id=MARC_SBI_SAV_ID, txn_date=date(d.year, d.month, 28) if d.month != 2 else date(d.year, 2, 28),
            amount_paise=45_000_00, txn_type="CREDIT", category="INTEREST",
            description=f"SBI Savings interest {d.strftime('%b %Y')}", merchant="SBI",
            fiscal_year=fy))

        # Equity buy/sell via Zerodha (variable — aggressive)
        buy_amt = 5_00_000_00 + (int(_sh(f"marc-eq-buy-{m}")[:4], 16) % 10_00_000_00)
        txns.append(_txn(owner_id=MARC_ID, seed=f"marc-eq-buy-{m}",
            account_id=MARC_ZERODHA_ID, txn_date=date(d.year, d.month, 7),
            amount_paise=buy_amt, txn_type="DEBIT", category="INVESTMENT",
            description=f"Equity purchase – NSE {d.strftime('%b %Y')}", merchant="Zerodha",
            fiscal_year=fy))

        # Dividend credits (quarterly — Jan, Apr, Jul, Oct)
        if d.month in (1, 4, 7, 10):
            txns.append(_txn(owner_id=MARC_ID, seed=f"marc-dividend-{m}",
                account_id=MARC_HDFC_SAV_ID, txn_date=date(d.year, d.month, 20),
                amount_paise=35_000_00, txn_type="CREDIT", category="DIVIDEND",
                description=f"TCS + Infosys dividend {d.strftime('%b %Y')}", merchant="BSE",
                fiscal_year=fy))

        # Tax advance payment (quarterly: Jun, Sep, Dec, Mar)
        if d.month in (6, 9, 12, 3):
            txns.append(_txn(owner_id=MARC_ID, seed=f"marc-advtax-{m}",
                account_id=MARC_HDFC_SAV_ID, txn_date=date(d.year, d.month, 15),
                amount_paise=2_50_000_00, txn_type="DEBIT", category="TAX",
                description=f"Advance tax payment {d.strftime('%b %Y')}", merchant="Income Tax Dept",
                fiscal_year=fy))

    return txns


# ---------------------------------------------------------------------------
# Marc Antony — Holdings
# ---------------------------------------------------------------------------

def build_marc_holdings() -> list[Holding]:
    return [
        Holding(
            id=uuid.UUID("11111111-bbbb-bbbb-bbbb-222222222222"),
            owner_id=MARC_ID,
            account_id=MARC_ZERODHA_ID,
            asset_class="EQUITY",
            instrument_name="Reliance Industries Ltd",
            isin="INE002A01018",
            units=200.0,
            nav_paise=2_85_000_00,           # ₹2,850/share
            purchase_price_paise=40_00_00_000_00,  # ₹40,00,000 cost
            current_value_paise=57_00_00_000_00,   # ₹57,00,000
            valuation_date=date(2026, 4, 15),
            metadata_={"broker": "Zerodha", "exchange": "NSE"},
        ),
        Holding(
            id=uuid.UUID("22222222-bbbb-bbbb-bbbb-222222222222"),
            owner_id=MARC_ID,
            account_id=MARC_ZERODHA_ID,
            asset_class="EQUITY",
            instrument_name="HDFC Bank Ltd",
            isin="INE040A01034",
            units=300.0,
            nav_paise=1_72_000_00,           # ₹1,720/share
            purchase_price_paise=42_00_00_000_00,  # ₹42,00,000 cost
            current_value_paise=51_60_00_000_00,   # ₹51,60,000
            valuation_date=date(2026, 4, 15),
            metadata_={"broker": "Zerodha", "exchange": "NSE"},
        ),
        Holding(
            id=uuid.UUID("33333333-bbbb-bbbb-bbbb-222222222222"),
            owner_id=MARC_ID,
            account_id=MARC_ZERODHA_ID,
            asset_class="EQUITY",
            instrument_name="Tata Consultancy Services Ltd",
            isin="INE467B01029",
            units=100.0,
            nav_paise=3_95_000_00,           # ₹3,950/share
            purchase_price_paise=30_00_00_000_00,  # ₹30,00,000 cost
            current_value_paise=39_50_00_000_00,   # ₹39,50,000
            valuation_date=date(2026, 4, 15),
            metadata_={"broker": "Zerodha", "exchange": "NSE"},
        ),
        Holding(
            id=uuid.UUID("44444444-bbbb-bbbb-bbbb-222222222222"),
            owner_id=MARC_ID,
            account_id=MARC_ZERODHA_ID,
            asset_class="MUTUAL_FUND",
            instrument_name="Nippon India Small Cap Fund – Direct Growth",
            isin="INF204K01I28",
            units=1850.500,
            nav_paise=18_500_00,             # ₹185 NAV
            purchase_price_paise=25_00_00_000_00,   # ₹25,00,000 cost
            current_value_paise=34_23_425_00,       # current value
            valuation_date=date(2026, 4, 15),
            metadata_={"folio": "MRC-001-NIPPON"},
        ),
        Holding(
            id=uuid.UUID("55555555-bbbb-bbbb-bbbb-222222222222"),
            owner_id=MARC_ID,
            account_id=MARC_SBI_SAV_ID,
            asset_class="FD",
            instrument_name="SBI Fixed Deposit – 24 months",
            isin=None,
            units=None,
            nav_paise=None,
            purchase_price_paise=10_00_00_000_00,   # ₹10,00,000
            current_value_paise=11_60_00_000_00,    # ₹11,60,000 (maturity @ 7.5%)
            valuation_date=date(2026, 4, 15),
            metadata_={"maturity_date": "2026-12-31", "rate_pct": 7.5},
        ),
        Holding(
            id=uuid.UUID("66666666-bbbb-bbbb-bbbb-222222222222"),
            owner_id=MARC_ID,
            account_id=None,
            asset_class="NPS",
            instrument_name="NPS – Tier I (Aggressive E75)",
            isin=None,
            units=None,
            nav_paise=None,
            purchase_price_paise=8_00_00_000_00,    # ₹8,00,000 contributions
            current_value_paise=9_80_00_000_00,     # ₹9,80,000 current
            valuation_date=date(2026, 4, 15),
            metadata_={"pran": "110XXXX0001", "fund_manager": "SBI Pension Funds"},
        ),
    ]


# ---------------------------------------------------------------------------
# Marc Antony — Tax Data
# ---------------------------------------------------------------------------

def build_marc_tax_data() -> list[TaxData]:
    return [
        TaxData(
            id=uuid.UUID("11111111-cccc-cccc-cccc-222222222222"),
            owner_id=MARC_ID,
            fiscal_year="2023-24",
            gross_income_paise=3_20_00_000_00,   # ₹32,00,000
            taxable_income_paise=2_85_00_000_00,  # ₹28,50,000 (after 80C/80D)
            tax_paid_paise=55_00_000_00,          # ₹5,50,000
            tds_paise=40_00_000_00,               # ₹4,00,000
            itr_filed=True,
            raw_data={"itr_form": "ITR-2", "assessment_year": "2024-25",
                      "refund_paise": 0, "stcg_paise": 12_00_000_00, "ltcg_paise": 8_00_000_00},
        ),
        TaxData(
            id=uuid.UUID("22222222-cccc-cccc-cccc-222222222222"),
            owner_id=MARC_ID,
            fiscal_year="2024-25",
            gross_income_paise=3_60_00_000_00,   # ₹36,00,000
            taxable_income_paise=3_20_00_000_00,  # ₹32,00,000
            tax_paid_paise=68_00_000_00,          # ₹6,80,000
            tds_paise=50_00_000_00,               # ₹5,00,000
            itr_filed=True,
            raw_data={"itr_form": "ITR-2", "assessment_year": "2025-26",
                      "refund_paise": 0, "stcg_paise": 18_00_000_00, "ltcg_paise": 12_00_000_00},
        ),
        TaxData(
            id=uuid.UUID("33333333-cccc-cccc-cccc-222222222222"),
            owner_id=MARC_ID,
            fiscal_year="2025-26",
            gross_income_paise=4_20_00_000_00,   # ₹42,00,000 (estimated)
            taxable_income_paise=3_75_00_000_00,
            tax_paid_paise=0,
            tds_paise=60_00_000_00,
            itr_filed=False,
            raw_data={"note": "FY in progress – estimated from salary + trading income"},
        ),
    ]


# ---------------------------------------------------------------------------
# Cleopatra — Owner + Accounts
# ---------------------------------------------------------------------------

def build_cleo_owner() -> Owner:
    return Owner(
        id=CLEO_ID,
        name="Cleopatra",
        is_admin=False,
        pin_hash=hash_pin(CLEO_PIN),
    )


def build_cleo_accounts() -> list[Account]:
    return [
        Account(
            id=CLEO_ICICI_SAV_ID,
            owner_id=CLEO_ID,
            account_type="SAVINGS",
            institution="ICICI Bank",
            nickname="ICICI Primary Savings",
            is_active=True,
        ),
        Account(
            id=CLEO_KOTAK_SAV_ID,
            owner_id=CLEO_ID,
            account_type="SAVINGS",
            institution="Kotak Mahindra Bank",
            nickname="Kotak 811 Savings",
            is_active=True,
        ),
        Account(
            id=CLEO_HDFC_CC_ID,
            owner_id=CLEO_ID,
            account_type="CREDIT_CARD",
            institution="HDFC Bank",
            nickname="HDFC Regalia CC",
            is_active=True,
        ),
        Account(
            id=CLEO_GROWW_MF_ID,
            owner_id=CLEO_ID,
            account_type="MF_FOLIO",
            institution="Groww",
            nickname="Groww MF Folio",
            is_active=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Cleopatra — Profile
# ---------------------------------------------------------------------------

def build_cleo_profile() -> UserProfile:
    return UserProfile(
        owner_id=CLEO_ID,
        risk_appetite="moderate",
        age=35,
        is_family_scope=True,
        total_monthly_income_paise=18_00_000_00,   # ₹1,80,000/month
        income_sources_json=[
            {"label": "Salary – MedArc Pharma", "monthly_paise": 16_00_000_00},
            {"label": "Rental Income", "monthly_paise": 2_00_000_00},
        ],
        emis_json=[
            {"label": "Education Loan – SBI", "monthly_paise": 40_000_00},
        ],
        preferences={"theme": "light", "currency_display": "short"},
    )


# ---------------------------------------------------------------------------
# Cleopatra — Goals
# ---------------------------------------------------------------------------

def build_cleo_goals() -> list[FinancialGoal]:
    return [
        FinancialGoal(
            id=uuid.UUID("11111111-aaaa-aaaa-aaaa-333333333333"),
            owner_id=CLEO_ID,
            goal_name="Children Education Fund",
            target_amount_paise=50_00_00_000_00,    # ₹50,00,000
            current_amount_paise=12_00_00_000_00,   # ₹12,00,000 — 24%
            target_date=date(2035, 3, 31),
            category="EDUCATION",
            is_active=True,
        ),
        FinancialGoal(
            id=uuid.UUID("22222222-aaaa-aaaa-aaaa-333333333333"),
            owner_id=CLEO_ID,
            goal_name="PPF Maturity Target",
            target_amount_paise=20_00_00_000_00,    # ₹20,00,000
            current_amount_paise=9_50_00_000_00,    # ₹9,50,000 — 47.5%
            target_date=date(2030, 3, 31),
            category="SAVINGS",
            is_active=True,
        ),
        FinancialGoal(
            id=uuid.UUID("33333333-aaaa-aaaa-aaaa-333333333333"),
            owner_id=CLEO_ID,
            goal_name="Retirement Corpus",
            target_amount_paise=3_00_00_00_000_00,  # ₹3,00,00,000
            current_amount_paise=45_00_00_000_00,   # ₹45,00,000 — 15%
            target_date=date(2040, 3, 31),
            category="INVESTMENT",
            is_active=True,
        ),
        FinancialGoal(
            id=uuid.UUID("44444444-aaaa-aaaa-aaaa-333333333333"),
            owner_id=CLEO_ID,
            goal_name="Emergency Fund",
            target_amount_paise=10_00_00_000_00,    # ₹10,00,000
            current_amount_paise=10_00_00_000_00,   # 100% — complete
            target_date=date(2024, 12, 31),
            category="SAVINGS",
            is_active=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Cleopatra — Transactions (24 months: Apr 2024 – Apr 2026)
# ---------------------------------------------------------------------------

def build_cleo_transactions() -> list[Transaction]:
    txns: list[Transaction] = []

    months = [
        (date(2024, m, 1) if m >= 4 else date(2025, m, 1))
        for m in list(range(4, 13)) + list(range(1, 4))
    ]
    months += [
        (date(2025, m, 1) if m >= 4 else date(2026, m, 1))
        for m in list(range(4, 13)) + list(range(1, 4))
    ]
    months += [date(2026, 4, 1)]

    def mo(d: date) -> str:
        return d.strftime("%Y%m")

    for d in months:
        fy = _fy(d)
        m = mo(d)

        # Salary
        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-sal-{m}",
            account_id=CLEO_ICICI_SAV_ID, txn_date=date(d.year, d.month, 1),
            amount_paise=16_00_000_00, txn_type="CREDIT", category="SALARY",
            description=f"MedArc Pharma Salary {d.strftime('%b %Y')}", merchant="MedArc Pharma",
            fiscal_year=fy))

        # Rental income
        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-rent-inc-{m}",
            account_id=CLEO_KOTAK_SAV_ID, txn_date=date(d.year, d.month, 5),
            amount_paise=2_00_000_00, txn_type="CREDIT", category="INTEREST",
            description=f"Rental income – Koramangala flat {d.strftime('%b %Y')}", merchant="Tenant",
            fiscal_year=fy))

        # Education loan EMI
        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-edu-emi-{m}",
            account_id=CLEO_ICICI_SAV_ID, txn_date=date(d.year, d.month, 5),
            amount_paise=40_000_00, txn_type="DEBIT", category="EMI",
            description=f"SBI Education Loan EMI {d.strftime('%b %Y')}", merchant="SBI",
            fiscal_year=fy))

        # Balanced SIPs (moderate profile — balanced equity + debt)
        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-sip-balanced-{m}",
            account_id=CLEO_ICICI_SAV_ID, txn_date=date(d.year, d.month, 10),
            amount_paise=1_00_000_00, txn_type="DEBIT", category="INVESTMENT",
            description=f"Groww SIP – HDFC Balanced Advantage {d.strftime('%b %Y')}", merchant="Groww",
            fiscal_year=fy))

        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-sip-ppf-{m}",
            account_id=CLEO_KOTAK_SAV_ID, txn_date=date(d.year, d.month, 12),
            amount_paise=50_000_00, txn_type="DEBIT", category="INVESTMENT",
            description=f"PPF deposit {d.strftime('%b %Y')}", merchant="Post Office",
            fiscal_year=fy))

        # Groceries
        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-groc-{m}",
            account_id=CLEO_HDFC_CC_ID, txn_date=date(d.year, d.month, 8),
            amount_paise=55_000_00, txn_type="DEBIT", category="GROCERIES",
            description=f"BigBasket + D-Mart {d.strftime('%b %Y')}", merchant="BigBasket",
            fiscal_year=fy))

        # Dining
        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-dining-{m}",
            account_id=CLEO_HDFC_CC_ID, txn_date=date(d.year, d.month, 14),
            amount_paise=30_000_00, txn_type="DEBIT", category="DINING",
            description=f"Dining out {d.strftime('%b %Y')}", merchant="Swiggy",
            fiscal_year=fy))

        # Utilities
        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-utils-{m}",
            account_id=CLEO_ICICI_SAV_ID, txn_date=date(d.year, d.month, 12),
            amount_paise=8_000_00, txn_type="DEBIT", category="UTILITIES",
            description=f"BESCOM + Jio {d.strftime('%b %Y')}", merchant="BESCOM",
            fiscal_year=fy))

        # Healthcare (moderate profile — regular health spend)
        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-health-{m}",
            account_id=CLEO_HDFC_CC_ID, txn_date=date(d.year, d.month, 16),
            amount_paise=15_000_00, txn_type="DEBIT", category="HEALTHCARE",
            description=f"Apollo + Pharmacy {d.strftime('%b %Y')}", merchant="Apollo",
            fiscal_year=fy))

        # Transport
        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-transport-{m}",
            account_id=CLEO_HDFC_CC_ID, txn_date=date(d.year, d.month, 18),
            amount_paise=18_000_00, txn_type="DEBIT", category="TRANSPORT",
            description=f"Ola + Metro {d.strftime('%b %Y')}", merchant="Ola",
            fiscal_year=fy))

        # Education (child)
        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-edu-{m}",
            account_id=CLEO_HDFC_CC_ID, txn_date=date(d.year, d.month, 7),
            amount_paise=25_000_00, txn_type="DEBIT", category="EDUCATION",
            description=f"School fees {d.strftime('%b %Y')}", merchant="Delhi Public School",
            fiscal_year=fy))

        # Insurance — annual (April)
        if d.month == 4:
            txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-insurance-{m}",
                account_id=CLEO_ICICI_SAV_ID, txn_date=date(d.year, d.month, 16),
                amount_paise=85_000_00, txn_type="DEBIT", category="INSURANCE",
                description=f"ICICI Prudential Life + Health Premium {d.year}", merchant="ICICI Prudential",
                fiscal_year=fy))

        # Savings interest
        txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-interest-{m}",
            account_id=CLEO_KOTAK_SAV_ID, txn_date=date(d.year, d.month, 28) if d.month != 2 else date(d.year, 2, 28),
            amount_paise=28_000_00, txn_type="CREDIT", category="INTEREST",
            description=f"Kotak savings interest {d.strftime('%b %Y')}", merchant="Kotak Bank",
            fiscal_year=fy))

        # Advance tax (quarterly)
        if d.month in (6, 9, 12, 3):
            txns.append(_txn(owner_id=CLEO_ID, seed=f"cleo-advtax-{m}",
                account_id=CLEO_ICICI_SAV_ID, txn_date=date(d.year, d.month, 15),
                amount_paise=80_000_00, txn_type="DEBIT", category="TAX",
                description=f"Advance tax payment {d.strftime('%b %Y')}", merchant="Income Tax Dept",
                fiscal_year=fy))

    return txns


# ---------------------------------------------------------------------------
# Cleopatra — Holdings
# ---------------------------------------------------------------------------

def build_cleo_holdings() -> list[Holding]:
    return [
        Holding(
            id=uuid.UUID("11111111-bbbb-bbbb-bbbb-333333333333"),
            owner_id=CLEO_ID,
            account_id=CLEO_GROWW_MF_ID,
            asset_class="MUTUAL_FUND",
            instrument_name="HDFC Balanced Advantage Fund – Direct Growth",
            isin="INF179K01WT1",
            units=2200.000,
            nav_paise=6_250_00,              # ₹62.50 NAV
            purchase_price_paise=10_00_00_000_00,   # ₹10,00,000 cost
            current_value_paise=13_75_00_000_00,    # ₹13,75,000
            valuation_date=date(2026, 4, 15),
            metadata_={"folio": "CL-GROWW-001"},
        ),
        Holding(
            id=uuid.UUID("22222222-bbbb-bbbb-bbbb-333333333333"),
            owner_id=CLEO_ID,
            account_id=CLEO_GROWW_MF_ID,
            asset_class="MUTUAL_FUND",
            instrument_name="Mirae Asset Large & Midcap Fund – Direct Growth",
            isin="INF769K01EG7",
            units=850.000,
            nav_paise=13_500_00,             # ₹135 NAV
            purchase_price_paise=8_00_00_000_00,    # ₹8,00,000 cost
            current_value_paise=11_47_50_000_00,    # ₹11,47,500
            valuation_date=date(2026, 4, 15),
            metadata_={"folio": "CL-GROWW-002"},
        ),
        Holding(
            id=uuid.UUID("33333333-bbbb-bbbb-bbbb-333333333333"),
            owner_id=CLEO_ID,
            account_id=None,
            asset_class="PPF",
            instrument_name="PPF Account – Post Office",
            isin=None,
            units=None,
            nav_paise=None,
            purchase_price_paise=8_50_00_000_00,    # ₹8,50,000 contributions
            current_value_paise=9_50_00_000_00,     # ₹9,50,000 with interest
            valuation_date=date(2026, 4, 15),
            metadata_={"account_no": "PPF-CLEO-001", "maturity_year": 2030, "rate_pct": 7.1},
        ),
        Holding(
            id=uuid.UUID("44444444-bbbb-bbbb-bbbb-333333333333"),
            owner_id=CLEO_ID,
            account_id=None,
            asset_class="INSURANCE",
            instrument_name="ICICI Prudential Life – Savings Plan",
            isin=None,
            units=None,
            nav_paise=None,
            purchase_price_paise=5_00_00_000_00,    # ₹5,00,000 premiums paid
            current_value_paise=5_60_00_000_00,     # ₹5,60,000 surrender value
            valuation_date=date(2026, 4, 15),
            metadata_={"policy_no": "ICICI-CLEO-2019", "maturity_year": 2029},
        ),
        Holding(
            id=uuid.UUID("55555555-bbbb-bbbb-bbbb-333333333333"),
            owner_id=CLEO_ID,
            account_id=CLEO_KOTAK_SAV_ID,
            asset_class="FD",
            instrument_name="Kotak Bank FD – 18 months",
            isin=None,
            units=None,
            nav_paise=None,
            purchase_price_paise=3_00_00_000_00,    # ₹3,00,000
            current_value_paise=3_34_50_000_00,     # ₹3,34,500 (7.5% p.a.)
            valuation_date=date(2026, 4, 15),
            metadata_={"maturity_date": "2026-09-30", "rate_pct": 7.5},
        ),
        Holding(
            id=uuid.UUID("66666666-bbbb-bbbb-bbbb-333333333333"),
            owner_id=CLEO_ID,
            account_id=CLEO_GROWW_MF_ID,
            asset_class="MUTUAL_FUND",
            instrument_name="ICICI Prudential Liquid Fund – Direct Growth",
            isin="INF109K01Z04",
            units=450.000,
            nav_paise=3_850_00,              # ₹38.50 NAV
            purchase_price_paise=1_50_00_000_00,    # ₹1,50,000 cost
            current_value_paise=1_73_25_000_00,     # ₹1,73,250
            valuation_date=date(2026, 4, 15),
            metadata_={"folio": "CL-GROWW-003", "category": "liquid"},
        ),
    ]


# ---------------------------------------------------------------------------
# Cleopatra — Tax Data
# ---------------------------------------------------------------------------

def build_cleo_tax_data() -> list[TaxData]:
    return [
        TaxData(
            id=uuid.UUID("11111111-cccc-cccc-cccc-333333333333"),
            owner_id=CLEO_ID,
            fiscal_year="2023-24",
            gross_income_paise=2_10_00_000_00,   # ₹21,00,000
            taxable_income_paise=1_80_00_000_00,  # ₹18,00,000 (after 80C/80D)
            tax_paid_paise=26_00_000_00,          # ₹2,60,000
            tds_paise=22_00_000_00,               # ₹2,20,000
            itr_filed=True,
            raw_data={"itr_form": "ITR-1", "assessment_year": "2024-25",
                      "refund_paise": 2_00_000, "rental_income_paise": 24_00_000_00},
        ),
        TaxData(
            id=uuid.UUID("22222222-cccc-cccc-cccc-333333333333"),
            owner_id=CLEO_ID,
            fiscal_year="2024-25",
            gross_income_paise=2_40_00_000_00,   # ₹24,00,000
            taxable_income_paise=2_05_00_000_00,  # ₹20,50,000
            tax_paid_paise=35_00_000_00,          # ₹3,50,000
            tds_paise=28_00_000_00,               # ₹2,80,000
            itr_filed=True,
            raw_data={"itr_form": "ITR-1", "assessment_year": "2025-26",
                      "refund_paise": 0, "rental_income_paise": 24_00_000_00},
        ),
        TaxData(
            id=uuid.UUID("33333333-cccc-cccc-cccc-333333333333"),
            owner_id=CLEO_ID,
            fiscal_year="2025-26",
            gross_income_paise=2_64_00_000_00,   # ₹26,40,000 (estimated)
            taxable_income_paise=2_25_00_000_00,
            tax_paid_paise=0,
            tds_paise=32_00_000_00,
            itr_filed=False,
            raw_data={"note": "FY in progress – estimated from salary + rental income"},
        ),
    ]


# ---------------------------------------------------------------------------
# Family Memberships
# ---------------------------------------------------------------------------

def build_family_memberships() -> list[FamilyMembership]:
    return [
        FamilyMembership(
            id=uuid.UUID("ffffffff-aaaa-aaaa-aaaa-222222222222"),
            family_id=MARC_ID,   # Marc's ID is the family group key
            owner_id=MARC_ID,
            role="PRIMARY",
        ),
        FamilyMembership(
            id=uuid.UUID("ffffffff-aaaa-aaaa-aaaa-333333333333"),
            family_id=MARC_ID,   # same family group
            owner_id=CLEO_ID,
            role="SPOUSE",
        ),
    ]


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

async def _upsert_owner(session, owner: Owner) -> None:
    existing = await session.get(Owner, owner.id)
    if existing:
        existing.name = owner.name
        existing.pin_hash = owner.pin_hash
        print(f"  Updated owner: {owner.name}")
    else:
        session.add(owner)
        print(f"  Created owner: {owner.name} ({owner.id})")


async def _upsert_accounts(session, accounts: list[Account]) -> None:
    for acc in accounts:
        if not await session.get(Account, acc.id):
            session.add(acc)
            print(f"    + Account: {acc.nickname} ({acc.account_type} @ {acc.institution})")


async def _upsert_profile(session, owner_id: uuid.UUID, profile: UserProfile) -> UserProfile:
    result = await session.execute(
        select(UserProfile).where(UserProfile.owner_id == owner_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.risk_appetite = profile.risk_appetite
        existing.age = profile.age
        existing.is_family_scope = profile.is_family_scope
        existing.total_monthly_income_paise = profile.total_monthly_income_paise
        existing.income_sources_json = profile.income_sources_json
        existing.emis_json = profile.emis_json
        existing.preferences = profile.preferences
        print(f"    Updated profile (risk={profile.risk_appetite})")
        return existing
    else:
        session.add(profile)
        await session.flush()
        print(f"    Created profile (risk={profile.risk_appetite})")
        return profile


async def _upsert_profile_scope(session, profile_id: uuid.UUID, owner_id: uuid.UUID, scope: str) -> None:
    result = await session.execute(
        select(UserProfileScope).where(
            UserProfileScope.profile_id == profile_id,
            UserProfileScope.owner_id == owner_id,
        )
    )
    if not result.scalar_one_or_none():
        session.add(UserProfileScope(profile_id=profile_id, owner_id=owner_id, scope=scope))
        print(f"    Created {scope} profile scope")


async def _upsert_goals(session, goals: list[FinancialGoal]) -> None:
    for goal in goals:
        existing = await session.get(FinancialGoal, goal.id)
        if existing:
            existing.goal_name = goal.goal_name
            existing.target_amount_paise = goal.target_amount_paise
            existing.current_amount_paise = goal.current_amount_paise
            existing.target_date = goal.target_date
            existing.category = goal.category
        else:
            session.add(goal)
            print(f"    + Goal: {goal.goal_name}")


async def _upsert_transactions(session, txns: list[Transaction], owner_name: str) -> None:
    count = 0
    for txn in txns:
        if not await session.get(Transaction, txn.id):
            session.add(txn)
            count += 1
    print(f"    Inserted {count} new transactions for {owner_name}")


async def _upsert_holdings(session, holdings: list[Holding]) -> None:
    for h in holdings:
        existing = await session.get(Holding, h.id)
        if existing:
            existing.current_value_paise = h.current_value_paise
            existing.nav_paise = h.nav_paise
            existing.valuation_date = h.valuation_date
        else:
            session.add(h)
            print(f"    + Holding: {h.instrument_name} ({h.asset_class})")


async def _upsert_tax_data(session, tax_records: list[TaxData]) -> None:
    for td in tax_records:
        existing = await session.get(TaxData, td.id)
        if not existing:
            r = await session.execute(
                select(TaxData).where(
                    TaxData.owner_id == td.owner_id,
                    TaxData.fiscal_year == td.fiscal_year,
                )
            )
            if not r.scalar_one_or_none():
                session.add(td)
                print(f"    + TaxData: FY {td.fiscal_year} (filed={td.itr_filed})")


async def _upsert_family_memberships(session, memberships: list[FamilyMembership]) -> None:
    for fm in memberships:
        existing = await session.get(FamilyMembership, fm.id)
        if not existing:
            r = await session.execute(
                select(FamilyMembership).where(
                    FamilyMembership.family_id == fm.family_id,
                    FamilyMembership.owner_id == fm.owner_id,
                )
            )
            if not r.scalar_one_or_none():
                session.add(fm)
                print(f"    + FamilyMembership: owner={fm.owner_id} role={fm.role}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():

            # ================================================================
            # MARC ANTONY
            # ================================================================
            print("\n=== Marc Antony (aggressive) ===")
            await _upsert_owner(session, build_marc_owner())
            await _upsert_accounts(session, build_marc_accounts())

            marc_profile = await _upsert_profile(session, MARC_ID, build_marc_profile())
            await _upsert_profile_scope(session, marc_profile.id, MARC_ID, "PRIMARY")

            await _upsert_goals(session, build_marc_goals())
            await _upsert_transactions(session, build_marc_transactions(), "Marc Antony")
            await _upsert_holdings(session, build_marc_holdings())
            await _upsert_tax_data(session, build_marc_tax_data())

            # ================================================================
            # CLEOPATRA
            # ================================================================
            print("\n=== Cleopatra (moderate) ===")
            await _upsert_owner(session, build_cleo_owner())
            await _upsert_accounts(session, build_cleo_accounts())

            cleo_profile = await _upsert_profile(session, CLEO_ID, build_cleo_profile())
            await _upsert_profile_scope(session, cleo_profile.id, CLEO_ID, "PRIMARY")
            # Grant Marc's profile SPOUSE scope over Cleopatra — must be after Cleopatra owner exists
            await _upsert_profile_scope(session, marc_profile.id, CLEO_ID, "SPOUSE")

            await _upsert_goals(session, build_cleo_goals())
            await _upsert_transactions(session, build_cleo_transactions(), "Cleopatra")
            await _upsert_holdings(session, build_cleo_holdings())
            await _upsert_tax_data(session, build_cleo_tax_data())

            # ================================================================
            # FAMILY MEMBERSHIP
            # ================================================================
            print("\n=== Family Membership ===")
            await _upsert_family_memberships(session, build_family_memberships())

    print("\n" + "=" * 60)
    print("Seed complete — Marc Antony & Cleopatra family")
    print("=" * 60)
    print(f"  Marc Antony  ID : {MARC_ID}  PIN: {MARC_PIN}")
    print(f"  Cleopatra    ID : {CLEO_ID}  PIN: {CLEO_PIN}")
    print(f"  Family group ID : {MARC_ID} (Marc is PRIMARY)")
    print("  Login: POST /auth/login  {{ owner_id, pin }}")


if __name__ == "__main__":
    asyncio.run(main())
