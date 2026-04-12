"""
Money utilities for Artha.

INVARIANT: All monetary values are stored and operated on as PAISE (integer).
Never use float or Decimal for money. 1 INR = 100 paise.

Indian number format examples:
  1,00,000       → 10000000 paise  (₹1,00,000.00)
  1,00,000.50    → 10000050 paise
  -1,234.56      → -123456 paise
  ₹ 5,00,000     → 50000000 paise
"""

import re
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


# Regex: optional currency symbol, optional sign, digits with Indian commas,
# optional decimal part.
_INR_PATTERN = re.compile(
    r"^[₹\s]*"           # optional ₹ symbol and whitespace
    r"(?P<sign>[-−]?)"    # optional minus (ASCII or Unicode minus)
    r"\s*"
    r"(?P<digits>[\d,]+)" # digits with optional Indian-format commas
    r"(?:\.(?P<frac>\d+))?"  # optional fractional paise
    r"\s*(?:Dr|CR|cr|dr)?"   # optional bank suffix (Dr = debit, CR = credit)
    r"\s*$",
    re.IGNORECASE,
)


def parse_inr_to_paise(text: str) -> int:
    """
    Parse an INR amount string (Indian format) and return the value in paise.

    Args:
        text: e.g. "1,00,000.50", "₹ 5,00,000", "-1,234.56", "500.00 Dr"

    Returns:
        Integer paise value (negative for debit-suffixed amounts).

    Raises:
        ValueError: if the text cannot be parsed as a valid INR amount.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"Cannot parse empty or non-string INR value: {text!r}")

    cleaned = text.strip()
    # Determine sign from Dr/Cr suffix before running regex
    suffix_sign = 1
    lower = cleaned.lower()
    if lower.endswith("dr"):
        suffix_sign = -1
    elif lower.endswith("cr"):
        suffix_sign = 1

    match = _INR_PATTERN.match(cleaned)
    if not match:
        raise ValueError(f"Cannot parse INR amount: {text!r}")

    sign_str = match.group("sign")
    digits_str = match.group("digits").replace(",", "")
    frac_str = match.group("frac") or "00"

    # Normalise fraction to exactly 2 digits
    if len(frac_str) == 1:
        frac_str = frac_str + "0"
    elif len(frac_str) > 2:
        # Round to 2 decimal places
        try:
            raw = Decimal(f"{digits_str}.{frac_str}")
            rounded = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            digits_str, frac_str = str(rounded).split(".")
        except InvalidOperation as exc:
            raise ValueError(f"Cannot parse INR amount: {text!r}") from exc

    try:
        paise = int(digits_str) * 100 + int(frac_str)
    except ValueError as exc:
        raise ValueError(f"Cannot parse INR amount: {text!r}") from exc

    sign = -1 if sign_str in ("-", "−") else 1
    return sign * suffix_sign * paise


def format_inr(paise: int) -> str:
    """
    Format a paise integer as a human-readable INR string with Indian grouping.

    Args:
        paise: integer value in paise (may be negative)

    Returns:
        e.g. "₹1,00,000.50" or "-₹500.00"
    """
    if not isinstance(paise, int):
        raise TypeError(f"paise must be int, got {type(paise).__name__}")

    negative = paise < 0
    abs_paise = abs(paise)
    rupees = abs_paise // 100
    frac = abs_paise % 100

    # Indian grouping: last 3 digits, then groups of 2
    rupee_str = str(rupees)
    if len(rupee_str) <= 3:
        grouped = rupee_str
    else:
        # rightmost 3 digits
        result = rupee_str[-3:]
        remaining = rupee_str[:-3]
        while remaining:
            result = remaining[-2:] + "," + result
            remaining = remaining[:-2]
        grouped = result

    sign = "-" if negative else ""
    return f"{sign}₹{grouped}.{frac:02d}"
