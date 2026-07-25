"""
Tests for the extraction orchestrator.

Uses a fake `ner_fn` instead of the real OpenMed/GLiNER model, so these
tests run instantly and do not require any model download.
"""

from app.services.extraction import extract_notifiable_disease
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
