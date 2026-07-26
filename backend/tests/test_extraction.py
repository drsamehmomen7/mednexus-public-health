"""
Tests for the extraction orchestrator.

Uses a fake `ner_fn` instead of the real OpenMed/GLiNER model, so these
tests run instantly and do not require any model download.
"""

from app.services.extraction import (
    extract_notifiable_disease,
    extract_notifiable_disease_with_confidence,
)
from app.services.ner_client import ExtractedEntity
from app.schemas.notifiable_disease import DiagnosisStatus


def fake_ner(text, labels, domain="biomedical"):
    """Stands in for the real zero-shot model in tests."""
    return [
        ExtractedEntity(label="disease", text="Measles", score=0.91),
        ExtractedEntity(label="region", text="Al Asimah", score=0.87),
        ExtractedEntity(label="facility", text="Al Sabah Hospital", score=0.79),
    ]


def test_extracts_disease_and_region_from_fake_ner():
    text = "Confirmed case reported on 2026-06-15. Patient is 34-year-old."
    case = extract_notifiable_disease(text, ner_fn=fake_ner)

    assert case.disease_name == "Measles"
    assert case.region == "Al Asimah"
    assert case.facility_name == "Al Sabah Hospital"


def test_extracts_date_via_rules():
    text = "Confirmed case reported on 2026-06-15."
    case = extract_notifiable_disease(text, ner_fn=fake_ner)
    assert str(case.report_date) == "2026-06-15"


def test_extracts_age_via_rules():
    text = "Patient is 34-year-old, confirmed on 2026-06-15."
    case = extract_notifiable_disease(text, ner_fn=fake_ner)
    assert case.patient_age == 34


def test_infers_confirmed_status_from_keyword():
    text = "Lab-confirmed case, PCR positive, reported 2026-06-15."
    case = extract_notifiable_disease(text, ner_fn=fake_ner)
    assert case.diagnosis_status == DiagnosisStatus.CONFIRMED
    assert case.lab_confirmed is True


def test_defaults_to_suspected_when_no_status_keyword_present():
    text = "Patient reported on 2026-06-15 with fever."
    case = extract_notifiable_disease(text, ner_fn=fake_ner)
    assert case.diagnosis_status == DiagnosisStatus.SUSPECTED


def test_missing_entities_fall_back_to_unknown():
    def empty_ner(text, labels, domain="biomedical"):
        return []

    text = "Some report with no recognizable entities, dated 2026-06-15."
    case = extract_notifiable_disease(text, ner_fn=empty_ner)
    assert case.disease_name == "Unknown"
    assert case.region == "Unknown"


def test_confidence_report_includes_model_scores_for_found_entities():
    text = "Confirmed measles case, reported 2026-06-15."
    _case, confidence = extract_notifiable_disease_with_confidence(text, ner_fn=fake_ner)

    assert confidence["disease_name"]["source"] == "model"
    assert confidence["disease_name"]["score"] == 0.91
    assert confidence["region"]["score"] == 0.87


def test_confidence_report_flags_missing_entities_without_a_fake_score():
    def empty_ner(text, labels, domain="biomedical"):
        return []

    text = "Some report with no recognizable entities, dated 2026-06-15."
    _case, confidence = extract_notifiable_disease_with_confidence(text, ner_fn=empty_ner)

    assert confidence["disease_name"]["score"] is None
    assert "note" in confidence["disease_name"]


def test_confidence_report_marks_rule_based_fields_distinctly():
    text = "Confirmed measles case, reported 2026-06-15."
    _case, confidence = extract_notifiable_disease_with_confidence(text, ner_fn=fake_ner)

    for field in ("report_date", "patient_age", "diagnosis_status", "lab_confirmed"):
        assert confidence[field]["source"] == "rule_based"
        assert confidence[field]["score"] is None


# --- Regression tests from the first real messy-text test (2026-07-26) ---
# Real note: "pt c/o fever x3d, rash noted. hx of contact w/ confirmed case
# last wk. seen at Farwaniya Hosp ED 15/6/26. sample sent for PCR, results
# pending. 29yo, resides Jahra." — this surfaced three separate bugs.

MESSY_NOTE = (
    "pt c/o fever x3d, rash noted. hx of contact w/ confirmed case last wk. "
    "seen at Farwaniya Hosp ED 15/6/26. sample sent for PCR, results pending. "
    "29yo, resides Jahra."
)


def test_pending_result_overrides_confirmed_mentioned_elsewhere():
    """
    'confirmed' appears in the text describing a CONTACT's case, not the
    patient's own status, and the patient's own result is 'pending'. The
    system must not classify this as a confirmed case.
    """
    case = extract_notifiable_disease(MESSY_NOTE, ner_fn=fake_ner)
    assert case.diagnosis_status == DiagnosisStatus.SUSPECTED
    assert case.lab_confirmed is False


def test_two_digit_year_slash_date_is_parsed():
    """15/6/26 (day/month/2-digit-year) must resolve to 2026-06-15."""
    case = extract_notifiable_disease(MESSY_NOTE, ner_fn=fake_ner)
    assert str(case.report_date) == "2026-06-15"


def test_yo_age_abbreviation_is_parsed():
    """'29yo' (clinical shorthand) must be parsed the same as '29-year-old'."""
    case = extract_notifiable_disease(MESSY_NOTE, ner_fn=fake_ner)
    assert case.patient_age == 29


# --- Regression tests from the second messy-text test (2026-07-26) ---
# Real note: "...Ruled out dengue based on negative rapid test. Suspected
# typhoid fever pending blood culture...age 45 yrs...presented on 26 Jun
# 2026..." — this surfaced negation handling and two more parsing gaps.

MESSY_NOTE_2 = (
    "Female patient, age 45 yrs, presented on 26 Jun 2026. Ruled out dengue "
    "based on negative rapid test. Suspected typhoid fever pending blood "
    "culture. Seen at Adan Hospital, Mubarak Al-Kabeer."
)


def fake_ner_with_negated_disease(text, labels, domain="biomedical"):
    """
    Returns TWO disease entities, in the same order GLiNER returned them
    for the real note: "dengue" (which the text explicitly rules out)
    before "typhoid" (the actual suspected diagnosis) — with correct
    character offsets, since negation checking depends on them.
    """
    dengue_start = text.index("dengue")
    typhoid_start = text.index("typhoid")
    return [
        ExtractedEntity(
            label="disease", text="dengue", score=0.99,
            start=dengue_start, end=dengue_start + len("dengue"),
        ),
        ExtractedEntity(
            label="disease", text="typhoid", score=0.95,
            start=typhoid_start, end=typhoid_start + len("typhoid"),
        ),
        ExtractedEntity(label="facility", text="Adan Hospital", score=0.98),
    ]


def test_ruled_out_disease_is_not_selected_as_diagnosis():
    """
    'Ruled out dengue... Suspected typhoid' must extract typhoid, not the
    excluded disease — picking a ruled-out diagnosis is a clinically
    dangerous error, not a cosmetic one.
    """
    case = extract_notifiable_disease(MESSY_NOTE_2, ner_fn=fake_ner_with_negated_disease)
    assert case.disease_name == "typhoid"


def test_confidence_report_notes_the_excluded_negated_mention():
    _case, confidence = extract_notifiable_disease_with_confidence(
        MESSY_NOTE_2, ner_fn=fake_ner_with_negated_disease
    )
    assert "negated" in confidence["disease_name"].get("note", "").lower()


def test_month_name_date_is_parsed():
    """'26 Jun 2026' (day, month name, year) must resolve to 2026-06-26."""
    case = extract_notifiable_disease(MESSY_NOTE_2, ner_fn=fake_ner_with_negated_disease)
    assert str(case.report_date) == "2026-06-26"


def test_age_with_prefix_and_no_old_suffix_is_parsed():
    """'age 45 yrs' (no 'old' suffix) must still resolve to 45."""
    case = extract_notifiable_disease(MESSY_NOTE_2, ner_fn=fake_ner_with_negated_disease)
    assert case.patient_age == 45
