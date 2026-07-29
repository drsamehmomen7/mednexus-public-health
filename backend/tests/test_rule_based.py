"""
Direct tests for rule_based.py — independent of extraction.py, so any
future report type reusing extract_first_date / extract_age can trust
these without re-testing through a full extraction pipeline.
"""

from app.services.rule_based import (
    extract_adverse_event,
    extract_age,
    extract_age_months,
    extract_dose_number,
    extract_first_date,
    extract_onset_date,
    extract_route,
    extract_sex,
)


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


# --- Onset date (added 2026-07-28) ---

def test_onset_date_from_onset_keyword():
    assert str(extract_onset_date("Onset 2025-03-04 with fever, fatigue.")) == "2025-03-04"


def test_onset_date_from_symptoms_began_on():
    assert str(extract_onset_date("Symptoms began on 14 February 2025 with cough.")) == "2025-02-14"


def test_onset_date_from_date_of_symptom_onset_label():
    assert str(extract_onset_date("Date of symptom onset: 23/4/26\nPresenting symptoms: itching.")) == "2026-04-23"


def test_onset_date_from_shorthand_duration():
    from datetime import date
    assert extract_onset_date(
        "33yo M, c/o cough x12d. Seen 26/1/25.", report_date=date(2025, 1, 26)
    ) == date(2025, 1, 14)


def test_onset_date_shorthand_needs_report_date():
    # Duration alone, with no report_date supplied, can't resolve to a date.
    assert extract_onset_date("c/o cough x12d. Seen 26/1/25.", report_date=None) is None


def test_no_onset_date_returns_none():
    assert extract_onset_date("No onset information in this text.") is None


# --- Immunization fields (added for the Immunization report type) ---

def test_age_months_from_month_old_phrase():
    assert extract_age_months("2-month-old patient received the vaccine.") == 2


def test_age_months_from_shorthand():
    assert extract_age_months("4mo, 2nd dose of Rota vaccine.") == 4


def test_age_months_newborn():
    assert extract_age_months("Newborn received Hepatitis B vaccine.") == 0


def test_age_months_none_when_years_stated():
    assert extract_age_months("16-year-old patient received Tdap.") is None


def test_dose_number_ordinal():
    assert extract_dose_number("Vaccine administered: 2nd dose of Hexa vaccine") == 2


def test_dose_number_booster_aside_still_parses():
    assert extract_dose_number("4th (booster) dose of Pneumococcal vaccine") == 4


def test_dose_number_none_for_single_dose_vaccine():
    assert extract_dose_number("Vaccine administered: BCG vaccine") is None


def test_route_abbreviation_im():
    assert extract_route("Route: I.M.") == "intramuscular"


def test_route_abbreviation_sc():
    assert extract_route("administered s.c.") == "subcutaneous"


def test_route_oral():
    assert extract_route("Route: Oral") == "oral"


def test_route_intradermal():
    assert extract_route("Route: I.D.") == "intradermal"


def test_route_none_when_not_stated():
    assert extract_route("No route mentioned here.") is None


def test_adverse_event_reported_with_severity_and_description():
    reported, severity, description = extract_adverse_event(
        "AEFI: mild swelling at injection site (mild)."
    )
    assert reported is True
    assert severity == "mild"
    assert description == "mild swelling at injection site"


def test_adverse_event_narrative_wrapper_stripped():
    reported, severity, description = extract_adverse_event(
        "Patient developed low-grade fever following the dose (mild). "
    )
    assert description == "low-grade fever"


def test_no_adverse_event_returns_none_severity():
    reported, severity, description = extract_adverse_event("No adverse event reported.")
    assert reported is False
    assert severity == "none"
    assert description is None
