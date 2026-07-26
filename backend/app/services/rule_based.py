"""
Rule-based (deterministic) extraction helpers.

These handle fields that should NOT depend on a probabilistic model:
dates and ages have a fixed, learnable format, so regex is more reliable
and auditable than asking an NER model to guess them.
"""

import re
from datetime import date, datetime
from typing import Optional

_DATE_PATTERNS = [
    r"\b(\d{4})-(\d{2})-(\d{2})\b",           # 2026-07-01
    r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",       # 01/07/2026 (day/month/year, 4-digit year)
    r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b",       # 15/6/26 (day/month/2-digit year) — common in clinical shorthand
]

# Matches both "34-year-old"/"34 years old" and the clinical shorthand "29yo".
_AGE_PATTERN = re.compile(
    r"\b(\d{1,3})\s*[-\s]?(?:(?:year|yr)s?[-\s]?old|yo)\b",
    re.IGNORECASE,
)


def extract_first_date(text: str) -> Optional[date]:
    """Return the first date found in free text, or None if none is found."""
    iso_match = re.search(_DATE_PATTERNS[0], text)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass

    slash_match = re.search(_DATE_PATTERNS[1], text)
    if slash_match:
        day, month, year = map(int, slash_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # 2-digit year: assume 2000s. This project has no reports predating
    # 2000, so this is a safe assumption rather than a real Y2K-style guess.
    short_year_match = re.search(_DATE_PATTERNS[2], text)
    if short_year_match:
        day, month, year_2digit = map(int, short_year_match.groups())
        try:
            return date(2000 + year_2digit, month, day)
        except ValueError:
            pass

    return None


def extract_age(text: str) -> Optional[int]:
    """Return the first age-in-years mention found in free text, or None."""
    match = _AGE_PATTERN.search(text)
    if match:
        age = int(match.group(1))
        if 0 <= age <= 120:
            return age
    return None
