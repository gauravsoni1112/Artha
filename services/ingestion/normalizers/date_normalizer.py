"""
Date normalizer — parse Indian bank statement date strings to datetime.date.

Handles common formats across HDFC, SBI, ICICI, Axis, and CAMS/KFintech:
  - DD/MM/YYYY        → 15/03/2024
  - DD-MM-YYYY        → 15-03-2024
  - DD-Mon-YYYY       → 15-Mar-2024
  - DD-Mon-YY         → 15-Mar-24
  - YYYY-MM-DD        → 2024-03-15  (ISO, Zerodha API)
  - DD MMM YYYY       → 15 Mar 2024
  - DD.MM.YYYY        → 15.03.2024
"""

import re
from datetime import date, datetime
from typing import Optional

# All formats tried in order of specificity
_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%Y-%m-%d",
    "%d %b %Y",
    "%d %B %Y",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%d-%m-%y",
]

# Normalise Unicode/non-breaking spaces and common OCR artefacts
_CLEAN = re.compile(r"[\u00a0\u202f\t]+")


def parse_date(text: str) -> Optional[date]:
    """
    Parse a date string into a date object.

    Returns None if no known format matches (caller decides how to handle).
    """
    if not text or not text.strip():
        return None

    cleaned = _CLEAN.sub(" ", text).strip()

    for fmt in _FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    return None


def parse_date_strict(text: str) -> date:
    """
    Like parse_date but raises ValueError if the string cannot be parsed.
    Used by parsers that guarantee a date field exists.
    """
    result = parse_date(text)
    if result is None:
        raise ValueError(f"Cannot parse date string: {text!r}")
    return result
