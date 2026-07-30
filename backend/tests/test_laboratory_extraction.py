"""
Tests for the Laboratory extraction orchestrator.

Uses a fake `ner_fn` instead of the real OpenMed/GLiNER model, so these
tests run instantly and do not require any model download.
"""

from app.services.gazetteer import Gazetteer
from app.services.laboratory_extraction import extract_laboratory
from app.services.ner_client import ExtractedEntity
from app.schemas.laboratory import TestResult


def fake_ner(text, labels, domain="biomedical"):
    return [
        ExtractedEntity(label="region", text="Al Asimah", score=0.87),
        ExtractedEntity(label="facility", text="Al Sabah Hospital", score=0.79),
    ]


LAB_TEST_GAZETTEER = Gazetteer(["Influenza PCR", "Measles IgM Serology"])
SPECIMEN_GAZETTEER = Gazetteer(["Nasopharyngeal Swab", "Serum"])
DISEASE_GAZETTEER = Gazetteer(["Influenza", "Measles"])


def test_extracts_test_name_specimen_and_region():
    text = "Nasopharyngeal Swab specimen collected for Influenza PCR at Al Sabah Hospital."
    report = extract_laboratory(
        text, ner_fn=fake_ner,
        lab_test_gazetteer=LAB_TEST_GAZETTEER,
        specimen_type_gazetteer=SPECIMEN_GAZETTEER,
    )
    assert report.test_name == "Influenza PCR"
    assert report.specimen_type == "Nasopharyngeal Swab"
    assert report.region == "Al Asimah"
    assert report.facility_name == "Al Sabah Hospital"


def test_extracts_dates_and_result_via_rules():
    text = "Collected 2026-06-01 for Influenza PCR. Result date: 2026-06-03: Positive."
    report = extract_laboratory(text, ner_fn=fake_ner, lab_test_gazetteer=LAB_TEST_GAZETTEER)
    assert str(report.specimen_collection_date) == "2026-06-01"
    assert str(report.result_date) == "2026-06-03"
    assert report.result == TestResult.POSITIVE


def test_pathogen_identified_only_when_positive():
    text = "Measles IgM Serology. Result date: 2026-06-03: Positive, identifying Measles."
    report = extract_laboratory(
        text, ner_fn=fake_ner,
        lab_test_gazetteer=LAB_TEST_GAZETTEER, disease_gazetteer=DISEASE_GAZETTEER,
    )
    assert report.pathogen_identified == "Measles"


def test_pathogen_not_identified_when_negative_even_if_disease_name_present():
    """
    Real design point: the disease name appears in the TEST's own name
    ("Measles IgM Serology") regardless of outcome — a gazetteer hit
    there must not be read as "identified" when the result is negative.
    """
    text = "Measles IgM Serology. Result date: 2026-06-03: Negative."
    report = extract_laboratory(
        text, ner_fn=fake_ner,
        lab_test_gazetteer=LAB_TEST_GAZETTEER, disease_gazetteer=DISEASE_GAZETTEER,
    )
    assert report.result == TestResult.NEGATIVE
    assert report.pathogen_identified is None


def test_specimen_and_result_dates_disambiguated_in_tight_shorthand():
    """Real case found while testing the generator: two dates close
    together in shorthand voice must not be swapped."""
    text = "Collected 22 Mar 2025, result 27/3/25: Positive."
    report = extract_laboratory(text, ner_fn=fake_ner, lab_test_gazetteer=LAB_TEST_GAZETTEER)
    assert str(report.specimen_collection_date) == "2025-03-22"
    assert str(report.result_date) == "2025-03-27"
