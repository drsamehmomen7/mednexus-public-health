"""
Rule-based (deterministic) extraction helpers.

These handle fields that should NOT depend on a probabilistic model:
dates and ages have a fixed, learnable format, so regex is more reliable
and auditable than asking an NER model to guess them.
"""

import calendar
import re
from datetime import date, timedelta
from typing import Optional, Tuple

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


# --- Immunization-specific fields (added for the Immunization report type) -

# "2-month-old", "2 month old", "2mo" — the phrasing this project's own
# generator uses for infant ages, verified against all 500 synthetic
# immunization reports before writing this.
_AGE_MONTHS_PATTERN = re.compile(
    r"\b(\d{1,2})\s*-?\s*months?[-\s]?old\b|\b(\d{1,2})mo\b", re.IGNORECASE
)
_NEWBORN_PATTERN = re.compile(r"\bnewborn\b", re.IGNORECASE)


def extract_age_months(text: str) -> Optional[int]:
    """
    Return age in months for infant-phrased reports ("2-month-old",
    "newborn"), or None if the report states age in years instead.

    Immunization reports need this alongside extract_age(): most of the
    schedule (birth through 18 months) is naturally stated in months, not
    years, because "0 years old" carries almost no information for that
    age range. Use extract_age() for the complementary years-based case
    (patient_age = age_months // 12 when this returns a value, otherwise
    extract_age()'s own result).
    """
    if _NEWBORN_PATTERN.search(text):
        return 0
    match = _AGE_MONTHS_PATTERN.search(text)
    if match:
        return int(match.group(1) or match.group(2))
    return None


# "1st dose", "2nd dose", "4th (booster) dose" — matches how dose_number
# is stated across all three report voices; the optional "(booster)"
# aside doesn't change the captured digit.
_DOSE_NUMBER_PATTERN = re.compile(
    r"\b(\d+)(?:st|nd|rd|th)(?:\s*\(booster\))?\s+dose\b", re.IGNORECASE
)


def extract_dose_number(text: str) -> Optional[int]:
    """Return the dose number in a vaccination series, or None if not stated
    (single-dose vaccines like BCG or MMRV don't get a numbered phrasing)."""
    match = _DOSE_NUMBER_PATTERN.search(text)
    return int(match.group(1)) if match else None


# Ordered so the more specific two-letter abbreviations are checked before
# anything that could coincidentally overlap; intranasal isn't in the
# current Kuwait schedule (nothing in the 12-vaccine list uses it) but is
# matched for completeness since the schema supports it.
_ROUTE_PATTERNS = [
    (re.compile(r"\bintranasal\b", re.IGNORECASE), "intranasal"),
    (re.compile(r"\bi\.?d\.?\b", re.IGNORECASE), "intradermal"),
    (re.compile(r"\bi\.?m\.?\b", re.IGNORECASE), "intramuscular"),
    (re.compile(r"\bs\.?c\.?\b", re.IGNORECASE), "subcutaneous"),
    (re.compile(r"\boral\b", re.IGNORECASE), "oral"),
]


def extract_route(text: str) -> Optional[str]:
    """
    Return the injection route as a plain string ("intramuscular", etc.),
    or None if not stated. Kept as a plain string rather than the
    InjectionRoute enum, same reasoning as extract_sex returning a plain
    string — this module stays free of any schema dependency.
    """
    for pattern, route in _ROUTE_PATTERNS:
        if pattern.search(text):
            return route
    return None


_ADVERSE_EVENT_SEVERITY_PATTERN = re.compile(r"\((mild|moderate|severe)\)", re.IGNORECASE)
_ADVERSE_EVENT_DESCRIPTION_PATTERN = re.compile(
    r"(?:AEFI:|following immunization:|developed)\s*(.+?)\s*\((?:mild|moderate|severe)\)",
    re.IGNORECASE,
)
# The narrative voice wraps the description in "developed X following the
# dose (severity)" — "following the dose" is template padding, not part of
# X, so it has to be stripped off the captured text. (The generator's own
# description word list was fixed to avoid a genuine phrase collision here
# — see decisions-log — but the wrapper itself still needs this strip.)
_TRAILING_FOLLOWING_DOSE = re.compile(r"\s*following the dose\s*$", re.IGNORECASE)


def extract_adverse_event(text: str) -> Tuple[bool, str, Optional[str]]:
    """
    Return (adverse_event_reported, severity, description).

    severity is one of "none"/"mild"/"moderate"/"severe" (matching the
    AdverseEventSeverity enum's values) rather than the enum itself, for
    the same reason other extract_* helpers return plain values — the
    caller wraps it. The severity marker "(mild)"/"(moderate)"/"(severe)"
    is the reliable anchor across all three report voices; if it's
    absent, this reports no adverse event without trying to guess from
    looser language like "no adverse reaction" (a report that mentions
    neither phrasing at all should not be assumed clean).
    """
    severity_match = _ADVERSE_EVENT_SEVERITY_PATTERN.search(text)
    if not severity_match:
        return False, "none", None

    severity = severity_match.group(1).lower()
    description_match = _ADVERSE_EVENT_DESCRIPTION_PATTERN.search(text)
    description = None
    if description_match:
        description = _TRAILING_FOLLOWING_DOSE.sub("", description_match.group(1).strip()).strip()
    return True, severity, description


# --- Laboratory-specific fields (added for the Laboratory report type) ----

# Anchors specimen_collection_date vs result_date — a lab report always
# states both, often close together, so the window has to be narrow
# enough not to reach into the OTHER date. Verified against all 500
# synthetic lab reports: a 20-char window is wide enough for every date
# format used (up to "22 February 2025", 17 chars) but narrow enough to
# never reach the second date, even in the tightest shorthand phrasing
# ("Collected 22 Mar 2025, result 27/3/25:").
_SPECIMEN_DATE_KEYWORD_PATTERN = re.compile(
    r"(?:specimen collection date|collected(?:\s+on)?)\s*:?\s*", re.IGNORECASE
)
_RESULT_DATE_KEYWORD_PATTERN = re.compile(
    r"(?:result date|result finalized|result)\s*:?\s*", re.IGNORECASE
)
_DATE_WINDOW_CHARS = 20


def extract_specimen_collection_date(text: str) -> Optional[date]:
    """Return the specimen collection date, or None if not stated."""
    match = _SPECIMEN_DATE_KEYWORD_PATTERN.search(text)
    if not match:
        return None
    window = text[match.end():match.end() + _DATE_WINDOW_CHARS]
    return extract_first_date(window)


def extract_result_date(text: str) -> Optional[date]:
    """
    Return the date the lab result was finalized, or None if not stated.

    The keyword pattern's fallback alternative (bare "result") only
    matches correctly because, in every phrasing this project generates,
    the more specific anchors ("result date", "result finalized") or the
    bare word's only occurrence precede any OTHER use of "result" in the
    text (e.g. "Result: Positive" always appears after "Result Date:" in
    the structured voice, never before) — re.search takes the leftmost
    match, so the right one wins. Verified against all 500 reports.
    """
    match = _RESULT_DATE_KEYWORD_PATTERN.search(text)
    if not match:
        return None
    window = text[match.end():match.end() + _DATE_WINDOW_CHARS]
    return extract_first_date(window)


_RESULT_STATUS_KEYWORDS = [
    ("indeterminate", re.compile(r"\bindeterminate\b", re.IGNORECASE)),
    ("pending", re.compile(r"\bpending\b", re.IGNORECASE)),
    ("negative", re.compile(r"\bnegative\b", re.IGNORECASE)),
    ("positive", re.compile(r"\bpositive\b", re.IGNORECASE)),
]


def extract_lab_result(text: str) -> Optional[str]:
    """
    Return "positive"/"negative"/"indeterminate"/"pending", or None if
    none of those words appear. Plain string, not the TestResult enum —
    same reasoning as the other extract_* helpers returning plain values.
    """
    for value, pattern in _RESULT_STATUS_KEYWORDS:
        if pattern.search(text):
            return value
    return None
