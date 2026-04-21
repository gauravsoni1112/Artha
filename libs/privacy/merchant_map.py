"""
Static merchant-name → functional-category mapping.

Rules:
- Matching is case-insensitive prefix/substring.
- Unknown merchants → "merchant_other".
- Categories are functional (debt_service_home_loan) not brand names,
  so the cloud reflector knows the shape without knowing the vendor.
"""

from __future__ import annotations

# Ordered longest-match first to avoid "HDFC" matching before "HDFC HOME LOAN".
MERCHANT_CATEGORIES: list[tuple[str, str]] = [
    # Debt service
    ("HOME LOAN", "debt_service_home_loan"),
    ("CAR LOAN", "debt_service_car_loan"),
    ("PERSONAL LOAN", "debt_service_personal_loan"),
    ("LOAN EMI", "debt_service_loan_emi"),
    ("CREDIT CARD", "debt_service_credit_card"),
    # Investments / insurance
    ("MUTUAL FUND", "investment_mutual_fund"),
    ("SIP", "investment_sip"),
    ("ZERODHA", "investment_brokerage"),
    ("GROWW", "investment_brokerage"),
    ("KUVERA", "investment_brokerage"),
    ("LIC", "insurance_life"),
    ("HDFC LIFE", "insurance_life"),
    ("MAX LIFE", "insurance_life"),
    ("ICICI PRU", "insurance_life"),
    ("STAR HEALTH", "insurance_health"),
    ("NIVA BUPA", "insurance_health"),
    # Food & delivery
    ("SWIGGY", "food_delivery"),
    ("ZOMATO", "food_delivery"),
    ("DUNZO", "food_delivery"),
    ("BLINKIT", "grocery_delivery"),
    ("ZEPTO", "grocery_delivery"),
    ("BIGBASKET", "grocery_delivery"),
    ("DMART", "grocery_retail"),
    # Transport
    ("UBER", "transport_cab"),
    ("OLA", "transport_cab"),
    ("RAPIDO", "transport_cab"),
    ("IRCTC", "transport_rail"),
    ("INDIGO", "transport_air"),
    ("AIR INDIA", "transport_air"),
    # Utilities & telecom
    ("BESCOM", "utility_electricity"),
    ("MSEDCL", "utility_electricity"),
    ("TATA POWER", "utility_electricity"),
    ("AIRTEL", "utility_telecom"),
    ("JIOFIBER", "utility_telecom"),
    ("BSNL", "utility_telecom"),
    ("BBMP", "utility_municipality"),
    # Education
    ("BYJUS", "education"),
    ("UNACADEMY", "education"),
    ("COURSERA", "education"),
    # Entertainment / subscriptions
    ("NETFLIX", "subscription_entertainment"),
    ("HOTSTAR", "subscription_entertainment"),
    ("AMAZON PRIME", "subscription_entertainment"),
    ("SPOTIFY", "subscription_music"),
    ("YOUTUBE PREMIUM", "subscription_entertainment"),
    # E-commerce
    ("AMAZON", "ecommerce"),
    ("FLIPKART", "ecommerce"),
    ("MYNTRA", "ecommerce_fashion"),
    # Healthcare
    ("APOLLO", "healthcare"),
    ("PRACTO", "healthcare"),
    ("MEDPLUS", "healthcare_pharmacy"),
    # Fuel
    ("BPCL", "fuel"),
    ("HPCL", "fuel"),
    ("INDIAN OIL", "fuel"),
    ("IOCL", "fuel"),
    # Rent / housing
    ("RENT", "housing_rent"),
    ("NOBROKER", "housing_rent"),
]


MERCHANT_CATEGORY_VALUES: frozenset[str] = frozenset(cat for _, cat in MERCHANT_CATEGORIES)


def merchant_to_category(name: str) -> str:
    """Return functional category for a merchant name, or 'merchant_other'."""
    upper = name.upper()
    for fragment, category in MERCHANT_CATEGORIES:
        if fragment in upper:
            return category
    return "merchant_other"
