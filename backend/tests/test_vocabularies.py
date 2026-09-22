"""
Tests for the terminology-preview helpers in vocabularies.py: get_icd10_entry, get_loinc_entry,
get_cvx_entry. These are additive, preview-only functions (used by GET /terminology/preview) built
on the SAME lookups the save endpoints already call (load_icd10_lookup, get_loinc_code,
get_cvx_code) -- none of those existing functions change shape or behavior here.

Run against the real data files (icd10_codes.json, loinc_codes.json, cvx_codes.json), not mocks --
the whole point is to prove these functions read what's actually shipped, especially the "deliberate
no-code, with a reviewer's reasoning" entries, which only exist as real data, not as something a
mock could stand in for.
"""

import pytest

from app.services import vocabularies as vocab

ENTRY_KEYS = {"code", "status", "note", "in_vocabulary"}


def _assert_shape(entry):
    assert set(entry.keys()) == ENTRY_KEYS


# ---------------------------------------------------------------------------
# ICD-10
# ---------------------------------------------------------------------------


def test_icd10_entry_for_a_plain_disease_has_no_note():
    entry = vocab.get_icd10_entry("Anthrax")
    _assert_shape(entry)
    assert entry == {"code": "A22", "status": None, "note": None, "in_vocabulary": True}


def test_icd10_entry_for_a_flagged_disease_carries_its_reviewer_note():
    entry = vocab.get_icd10_entry("Influenza")
    _assert_shape(entry)
    assert entry["code"] == "J11"
    assert entry["in_vocabulary"] is True
    assert entry["status"] is None  # no ICD-10 status taxonomy yet -- by design, see decisions-log.md
    assert entry["note"] is not None
    assert "J09-J11" in entry["note"]


def test_icd10_entry_for_a_disease_name_that_does_not_match_anything():
    entry = vocab.get_icd10_entry("Not A Real Disease Name")
    _assert_shape(entry)
    assert entry == {"code": None, "status": None, "note": None, "in_vocabulary": False}


# Every disease this project has flagged for review must carry both a real code AND a note --
# a dataset-wide invariant, not just true of the one example above.
_FLAGGED_DISEASES = [
    "HIV infection",
    "Haemophilus influenzae invasive disease",
    "Hepatitis A",
    "Hepatitis B",
    "Hepatitis C",
    "Influenza",
    "Malaria",
    "Syphilis",
    "Tuberculosis",
]


@pytest.mark.parametrize("disease_name", _FLAGGED_DISEASES)
def test_every_flagged_icd10_disease_has_both_a_code_and_a_note(disease_name):
    entry = vocab.get_icd10_entry(disease_name)
    assert entry["in_vocabulary"] is True
    assert entry["code"] is not None
    assert entry["note"] is not None and entry["note"].strip() != ""


def test_get_icd10_entry_does_not_change_what_load_icd10_lookup_itself_returns():
    """The save endpoint calls load_icd10_lookup().get(...) directly -- confirm that keeps working
    identically, whichever function happens to run first (they share the same underlying cache)."""
    before = dict(vocab.load_icd10_lookup())
    vocab.get_icd10_entry("Influenza")
    after = vocab.load_icd10_lookup()
    assert after == before
    assert all(not k.endswith("_flag") and k != "_comment" for k in after)


# ---------------------------------------------------------------------------
# LOINC
# ---------------------------------------------------------------------------


def test_loinc_entry_for_an_exact_match():
    entry = vocab.get_loinc_entry("Dengue IgM Serology")
    _assert_shape(entry)
    assert entry == {
        "code": "25338-5",
        "status": "EXACT",
        "note": "Qualitative Presence in Serum, matches result field shape.",
        "in_vocabulary": True,
    }


@pytest.mark.parametrize(
    "test_name,expected_status",
    [
        ("Poliovirus Stool PCR", "REJECTED_MISMATCH"),
        ("Hantavirus IgM Serology", "NO_DIRECT_LOINC"),
        ("Leprosy Skin Biopsy", "NO_DIRECT_LOINC"),
    ],
)
def test_loinc_entry_for_a_deliberately_uncoded_test_explains_why(test_name, expected_status):
    """These 3 of 71 tests have no LOINC code by Dr. Sameh's deliberate decision, not because
    test_name failed to match anything -- in_vocabulary must be True and note must be populated,
    which is exactly what distinguishes this from an unmatched test name (next test)."""
    entry = vocab.get_loinc_entry(test_name)
    _assert_shape(entry)
    assert entry["code"] is None
    assert entry["status"] == expected_status
    assert entry["in_vocabulary"] is True
    assert entry["note"] is not None and "Dr. Sameh" in entry["note"]


def test_loinc_entry_for_a_test_name_that_does_not_match_anything():
    """Same code=None as the deliberate-no-code tests above, but a genuinely different shape:
    no status, no note, in_vocabulary False -- this is the pair the distinction has to hold across."""
    entry = vocab.get_loinc_entry("Some Made Up Test Nobody Has Heard Of")
    _assert_shape(entry)
    assert entry == {"code": None, "status": None, "note": None, "in_vocabulary": False}


def test_loinc_entry_guards_against_a_non_dict_raw_entry(monkeypatch):
    """loinc_codes.json has no such entry today, but the shape is guarded defensively anyway
    (see get_cvx_entry, which hits this for real) -- simulate it here so the guard itself is tested."""
    monkeypatch.setattr(vocab, "load_loinc_lookup", lambda: {"Weird Entry": "not a dict"})
    entry = vocab.get_loinc_entry("Weird Entry")
    assert entry == {"code": None, "status": None, "note": None, "in_vocabulary": False}


# ---------------------------------------------------------------------------
# CVX
# ---------------------------------------------------------------------------


def test_cvx_entry_for_an_exact_match():
    entry = vocab.get_cvx_entry("BCG")
    _assert_shape(entry)
    assert entry == {
        "code": "19",
        "status": "EXACT",
        "note": "Bacillus Calmette-Guerin vaccine. Single active code, no ambiguity.",
        "in_vocabulary": True,
    }


def test_cvx_entry_for_a_vaccine_name_that_does_not_match_anything():
    entry = vocab.get_cvx_entry("Not A Real Vaccine")
    _assert_shape(entry)
    assert entry == {"code": None, "status": None, "note": None, "in_vocabulary": False}


def test_cvx_entry_does_not_crash_on_the_real_comment_key():
    """cvx_codes.json's own top-level '_comment' is a plain string, not a {cvx, status, notes}
    object (unlike icd10_codes.json's '_comment', which load_icd10_lookup() already filters out).
    get_cvx_code() has this exact same gap and would raise on it; this function must not."""
    assert "_comment" in vocab.load_cvx_lookup()  # the real landmine this guards against
    entry = vocab.get_cvx_entry("_comment")
    assert entry == {"code": None, "status": None, "note": None, "in_vocabulary": False}


# ---------------------------------------------------------------------------
# Shape parity across all three systems (what the preview endpoint depends on)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn,matched_value,unmatched_value",
    [
        (vocab.get_icd10_entry, "Anthrax", "Not A Real Disease"),
        (vocab.get_loinc_entry, "Dengue IgM Serology", "Not A Real Test"),
        (vocab.get_cvx_entry, "BCG", "Not A Real Vaccine"),
    ],
)
def test_entry_functions_always_return_the_same_four_keys(fn, matched_value, unmatched_value):
    _assert_shape(fn(matched_value))
    _assert_shape(fn(unmatched_value))
