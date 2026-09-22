"""
Tests for report-type detection (see services/report_type_detection.py
for why this is gazetteer-based, not a model).
"""

from app.services.gazetteer import Gazetteer
from app.services.report_type_detection import detect_report_type


DISEASE_GAZETTEER = Gazetteer(["Influenza", "Measles", "Meningococcal disease"])
VACCINE_GAZETTEER = Gazetteer(["Hexa", "MMR", "Meningococcal ACWY"])


def test_detects_notifiable_disease_report():
    text = "Suspected case of Influenza, onset 2026-01-04, diagnosis confirmed by PCR."
    detected, scores = detect_report_type(text, DISEASE_GAZETTEER, VACCINE_GAZETTEER)
    assert detected == "notifiable"
    assert scores["notifiable"] > scores["immunization"]


def test_detects_immunization_report():
    text = "1st dose of Hexa vaccine administered, no adverse event following immunization."
    detected, scores = detect_report_type(text, DISEASE_GAZETTEER, VACCINE_GAZETTEER)
    assert detected == "immunization"
    assert scores["immunization"] > scores["notifiable"]


LAB_TEST_GAZETTEER = Gazetteer(["Influenza PCR", "Measles IgM Serology"])


def test_detects_laboratory_report():
    text = "Nasopharyngeal swab specimen collected for Influenza PCR. Result: Positive."
    detected, scores = detect_report_type(
        text, DISEASE_GAZETTEER, VACCINE_GAZETTEER, LAB_TEST_GAZETTEER
    )
    assert detected == "laboratory"
    assert scores["laboratory"] > scores["notifiable"]
    assert scores["laboratory"] > scores["immunization"]


def test_no_signal_returns_unknown():
    text = "The weather today was mild with occasional cloud cover."
    detected, scores = detect_report_type(text, DISEASE_GAZETTEER, VACCINE_GAZETTEER)
    assert detected == "unknown"
    assert scores["notifiable"] == 0
    assert scores["immunization"] == 0


def test_tie_returns_unknown():
    # One disease-signal word, one immunization-signal word, no gazetteer
    # term matches — a genuine tie should not be forced to a guess.
    text = "diagnosis and vaccine"
    detected, scores = detect_report_type(text, DISEASE_GAZETTEER, VACCINE_GAZETTEER)
    assert detected == "unknown"
    assert scores["notifiable"] == scores["immunization"]


def test_works_without_gazetteers_using_signal_words_only():
    text = "Patient developed adverse event following immunization, mild severity."
    detected, scores = detect_report_type(text, None, None)
    assert detected == "immunization"


def test_scores_surface_matched_terms_for_transparency():
    text = "Confirmed Measles case."
    _, scores = detect_report_type(text, DISEASE_GAZETTEER, VACCINE_GAZETTEER)
    assert "Measles" in scores["matched_diseases"]
    assert scores["matched_vaccines"] == []


# --- Regression coverage for the paste-path misclassification bug -------
# (found real via blind testing 2026-08-17 — see decisions-log.md). The
# detection SCORING was never actually wrong here — this pins the exact
# real-phrasing text that triggered the bug report, so a future change to
# the signal-word/gazetteer weighting can't silently regress it. The
# actual bug was that app.js never called this function at all for
# pasted text (only for uploads); that half of the fix has no pytest
# coverage since this project has no frontend test framework — see
# decisions-log.md for how it was verified instead (live UI + network
# inspection).
def test_real_phrasing_immunization_report_is_not_misdetected_as_laboratory():
    text = (
        "Vaccination given today at Bayan Clinic (Hawalli) to a 7-month-old infant. "
        "Product administered: Hexa vaccine, this being her second dose. "
        "Administered intramuscularly in the thigh. Date: 20/02/2025. "
        "Parent reports mild fever the following day but no other concerns "
        "— a known, expected reaction, not classified as a serious adverse event."
    )
    lab_gazetteer = Gazetteer(["Influenza PCR", "Measles IgM Serology"])
    detected, scores = detect_report_type(text, DISEASE_GAZETTEER, VACCINE_GAZETTEER, lab_gazetteer)
    assert detected == "immunization"
    assert scores["laboratory"] == 0
