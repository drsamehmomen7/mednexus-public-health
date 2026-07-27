"""
Direct tests for rule_based.py — independent of extraction.py, so any
future report type reusing extract_first_date / extract_age can trust
these without re-testing through a full extraction pipeline.
"""

from app.services.rule_based import extract_age, extract_first_date, extract_sex


# --- Dates ---

def test_iso_date():
    assert str(extract_first_date("Reported on 2026-06-15.")) == "2026-06-15"


def test_slash_date_4_digit_year():
    assert str(extract_first_date("Seen 15/06/2026.")) == "2026-06-15"


def test_slash_date_2_digit_year():
    assert str(extract_first_date("Seen 15/6/26.")) == "2026-06-15"


def test_day_month_name_year():
    assert str(extract_first_date("Presented on 26 Jun 2026.")) == "2026-06-26"


def test_day_full_month_name_year():
    assert str(extract_first_date("Presented on 26 June 2026.")) == "2026-06-26"


def test_month_name_day_year():
    assert str(extract_first_date("Presented on Jun 26, 2026.")) == "2026-06-26"


def test_no_date_returns_none():
    assert extract_first_date("No date anywhere in this text.") is None


def test_invalid_calendar_date_is_skipped_not_crashed():
    # 32nd of June isn't a real date — must not raise, just find nothing
    # (or a later valid date if one exists in the same text).
    assert extract_first_date("Invalid: 32/06/2026.") is None


# --- Ages ---

def test_age_with_hyphens_and_old():
    assert extract_age("34-year-old male") == 34


def test_age_with_spaces_and_old():
    assert extract_age("34 years old male") == 34


def test_age_yo_shorthand():
    assert extract_age("29yo female") == 29


def test_age_with_age_prefix_no_old_suffix():
    assert extract_age("age 45 yrs, presented today") == 45


def test_age_with_aged_prefix():
    assert extract_age("aged 60, known diabetic") == 60


def test_age_out_of_plausible_range_is_ignored():
    assert extract_age("age 200 yrs") is None


def test_no_age_returns_none():
    assert extract_age("No age mentioned in this text.") is None


# --- Sex (added 2026-07-27) ---

def test_sex_word_form_female():
    assert extract_sex("54-year-old female, presented today.") == "female"


def test_sex_word_form_male():
    assert extract_sex("8-year-old male, presented today.") == "male"


def test_sex_shorthand_form_male():
    assert extract_sex("33yo M, c/o cough x12d.") == "male"


def test_sex_shorthand_form_female():
    assert extract_sex("9yo F, c/o fever.") == "female"


def test_no_sex_returns_none():
    assert extract_sex("No sex mentioned in this text.") is None
