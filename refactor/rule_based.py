"""
Rule-based (deterministic) extraction helpers.

These handle fields that should NOT depend on a probabilistic model:
dates and ages have a fixed, learnable format, so regex is more reliable
and auditable than asking an NER model to guess them.
"""

import calendar
import re
from datetime import date
from typing import Optional

_MONTH_NAME_TO_NUM = {
    name.lower(): i for i, name in enumerate(calendar.month_name) if name
}
_MONTH_NAME_TO_NUM.update({
    abbr.lower(): i for i, abbr in enumerate(calendar.month_abbr) if abbr
})
_MONTH_NAMES_PATTERN = "|".join(sorted(_MONTH_NAME_TO_NUM.keys(), key=len, reverse=True))

_DATE_PATTERNS = [
    r"\b(\d{4})-(\d{2})-(\d{2})\b",           # 2026-07-01
    r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",       # 01/07/2026 (day/month/year, 4-digit year)
    r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b",       # 15/6/26 (day/month/2-digit year) — common in clinical shorthand
]

# "26 Jun 2026" / "26 June 2026" — day, month name, year
_DATE_PATTERN_DAY_MONTHNAME_YEAR = re.compile(
    rf"\b(\d{{1,2}})\s+({_MONTH_NAMES_PATTERN})\s+(\d{{4}})\b", re.IGNORECASE
)
# "Jun 26, 2026" / "June 26 2026" — month name, day, year
_DATE_PATTERN_MONTHNAME_DAY_YEAR = re.compile(
    rf"\b({_MONTH_NAMES_PATTERN})\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.IGNORECASE
)

# Matches "34-year-old" / "34 years old" / the clinical shorthand "29yo".
_AGE_PATTERN = re.compile(
    r"\b(\d{1,3})\s*[-\s]?(?:(?:year|yr)s?[-\s]?old|yo)\b",
    re.IGNORECASE,
)
# Matches "age 45 yrs" / "aged 45" / "age: 45" — no "old" suffix, but an
# explicit "age" cue word keeps this from matching unrelated numbers like
# "3 years ago".
_AGE_PATTERN_WITH_PREFIX = re.compile(
    r"\bage[d]?\s*[:\-]?\s*(\d{1,3})\b(?:\s*(?:year|yr)s?)?",
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

    day_monthname_match = _DATE_PATTERN_DAY_MONTHNAME_YEAR.search(text)
    if day_monthname_match:
        day_str, month_name, year_str = day_monthname_match.groups()
        month = _MONTH_NAME_TO_NUM.get(month_name.lower())
        if month:
            try:
                return date(int(year_str), month, int(day_str))
            except ValueError:
                pass

    monthname_day_match = _DATE_PATTERN_MONTHNAME_DAY_YEAR.search(text)
    if monthname_day_match:
        month_name, day_str, year_str = monthname_day_match.groups()
        month = _MONTH_NAME_TO_NUM.get(month_name.lower())
        if month:
            try:
                return date(int(year_str), month, int(day_str))
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

    prefix_match = _AGE_PATTERN_WITH_PREFIX.search(text)
    if prefix_match:
        age = int(prefix_match.group(1))
        if 0 <= age <= 120:
            return age

    return None
