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
