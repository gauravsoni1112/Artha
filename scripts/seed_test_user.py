"""
Seed dummy data for the Test User (owner_id = 11111111-1111-1111-1111-111111111111).

Populates:
  - Owner (PIN: 1234)
  - 3 Accounts: Savings, Credit Card, MF Folio
  - UserProfile (income, EMIs, risk appetite)
  - 4 Financial Goals (varying progress)
  - Transactions: April 2026 (current month) + 2 prior months for history
  - Holdings: Mutual Funds, Equity, FD
  - TaxData: FY 2024-25 and 2025-26

Run from repo root:
    python scripts/seed_test_user.py
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Ensure the project root is importable
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import AsyncSessionLocal
from api.deps import hash_pin
from libs.schemas.db_models import (
    Account,
    FinancialGoal,
    Holding,
    Owner,
    TaxData,
    Transaction,
    UserProfile,
    UserProfileScope,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OWNER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
PIN = "1234"

# Stable UUIDs for accounts so re-runs are idempotent
SAVINGS_ACC_ID   = uuid.UUID("aaaaaaaa-1111-1111-1111-111111111111")
CC_ACC_ID        = uuid.UUID("bbbbbbbb-1111-1111-1111-111111111111")
MF_ACC_ID        = uuid.UUID("cccccccc-1111-1111-1111-111111111111")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source_hash(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _txn(
    *,
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
        id=uuid.uuid5(OWNER_ID, seed),
        owner_id=OWNER_ID,
        account_id=account_id,
        source_hash=_source_hash(seed),
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


# ---------------------------------------------------------------------------
# Data builders
# ---------------------------------------------------------------------------

def build_owner() -> Owner:
    return Owner(
        id=OWNER_ID,
        name="Gaurav Soni",
        is_admin=False,
        pin_hash=hash_pin(PIN),
    )


def build_accounts() -> list[Account]:
    return [
        Account(
            id=SAVINGS_ACC_ID,
            owner_id=OWNER_ID,
            account_type="SAVINGS",
            institution="HDFC Bank",
            nickname="HDFC Savings",
            is_active=True,
        ),
        Account(
            id=CC_ACC_ID,
            owner_id=OWNER_ID,
            account_type="CREDIT_CARD",
            institution="ICICI Bank",
            nickname="ICICI Coral CC",
            is_active=True,
        ),
        Account(
            id=MF_ACC_ID,
            owner_id=OWNER_ID,
            account_type="MF_FOLIO",
            institution="Zerodha Coin",
            nickname="Zerodha MF",
            is_active=True,
        ),
    ]


def build_profile() -> UserProfile:
    return UserProfile(
        owner_id=OWNER_ID,
        risk_appetite="moderate",
        age=32,
        is_family_scope=False,
        total_monthly_income_paise=15_00_000_00,  # ₹1,50,000/month
        income_sources_json=[
            {"label": "Salary – Acme Corp", "monthly_paise": 14_00_000_00},
            {"label": "Freelance", "monthly_paise": 1_00_000_00},
        ],
        emis_json=[
            {"label": "Home Loan – HDFC", "monthly_paise": 3_50_000_00},
            {"label": "Car Loan – Axis", "monthly_paise": 75_000_00},
        ],
        preferences={"theme": "system", "currency_display": "short"},
    )


def build_goals() -> list[FinancialGoal]:
    return [
        FinancialGoal(
            id=uuid.UUID("dddddddd-1111-1111-1111-111111111111"),
            owner_id=OWNER_ID,
            goal_name="Emergency Fund",
            target_amount_paise=6_00_00_000_00,   # ₹6,00,000
            current_amount_paise=4_20_00_000_00,  # ₹4,20,000 — 70%
            target_date=date(2026, 9, 30),
            category="SAVINGS",
            is_active=True,
        ),
        FinancialGoal(
            id=uuid.UUID("eeeeeeee-1111-1111-1111-111111111111"),
            owner_id=OWNER_ID,
            goal_name="Europe Trip",
            target_amount_paise=3_00_00_000_00,   # ₹3,00,000
            current_amount_paise=90_00_000_00,    # ₹90,000 — 30%
            target_date=date(2027, 6, 30),
            category="TRAVEL",
            is_active=True,
        ),
        FinancialGoal(
            id=uuid.UUID("ffffffff-1111-1111-1111-111111111111"),
            owner_id=OWNER_ID,
            goal_name="Home Down Payment",
            target_amount_paise=30_00_00_000_00,  # ₹30,00,000
            current_amount_paise=8_50_00_000_00,  # ₹8,50,000 — 28%
            target_date=date(2028, 3, 31),
            category="REAL_ESTATE",
            is_active=True,
        ),
        FinancialGoal(
            id=uuid.UUID("00000000-2222-2222-2222-111111111111"),
            owner_id=OWNER_ID,
            goal_name="New Laptop",
            target_amount_paise=1_50_00_000_00,   # ₹1,50,000
            current_amount_paise=1_50_00_000_00,  # 100% — complete
            target_date=date(2026, 4, 30),
            category="OTHER",
            is_active=True,
        ),
    ]


def build_transactions() -> list[Transaction]:
    txns: list[Transaction] = []

    # ---- April 2026 (current month, FY 2025-26) ----
    apr = [
        ("apr-sal-01",    SAVINGS_ACC_ID, date(2026, 4, 1),  14_00_000_00, "CREDIT", "SALARY",        "Acme Corp Salary Apr",         "Acme Corp"),
        ("apr-free-01",   SAVINGS_ACC_ID, date(2026, 4, 3),   1_00_000_00, "CREDIT", "OTHER",          "Freelance payment – Design",   None),
        ("apr-rent-01",   SAVINGS_ACC_ID, date(2026, 4, 5),   2_50_000_00, "DEBIT",  "RENT",           "Rent – Apr 2026",              "Landlord"),
        ("apr-loan-01",   SAVINGS_ACC_ID, date(2026, 4, 5),   3_50_000_00, "DEBIT",  "EMI",            "HDFC Home Loan EMI",           "HDFC Bank"),
        ("apr-car-01",    SAVINGS_ACC_ID, date(2026, 4, 6),      75_000_00, "DEBIT",  "EMI",            "Axis Car Loan EMI",            "Axis Bank"),
        ("apr-groc-01",   CC_ACC_ID,      date(2026, 4, 7),      42_000_00, "DEBIT",  "GROCERIES",      "BigBasket order",              "BigBasket"),
        ("apr-dine-01",   CC_ACC_ID,      date(2026, 4, 8),      18_500_00, "DEBIT",  "DINING",         "Dinner at Taj Bistro",         "Taj Bistro"),
        ("apr-trans-01",  CC_ACC_ID,      date(2026, 4, 9),       8_200_00, "DEBIT",  "TRANSPORT",      "Uber rides",                   "Uber"),
        ("apr-ott-01",    CC_ACC_ID,      date(2026, 4, 10),      1_499_00, "DEBIT",  "ENTERTAINMENT",  "Netflix subscription",         "Netflix"),
        ("apr-elec-01",   SAVINGS_ACC_ID, date(2026, 4, 10),      4_300_00, "DEBIT",  "UTILITIES",      "Electricity – BESCOM Apr",     "BESCOM"),
        ("apr-inv-01",    SAVINGS_ACC_ID, date(2026, 4, 11),  1_00_000_00, "DEBIT",  "INVESTMENT",     "Zerodha SIP – Nifty 50 Index", "Zerodha"),
        ("apr-inv-02",    SAVINGS_ACC_ID, date(2026, 4, 11),     50_000_00, "DEBIT",  "INVESTMENT",     "Zerodha SIP – Midcap 150",     "Zerodha"),
        ("apr-groc-02",   CC_ACC_ID,      date(2026, 4, 13),      21_300_00, "DEBIT",  "GROCERIES",      "Swiggy Instamart",             "Swiggy"),
        ("apr-health-01", CC_ACC_ID,      date(2026, 4, 14),       5_500_00, "DEBIT",  "HEALTHCARE",     "Apollo Pharmacy",              "Apollo"),
        ("apr-dine-02",   CC_ACC_ID,      date(2026, 4, 15),      12_400_00, "DEBIT",  "DINING",         "Zomato order",                 "Zomato"),
        ("apr-int-01",    SAVINGS_ACC_ID, date(2026, 4, 15),      32_000_00, "CREDIT", "INTEREST",       "Savings interest credit",      "HDFC Bank"),
        ("apr-ins-01",    SAVINGS_ACC_ID, date(2026, 4, 16),      45_000_00, "DEBIT",  "INSURANCE",      "LIC term premium",             "LIC"),
    ]

    # ---- March 2026 (FY 2025-26) ----
    mar = [
        ("mar-sal-01",   SAVINGS_ACC_ID, date(2026, 3, 1),  14_00_000_00, "CREDIT", "SALARY",        "Acme Corp Salary Mar",         "Acme Corp"),
        ("mar-free-01",  SAVINGS_ACC_ID, date(2026, 3, 4),     80_000_00, "CREDIT", "OTHER",          "Freelance payment",            None),
        ("mar-rent-01",  SAVINGS_ACC_ID, date(2026, 3, 5),   2_50_000_00, "DEBIT",  "RENT",           "Rent – Mar 2026",              "Landlord"),
        ("mar-loan-01",  SAVINGS_ACC_ID, date(2026, 3, 5),   3_50_000_00, "DEBIT",  "EMI",            "HDFC Home Loan EMI",           "HDFC Bank"),
        ("mar-car-01",   SAVINGS_ACC_ID, date(2026, 3, 6),      75_000_00, "DEBIT",  "EMI",            "Axis Car Loan EMI",            "Axis Bank"),
        ("mar-groc-01",  CC_ACC_ID,      date(2026, 3, 8),      55_000_00, "DEBIT",  "GROCERIES",      "BigBasket monthly order",      "BigBasket"),
        ("mar-dine-01",  CC_ACC_ID,      date(2026, 3, 11),     28_000_00, "DEBIT",  "DINING",         "Weekend dinners",              "Swiggy"),
        ("mar-trans-01", CC_ACC_ID,      date(2026, 3, 14),      9_000_00, "DEBIT",  "TRANSPORT",      "Rapido + Uber",                "Uber"),
        ("mar-inv-01",   SAVINGS_ACC_ID, date(2026, 3, 11),  1_00_000_00, "DEBIT",  "INVESTMENT",     "Zerodha SIP – Nifty 50",       "Zerodha"),
        ("mar-inv-02",   SAVINGS_ACC_ID, date(2026, 3, 11),     50_000_00, "DEBIT",  "INVESTMENT",     "Zerodha SIP – Midcap 150",     "Zerodha"),
        ("mar-elec-01",  SAVINGS_ACC_ID, date(2026, 3, 12),      4_100_00, "DEBIT",  "UTILITIES",      "Electricity – BESCOM Mar",     "BESCOM"),
        ("mar-edu-01",   CC_ACC_ID,      date(2026, 3, 20),     12_000_00, "DEBIT",  "EDUCATION",      "Coursera annual plan",         "Coursera"),
        ("mar-int-01",   SAVINGS_ACC_ID, date(2026, 3, 31),     32_000_00, "CREDIT", "INTEREST",       "Savings interest credit",      "HDFC Bank"),
    ]

    # ---- February 2026 (FY 2025-26) ----
    feb = [
        ("feb-sal-01",   SAVINGS_ACC_ID, date(2026, 2, 1),  14_00_000_00, "CREDIT", "SALARY",        "Acme Corp Salary Feb",         "Acme Corp"),
        ("feb-rent-01",  SAVINGS_ACC_ID, date(2026, 2, 5),   2_50_000_00, "DEBIT",  "RENT",           "Rent – Feb 2026",              "Landlord"),
        ("feb-loan-01",  SAVINGS_ACC_ID, date(2026, 2, 5),   3_50_000_00, "DEBIT",  "EMI",            "HDFC Home Loan EMI",           "HDFC Bank"),
        ("feb-car-01",   SAVINGS_ACC_ID, date(2026, 2, 6),      75_000_00, "DEBIT",  "EMI",            "Axis Car Loan EMI",            "Axis Bank"),
        ("feb-groc-01",  CC_ACC_ID,      date(2026, 2, 8),      48_000_00, "DEBIT",  "GROCERIES",      "Zepto + BigBasket",            "BigBasket"),
        ("feb-dine-01",  CC_ACC_ID,      date(2026, 2, 14),     35_000_00, "DEBIT",  "DINING",         "Valentine's dinner",           "Restaurant"),
        ("feb-health-01",CC_ACC_ID,      date(2026, 2, 18),     22_000_00, "DEBIT",  "HEALTHCARE",     "Dentist consultation",         "Apollo"),
        ("feb-inv-01",   SAVINGS_ACC_ID, date(2026, 2, 11),  1_00_000_00, "DEBIT",  "INVESTMENT",     "Zerodha SIP – Nifty 50",       "Zerodha"),
        ("feb-inv-02",   SAVINGS_ACC_ID, date(2026, 2, 11),     50_000_00, "DEBIT",  "INVESTMENT",     "Zerodha SIP – Midcap 150",     "Zerodha"),
        ("feb-elec-01",  SAVINGS_ACC_ID, date(2026, 2, 12),      3_800_00, "DEBIT",  "UTILITIES",      "Electricity – BESCOM Feb",     "BESCOM"),
        ("feb-int-01",   SAVINGS_ACC_ID, date(2026, 2, 28),     32_000_00, "CREDIT", "INTEREST",       "Savings interest credit",      "HDFC Bank"),
        ("feb-div-01",   SAVINGS_ACC_ID, date(2026, 2, 20),     15_000_00, "CREDIT", "DIVIDEND",       "Infosys dividend",             "Infosys"),
    ]

    for row in apr:
        seed, acc, dt, amt, tt, cat, desc, merch = row
        txns.append(_txn(seed=seed, account_id=acc, txn_date=dt, amount_paise=amt,
                         txn_type=tt, category=cat, description=desc, merchant=merch,
                         fiscal_year="2025-26"))
    for row in mar:
        seed, acc, dt, amt, tt, cat, desc, merch = row
        txns.append(_txn(seed=seed, account_id=acc, txn_date=dt, amount_paise=amt,
                         txn_type=tt, category=cat, description=desc, merchant=merch,
                         fiscal_year="2025-26"))
    for row in feb:
        seed, acc, dt, amt, tt, cat, desc, merch = row
        txns.append(_txn(seed=seed, account_id=acc, txn_date=dt, amount_paise=amt,
                         txn_type=tt, category=cat, description=desc, merchant=merch,
                         fiscal_year="2025-26"))

    return txns


def build_holdings() -> list[Holding]:
    return [
        Holding(
            id=uuid.UUID("11111111-3333-3333-3333-111111111111"),
            owner_id=OWNER_ID,
            account_id=MF_ACC_ID,
            asset_class="MUTUAL_FUND",
            instrument_name="Nifty 50 Index Fund – Direct Growth",
            isin="INF204K01I28",
            units=245.832,
            nav_paise=8_452_00,           # ₹8,452 NAV
            purchase_price_paise=6_100_00_00,  # ₹61,000 cost
            current_value_paise=20_77_800_00,  # ₹2,07,780
            valuation_date=date(2026, 4, 15),
            metadata_={"folio": "123456789"},
        ),
        Holding(
            id=uuid.UUID("22222222-3333-3333-3333-111111111111"),
            owner_id=OWNER_ID,
            account_id=MF_ACC_ID,
            asset_class="MUTUAL_FUND",
            instrument_name="Parag Parikh Flexi Cap Fund – Direct Growth",
            isin="INF879O01019",
            units=120.000,
            nav_paise=9_812_00,
            purchase_price_paise=9_00_000_00,  # ₹90,000 cost
            current_value_paise=11_77_440_00,  # ₹1,17,744
            valuation_date=date(2026, 4, 15),
            metadata_={"folio": "987654321"},
        ),
        Holding(
            id=uuid.UUID("33333333-3333-3333-3333-111111111111"),
            owner_id=OWNER_ID,
            account_id=MF_ACC_ID,
            asset_class="MUTUAL_FUND",
            instrument_name="Mirae Asset Midcap 150 ETF",
            isin="INF769K01DQ0",
            units=85.500,
            nav_paise=4_230_00,
            purchase_price_paise=3_00_000_00,
            current_value_paise=3_61_665_00,
            valuation_date=date(2026, 4, 15),
            metadata_={"folio": "555666777"},
        ),
        Holding(
            id=uuid.UUID("44444444-3333-3333-3333-111111111111"),
            owner_id=OWNER_ID,
            account_id=SAVINGS_ACC_ID,
            asset_class="FD",
            instrument_name="HDFC Bank FD – 12 months",
            isin=None,
            units=None,
            nav_paise=None,
            purchase_price_paise=5_00_00_000_00,   # ₹5,00,000
            current_value_paise=5_35_00_000_00,    # ₹5,35,000 (maturity)
            valuation_date=date(2026, 4, 15),
            metadata_={"maturity_date": "2026-10-14", "rate_pct": 7.0},
        ),
        Holding(
            id=uuid.UUID("55555555-3333-3333-3333-111111111111"),
            owner_id=OWNER_ID,
            account_id=None,
            asset_class="EQUITY",
            instrument_name="Infosys Ltd",
            isin="INE009A01021",
            units=50.0,
            nav_paise=1_89_000_00,       # ₹1,890 per share
            purchase_price_paise=7_50_000_00,  # ₹75,000 cost basis (50 @ ₹1,500)
            current_value_paise=9_45_000_00,   # ₹94,500 current
            valuation_date=date(2026, 4, 15),
            metadata_={"broker": "Zerodha", "demat_account": "XXXX123"},
        ),
    ]


def build_tax_data() -> list[TaxData]:
    return [
        TaxData(
            id=uuid.UUID("66666666-4444-4444-4444-111111111111"),
            owner_id=OWNER_ID,
            fiscal_year="2024-25",
            gross_income_paise=1_60_00_000_00,   # ₹16,00,000
            taxable_income_paise=1_45_00_000_00,  # ₹14,50,000
            tax_paid_paise=17_50_000_00,          # ₹1,75,000
            tds_paise=15_00_000_00,               # ₹1,50,000
            itr_filed=True,
            raw_data={"itr_form": "ITR-1", "assessment_year": "2025-26", "refund_paise": 0},
        ),
        TaxData(
            id=uuid.UUID("77777777-4444-4444-4444-111111111111"),
            owner_id=OWNER_ID,
            fiscal_year="2025-26",
            gross_income_paise=1_80_00_000_00,   # ₹18,00,000 (estimated)
            taxable_income_paise=1_62_00_000_00,
            tax_paid_paise=0,
            tds_paise=18_00_000_00,
            itr_filed=False,
            raw_data={"note": "FY in progress – estimated from profile income"},
        ),
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # ---- Owner ----
            existing = await session.get(Owner, OWNER_ID)
            if existing:
                print(f"Owner {OWNER_ID} already exists — updating pin_hash and name")
                existing.name = "Gaurav Soni"
                existing.pin_hash = hash_pin(PIN)
            else:
                session.add(build_owner())
                print(f"Created owner {OWNER_ID}")

            # ---- Accounts (upsert by id) ----
            for acc in build_accounts():
                existing_acc = await session.get(Account, acc.id)
                if not existing_acc:
                    session.add(acc)
                    print(f"  Created account: {acc.nickname}")

            # ---- UserProfile ----
            result = await session.execute(
                select(UserProfile).where(UserProfile.owner_id == OWNER_ID)
            )
            prof = result.scalar_one_or_none()
            new_prof = build_profile()
            if prof:
                prof.risk_appetite = new_prof.risk_appetite
                prof.age = new_prof.age
                prof.total_monthly_income_paise = new_prof.total_monthly_income_paise
                prof.income_sources_json = new_prof.income_sources_json
                prof.emis_json = new_prof.emis_json
                prof.preferences = new_prof.preferences
                print("  Updated user profile")
            else:
                session.add(new_prof)
                await session.flush()   # get profile.id before scope insert
                prof = new_prof
                print("  Created user profile")

            # ---- UserProfileScope (PRIMARY self-scope) ----
            scope_result = await session.execute(
                select(UserProfileScope).where(UserProfileScope.profile_id == prof.id)
            )
            if not scope_result.scalar_one_or_none():
                session.add(UserProfileScope(
                    profile_id=prof.id,
                    owner_id=OWNER_ID,
                    scope="PRIMARY",
                ))
                print("  Created PRIMARY profile scope")

            # ---- Goals ----
            for goal in build_goals():
                existing_goal = await session.get(FinancialGoal, goal.id)
                if existing_goal:
                    existing_goal.goal_name = goal.goal_name
                    existing_goal.target_amount_paise = goal.target_amount_paise
                    existing_goal.current_amount_paise = goal.current_amount_paise
                    existing_goal.target_date = goal.target_date
                    existing_goal.category = goal.category
                    existing_goal.is_active = goal.is_active
                else:
                    session.add(goal)
                    print(f"  Created goal: {goal.goal_name}")

            # ---- Transactions ----
            txn_count = 0
            for txn in build_transactions():
                existing_txn = await session.get(Transaction, txn.id)
                if not existing_txn:
                    session.add(txn)
                    txn_count += 1
            print(f"  Inserted {txn_count} new transactions")

            # ---- Holdings ----
            for h in build_holdings():
                existing_h = await session.get(Holding, h.id)
                if existing_h:
                    existing_h.current_value_paise = h.current_value_paise
                    existing_h.nav_paise = h.nav_paise
                    existing_h.valuation_date = h.valuation_date
                else:
                    session.add(h)
                    print(f"  Created holding: {h.instrument_name}")

            # ---- Tax Data ----
            for td in build_tax_data():
                existing_td = await session.get(TaxData, td.id)
                if not existing_td:
                    # Check unique constraint (owner_id, fiscal_year) first
                    r = await session.execute(
                        select(TaxData).where(
                            TaxData.owner_id == OWNER_ID,
                            TaxData.fiscal_year == td.fiscal_year,
                        )
                    )
                    if not r.scalar_one_or_none():
                        session.add(td)
                        print(f"  Created tax data: FY {td.fiscal_year}")

    print("\nSeed complete.")
    print(f"  Owner ID : {OWNER_ID}")
    print(f"  PIN      : {PIN}")
    print("  Login at: POST /auth/login  {owner_id, pin}")


if __name__ == "__main__":
    asyncio.run(main())
