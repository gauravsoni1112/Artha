"""
Category mapper — keyword-based transaction categorisation.

Maps normalised description strings to TransactionCategory enums.
Matching is case-insensitive, longest-match wins.
"""

from __future__ import annotations

import re
from libs.schemas.enums import TransactionCategory

# keyword → category (checked in order; first match wins)
# Longer / more-specific patterns should come before generic ones.
_RULES: list[tuple[re.Pattern, str]] = [
    # Salary / income
    (re.compile(r"\b(salary|sal|payroll|stipend|ctc)\b", re.I), TransactionCategory.SALARY),
    (re.compile(r"\b(dividend|div payout)\b", re.I), TransactionCategory.DIVIDEND),
    (re.compile(r"\b(interest|int credit|savings interest)\b", re.I), TransactionCategory.INTEREST),

    # Housing / utilities
    (re.compile(r"\b(rent|house rent|hrental)\b", re.I), TransactionCategory.RENT),
    (re.compile(r"\b(electricity|bescom|tata power|msedcl|bses|cesc|reliance energy|torrent power)\b", re.I), TransactionCategory.UTILITIES),
    (re.compile(r"\b(water|gas|lpg|igl|mgl|indraprastha gas)\b", re.I), TransactionCategory.UTILITIES),
    (re.compile(r"\b(broadband|internet|jio|airtel|bsnl|vodafone|vi )\b", re.I), TransactionCategory.UTILITIES),
    (re.compile(r"\b(mobile recharge|prepaid|postpaid)\b", re.I), TransactionCategory.UTILITIES),

    # Food & groceries
    (re.compile(r"\b(bigbasket|grofers|blinkit|zepto|swiggy instamart|jiomart|dmart|more supermarket)\b", re.I), TransactionCategory.GROCERIES),
    (re.compile(r"\b(grocery|supermarket|kirana|vegetables|veggies|veggie|sabzi|fruits|fruit|dairy)\b", re.I), TransactionCategory.GROCERIES),
    (re.compile(r"\b(zomato|swiggy|dominos|mcdonalds|kfc|subway|pizza|restaurant|cafe|chai|coffee)\b", re.I), TransactionCategory.DINING),

    # Transport
    (re.compile(r"\b(uber|ola|rapido|auto|rickshaw|cab|taxi)\b", re.I), TransactionCategory.TRANSPORT),
    (re.compile(r"\b(metro|local train|irctc|railways|bus|ksrtc|msrtc|dtc)\b", re.I), TransactionCategory.TRANSPORT),
    (re.compile(r"\b(petrol|diesel|fuel|hp|ioc|bharat petroleum|shell)\b", re.I), TransactionCategory.TRANSPORT),
    (re.compile(r"\b(fastag|toll)\b", re.I), TransactionCategory.TRANSPORT),

    # Entertainment
    (re.compile(r"\b(netflix|amazon prime|hotstar|disney|sony liv|zee5|youtube premium|spotify|apple music)\b", re.I), TransactionCategory.ENTERTAINMENT),
    (re.compile(r"\b(pvr|inox|cinepolis|bookmyshow|concert|event)\b", re.I), TransactionCategory.ENTERTAINMENT),

    # Healthcare
    (re.compile(r"\b(hospital|clinic|doctor|pharmacy|medplus|apollo pharmacy|1mg|netmeds|practo|lab test|diagnostic|medicines|medicine|medical)\b", re.I), TransactionCategory.HEALTHCARE),

    # Education
    (re.compile(r"\b(school fee|college fee|tuition|udemy|coursera|byju|unacademy|vedantu)\b", re.I), TransactionCategory.EDUCATION),

    # Investments
    (re.compile(r"\b(mutual fund|mf|sip|nfo|zerodha|groww|kuvera|coin|nps|ppf|elss|fd booking|fixed deposit)\b", re.I), TransactionCategory.INVESTMENT),
    (re.compile(r"\b(stock|equity|demat|nse|bse|ipo|shares)\b", re.I), TransactionCategory.INVESTMENT),

    # Insurance
    (re.compile(r"\b(lic|insurance|premium|policy|term plan|health insurance|ulip)\b", re.I), TransactionCategory.INSURANCE),

    # EMI / loans
    (re.compile(r"\b(emi|loan|home loan|car loan|personal loan|hdfc loan|iciciloan|axis loan)\b", re.I), TransactionCategory.EMI),

    # Tax
    (re.compile(r"\b(tds|advance tax|income tax|gst|self assessment tax|challan)\b", re.I), TransactionCategory.TAX),

    # Transfers
    (re.compile(r"\b(neft|rtgs|imps|upi|transfer|trf|fund transfer|nach|ecs|si )\b", re.I), TransactionCategory.TRANSFER),
    (re.compile(r"\b(atm|cash withdrawal|cash deposit)\b", re.I), TransactionCategory.TRANSFER),
]


def map_category(description: str) -> str:
    """
    Return the best-matching TransactionCategory for a description string.
    Falls back to UNKNOWN if no rule matches.
    """
    for pattern, category in _RULES:
        if pattern.search(description):
            return category
    return TransactionCategory.UNKNOWN
