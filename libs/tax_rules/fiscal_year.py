"""
Indian fiscal year utilities (April 1 – March 31).

Format: "YYYY-YY"  e.g. "2024-25"
"""

from datetime import date


def get_fiscal_year(d: date) -> str:
    """
    Return the Indian fiscal year string for a given date.

    April 1, 2024 – March 31, 2025  →  "2024-25"
    January 15, 2025               →  "2024-25"
    April 1, 2025                  →  "2025-26"
    """
    if d.month >= 4:
        start = d.year
    else:
        start = d.year - 1
    end = (start + 1) % 100  # last two digits of end year
    return f"{start}-{end:02d}"


def fiscal_year_range(fiscal_year: str) -> tuple[date, date]:
    """
    Return (start_date, end_date) for a fiscal year string like "2024-25".

    Returns:
        (date(2024, 4, 1), date(2025, 3, 31))

    Raises:
        ValueError: if fiscal_year is not in "YYYY-YY" format.
    """
    parts = fiscal_year.split("-")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError(f"Invalid fiscal year format: {fiscal_year!r}. Expected 'YYYY-YY'.")

    start_year = int(parts[0])
    end_year_short = int(parts[1])

    # Derive full end year: handle century boundary (e.g., "2099-00" → 2100)
    century = (start_year // 100) * 100
    end_year = century + end_year_short
    if end_year <= start_year:
        end_year += 100

    return date(start_year, 4, 1), date(end_year, 3, 31)
