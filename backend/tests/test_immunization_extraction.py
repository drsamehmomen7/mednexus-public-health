"""
Tests for the Immunization extraction orchestrator.

Uses a fake `ner_fn` instead of the real OpenMed/GLiNER model, so these
tests run instantly and do not require any model download.
"""

from datetime import date

from app.services.confidence import needs_review
from app.services.gazetteer import Gazetteer
from app.services.immunization_extraction import (
    _strip_trailing_region,
    extract_immunization,
    extract_immunization_with_confidence,
)
from app.services.ner_client import ExtractedEntity
from app.schemas.immunization import InjectionRoute


def fake_ner(text, labels, domain="biomedical"):
    """Stands in for the real zero-shot model in tests."""
    return [
        ExtractedEntity(label="vaccine", text="Hexa", score=0.91),
        ExtractedEntity(label="region", text="Al Asimah", score=0.87),
        ExtractedEntity(label="facility", text="Al Sabah Hospital", score=0.79),
    ]


def test_extracts_vaccine_region_facility_from_fake_ner():
    text = "1st dose of Hexa vaccine given 2026-06-15."
    record = extract_immunization(text, ner_fn=fake_ner)

    assert record.vaccine_name == "Hexa"
    assert record.region == "Al Asimah"
    assert record.facility_name == "Al Sabah Hospital"


def test_extracts_dose_route_and_date_via_rules():
    text = "Route: I.M. 1st dose of Hexa vaccine given 2026-06-15."
    record = extract_immunization(text, ner_fn=fake_ner)

    assert record.dose_number == 1
    assert record.route == InjectionRoute.IM
    assert str(record.administration_date) == "2026-06-15"


def test_vaccine_gazetteer_takes_precedence_over_ner():
    vaccine_gazetteer = Gazetteer(["MMRV"])
    text = "MMRV vaccine given 2026-06-15."
    record = extract_immunization(text, ner_fn=fake_ner, vaccine_gazetteer=vaccine_gazetteer)
    assert record.vaccine_name == "MMRV"


# --- Regression coverage for the silent date.today() fallback bug -------
# (found real via blind testing 2026-08-17 — see decisions-log.md).
# administration_date is a required schema field, so a value always has
# to be supplied even when nothing parses; the fix is not changing that
# value, it's making sure the fallback is flagged for review, not hidden.

def test_administration_date_fallback_is_flagged_found_false_and_needs_review():
    text = "Hexa vaccine given, no parseable date anywhere in this text."
    record, confidence = extract_immunization_with_confidence(text, ner_fn=fake_ner)

    assert record.administration_date == date.today()
    assert confidence["administration_date"] == {"source": "rule_based", "score": None, "found": False}
    assert needs_review(confidence) is True


def test_administration_date_found_true_when_genuinely_parsed():
    text = "1st dose of Hexa vaccine given 2026-06-15."
    record, confidence = extract_immunization_with_confidence(text, ner_fn=fake_ner)

    assert str(record.administration_date) == "2026-06-15"
    assert confidence["administration_date"]["found"] is True


# --- Real bug found against an actual 500-report GLiNER run: the model's -
# "facility" label sometimes swallows a trailing ", <region>" when both
# are on one comma-separated line. -------------------------------------

def test_strip_trailing_region_removes_known_region_suffix():
    region_gazetteer = Gazetteer(["Al Asimah", "Hawalli"])
    assert _strip_trailing_region("Central District Hospital, Al Asimah", region_gazetteer) == \
        "Central District Hospital"


def test_strip_trailing_region_leaves_facility_without_region_suffix_alone():
    region_gazetteer = Gazetteer(["Al Asimah", "Hawalli"])
    assert _strip_trailing_region("Ardiya Clinic", region_gazetteer) == "Ardiya Clinic"


def test_strip_trailing_region_handles_none_gazetteer():
    assert _strip_trailing_region("Central District Hospital, Al Asimah", None) == \
        "Central District Hospital, Al Asimah"


def test_strip_trailing_region_handles_none_facility():
    region_gazetteer = Gazetteer(["Al Asimah"])
    assert _strip_trailing_region(None, region_gazetteer) is None


def test_facility_region_leak_fixed_end_to_end():
    """The exact pattern seen in the real GLiNER run's mismatches."""
    def leaky_ner(text, labels, domain="biomedical"):
        return [
            ExtractedEntity(label="vaccine", text="Hexa", score=0.9),
            ExtractedEntity(label="region", text="Al Asimah", score=0.9),
            ExtractedEntity(label="facility", text="Central District Hospital, Al Asimah", score=0.8),
        ]

    region_gazetteer = Gazetteer(["Al Asimah", "Hawalli"])
    text = "Facility: Central District Hospital, Al Asimah. Hexa vaccine given 2026-06-15."
    record = extract_immunization(text, ner_fn=leaky_ner, region_gazetteer=region_gazetteer)
    assert record.facility_name == "Central District Hospital"
