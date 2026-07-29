"""
Tests for the Immunization extraction orchestrator.

Uses a fake `ner_fn` instead of the real OpenMed/GLiNER model, so these
tests run instantly and do not require any model download.
"""

from app.services.gazetteer import Gazetteer
from app.services.immunization_extraction import (
    _strip_trailing_region,
    extract_immunization,
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
