"""
Rule-based (deterministic) extraction helpers.

These handle fields that should NOT depend on a probabilistic model:
dates and ages have a fixed, learnable format, so regex is more reliable
and auditable than asking an NER model to guess them.
"""

import calendar
import re
from datetime import date, timedelta
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


# Matches the clinical shorthand "33yo M" / "9yo F".
_SEX_PATTERN_ABBREVIATION = re.compile(
    r"\b\d{1,3}\s*yo\s*([MF])\b",
    re.IGNORECASE,
)
# Matches prose "54-year-old female" / "8 year old male" — the same age
# phrase extract_age already parses, immediately followed by the word.
_SEX_PATTERN_WORD = re.compile(
    r"\b\d{1,3}[-\s](?:year|yr)s?[-\s]?old\s+(male|female)\b",
    re.IGNORECASE,
)


def extract_sex(text: str) -> Optional[str]:
    """
    Return "male", "female", or None if not stated in text.

    Verified against all 500 synthetic reports: every one is covered by
    exactly one of these two phrasings (shorthand "33yo M" or prose
    "54-year-old female") — zero reports fell outside both. Returns a
    plain string, not the PatientSex enum, to keep this module free of
    any schema dependency (same reasoning as extract_age returning a
    plain int) — the caller wraps it in PatientSex.
    """
    word_match = _SEX_PATTERN_WORD.search(text)
    if word_match:
        return word_match.group(1).lower()

    abbrev_match = _SEX_PATTERN_ABBREVIATION.search(text)
    if abbrev_match:
        return "male" if abbrev_match.group(1).upper() == "M" else "female"

    return None


# Anchors the three phrasings prose reports use for onset: "Onset 25/1/26",
# "Symptoms began on 14 February 2025", "Date of symptom onset: 23/4/26".
_ONSET_KEYWORD_PATTERN = re.compile(
    r"(?:date of symptom onset|onset|symptoms?\s+began on)\s*:?\s*",
    re.IGNORECASE,
)
# Clinical shorthand expresses onset as a duration instead of a date:
# "c/o cough x12d" means symptoms have been present for 12 days as of the
# report date, not a stated onset date.
_DURATION_PATTERN = re.compile(r"x\s*(\d+)\s*d\b", re.IGNORECASE)


def extract_onset_date(text: str, report_date: Optional[date] = None) -> Optional[date]:
    """
    Return the date symptoms began, or None if not determinable.

    Two phrasings cover all 500 synthetic reports, verified directly
    against ground truth (naively reusing extract_first_date on the whole
    text matched 0/500 — onset_date and report_date are both present, in
    different formats/positions, so an unanchored scan can't tell them
    apart):

    1. Prose reports state it directly, anchored by a keyword ("Onset",
       "Symptoms began on", "Date of symptom onset") — reuses
       extract_first_date's format parsing on the text just after the
       keyword, rather than duplicating it.
    2. Clinical shorthand states a DURATION instead ("c/o cough x12d") —
       onset = report_date minus that many days. Requires report_date to
       already be known; returns None if it isn't passed in.
    """
    keyword_match = _ONSET_KEYWORD_PATTERN.search(text)
    if keyword_match:
        window = text[keyword_match.end():keyword_match.end() + 30]
        found = extract_first_date(window)
        if found:
            return found

    duration_match = _DURATION_PATTERN.search(text)
    if duration_match and report_date:
        return report_date - timedelta(days=int(duration_match.group(1)))

    return None
