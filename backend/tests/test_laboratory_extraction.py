"""
Tests for the Laboratory extraction orchestrator.

Uses a fake `ner_fn` instead of the real OpenMed/GLiNER model, so these
tests run instantly and do not require any model download.
"""

from datetime import date

from app.services.confidence import needs_review
from app.services.gazetteer import Gazetteer
from app.services.laboratory_extraction import extract_laboratory, extract_laboratory_with_confidence
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


# --- Regression coverage for the silent date.today() fallback bug -------
# (found real via blind testing 2026-08-17 — see decisions-log.md).
# result_date is a required schema field (unlike specimen_collection_date,
# which stays None when not found), so a value always has to be supplied
# even when nothing parses. The two-tier fallback (result_date_value ->
# specimen_collection_date -> date.today()) is unchanged; the fix is
# making sure ANY use of that fallback is flagged for review, not hidden.

def test_result_date_found_true_when_genuinely_parsed():
    text = "Collected 2026-06-01 for Influenza PCR. Result date: 2026-06-03: Positive."
    report, confidence = extract_laboratory_with_confidence(
        text, ner_fn=fake_ner, lab_test_gazetteer=LAB_TEST_GAZETTEER
    )
    assert str(report.result_date) == "2026-06-03"
    assert confidence["result_date"]["found"] is True
    assert needs_review(confidence) is False


def test_result_date_borrowed_from_specimen_date_is_flagged_found_false():
    """Real bug, tier 1: 'finalized two days later' is not a parseable
    date — extract_result_date() itself finds nothing, so result_date
    silently borrows specimen_collection_date instead. The borrowed
    value is real, not date.today(), but it's still not what the text
    actually said about the result date, so it must still be flagged."""
    text = (
        "Collected on 2026-06-01 for Influenza PCR. "
        "The result, finalized two days later, came back positive."
    )
    report, confidence = extract_laboratory_with_confidence(
        text, ner_fn=fake_ner, lab_test_gazetteer=LAB_TEST_GAZETTEER
    )
    assert str(report.specimen_collection_date) == "2026-06-01"
    assert str(report.result_date) == "2026-06-01"
    assert confidence["result_date"] == {"source": "rule_based", "score": None, "found": False}
    assert needs_review(confidence) is True


def test_result_date_falls_back_to_today_when_no_date_at_all_is_parseable():
    """Real bug, tier 2 (the exact reported scenario): real clinical
    phrasing ('specimen drawn' rather than the generator's own
    'collected') doesn't match the specimen-date keyword anchor either,
    so BOTH tiers of the fallback miss and result_date silently became
    today's actual system date with no review flag."""
    text = (
        "Specimen drawn for Influenza PCR. "
        "The result, finalized two days later, came back positive."
    )
    report, confidence = extract_laboratory_with_confidence(
        text, ner_fn=fake_ner, lab_test_gazetteer=LAB_TEST_GAZETTEER
    )
    assert report.specimen_collection_date is None
    assert report.result_date == date.today()
    assert confidence["result_date"] == {"source": "rule_based", "score": None, "found": False}
    assert needs_review(confidence) is True
