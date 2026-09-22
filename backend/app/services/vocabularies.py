"""
Builds vocabularies for closed-vocabulary extraction fields from data the
deployment already holds, rather than from anything hardcoded.

The separation matters: `gazetteer.py` knows HOW to match a vocabulary,
this module knows WHERE a given deployment's vocabulary lives, and
`extraction.py` knows neither. Swap the data and the same code serves a
different country with no change to extraction logic — which is the
system-agnostic ground rule stated in docs/decisions-log.md.

Region vocabulary comes from `population_strata`, because that table
already has to list every region for rate-per-100,000 to work. Reusing it
means there is exactly one place a deployment declares its regions, and no
opportunity for two lists to drift apart.

Disease vocabulary (added after the 500-report load showed disease_name at
84.8% versus 100% for every other, gazetteer-backed field) has no
equivalent existing table yet — nothing already needs "the list of
notifiable diseases" the way population_strata needs regions. Until a real
deployment supplies its own reportable-disease list, this is seeded from
data/notifiable_diseases.json — see scripts/build_disease_vocabulary.py.
"""

import json
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.gazetteer import Gazetteer

# Cached because the vocabulary changes about never, and rebuilding it per
# extraction call would mean a database round trip (region) or file read
# (disease) per report.
_region_gazetteer_cache: Optional[Gazetteer] = None
_disease_gazetteer_cache: Optional[Gazetteer] = None
_vaccine_gazetteer_cache: Optional[Gazetteer] = None
_lab_test_gazetteer_cache: Optional[Gazetteer] = None
_specimen_type_gazetteer_cache: Optional[Gazetteer] = None

_DISEASE_VOCAB_PATH = Path(__file__).resolve().parents[2] / "data" / "notifiable_diseases.json"
_VACCINE_VOCAB_PATH = Path(__file__).resolve().parents[2] / "data" / "vaccines.json"
_LAB_TEST_VOCAB_PATH = Path(__file__).resolve().parents[2] / "data" / "lab_tests.json"
_SPECIMEN_TYPE_VOCAB_PATH = Path(__file__).resolve().parents[2] / "data" / "specimen_types.json"
_ICD10_LOOKUP_PATH = Path(__file__).resolve().parents[2] / "data" / "icd10_codes.json"
_LOINC_LOOKUP_PATH = Path(__file__).resolve().parents[2] / "data" / "loinc_codes.json"
_CVX_LOOKUP_PATH = Path(__file__).resolve().parents[2] / "data" / "cvx_codes.json"

_icd10_lookup_cache: Optional[Dict[str, str]] = None
_loinc_lookup_cache: Optional[Dict[str, dict]] = None
_cvx_lookup_cache: Optional[Dict[str, dict]] = None


def load_region_gazetteer(db: Session, aliases: Optional[Dict[str, str]] = None,
                          refresh: bool = False) -> Gazetteer:
    """
    Build (or return the cached) region vocabulary for this deployment.

    Returns an empty Gazetteer if the region table isn't populated — callers
    treat that as "no vocabulary configured" and fall back to the NER model,
    so a fresh install with no reference data still works.
    """
    global _region_gazetteer_cache

    if _region_gazetteer_cache is not None and not refresh:
        return _region_gazetteer_cache

    try:
        rows = db.execute(
            text("SELECT DISTINCT region FROM population_strata ORDER BY region")
        ).scalars().all()
    except Exception:
        rows = []

    _region_gazetteer_cache = Gazetteer(rows, aliases=aliases)
    return _region_gazetteer_cache


def load_disease_gazetteer(aliases: Optional[Dict[str, str]] = None,
                           refresh: bool = False) -> Gazetteer:
    """
    Build (or return the cached) notifiable-disease vocabulary.

    Returns an empty Gazetteer if data/notifiable_diseases.json is missing,
    so a fresh install still works and extraction falls back to the NER
    model entirely — same fail-safe behaviour as load_region_gazetteer.
    """
    global _disease_gazetteer_cache

    if _disease_gazetteer_cache is not None and not refresh:
        return _disease_gazetteer_cache

    try:
        terms = json.loads(_DISEASE_VOCAB_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        terms = []

    _disease_gazetteer_cache = Gazetteer(terms, aliases=aliases)
    return _disease_gazetteer_cache


def clear_cache() -> None:
    """Call after changing the region reference data, and in tests."""
    global _region_gazetteer_cache
    _region_gazetteer_cache = None


def clear_disease_cache() -> None:
    """Call after changing the disease reference data, and in tests."""
    global _disease_gazetteer_cache
    _disease_gazetteer_cache = None


def load_icd10_lookup(refresh: bool = False) -> Dict[str, str]:
    """
    Build (or return the cached) disease-name -> ICD-10 code lookup, from
    data/icd10_codes.json.

    Deliberately separate from load_disease_gazetteer(): the gazetteer
    drives NAME MATCHING during extraction (unaffected by this file
    existing or not), while this lookup is only consulted at SAVE time to
    populate icd10_code once a disease name is already matched. Keeping
    them separate means a mistake in the code mapping can never break
    extraction itself.

    Skips '_comment' and any '*_flag' keys — the flag entries are notes
    for a human reviewing the mapping (see icd10_codes.json), not disease
    names to look up. Returns an empty dict (not an error) if the file is
    missing or malformed, so icd10_code is simply left unpopulated rather
    than breaking saves — same fail-safe pattern as the other loaders here.
    """
    global _icd10_lookup_cache

    if _icd10_lookup_cache is not None and not refresh:
        return _icd10_lookup_cache

    try:
        raw = json.loads(_ICD10_LOOKUP_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}

    _icd10_lookup_cache = {
        k: v for k, v in raw.items()
        if k != "_comment" and not k.endswith("_flag")
    }
    return _icd10_lookup_cache


def load_loinc_lookup(refresh: bool = False) -> Dict[str, dict]:
    """
    Build (or return the cached) lab-test-name -> LOINC mapping, from
    data/loinc_codes.json.

    Unlike load_icd10_lookup(), each entry here is a small object, not
    just a code string:
        {"loinc": "<code>" | null, "status": "<mapping status>", "notes": "<why>"}

    This richer shape exists because LOINC codes are specimen+method
    specific in a way ICD-10 codes aren't, and several of the 71 lab
    tests genuinely don't have a single clean code -- deliberately
    reviewed and decided per-test by Dr. Sameh rather than defaulted.
    "loinc" is null for entries with no usable code at all (e.g.
    Poliovirus Stool PCR -- the only available code is a CULTURE method,
    which would be a real method mismatch, not just a granularity
    compromise; Leprosy Skin Biopsy -- histopathology, not a discrete
    lab analyte; Hantavirus IgM Serology -- the only code found is
    Sin-Nombre-subtype-specific, and defaulting to it would silently
    narrow every case to one viral subtype without evidence).

    Mapping status values (see loinc_codes.json for the full picture):
    EXACT, ACCEPTABLE_GENERIC_SPECIMEN, ACCEPTABLE_GENUS_LEVEL, PROXY,
    COMPOSITE, NO_DIRECT_LOINC, REJECTED_MISMATCH.

    Same fail-safe pattern as load_icd10_lookup(): a missing or
    malformed file returns an empty dict rather than raising, so
    test_code is simply left unpopulated rather than breaking saves.
    """
    global _loinc_lookup_cache

    if _loinc_lookup_cache is not None and not refresh:
        return _loinc_lookup_cache

    try:
        raw = json.loads(_LOINC_LOOKUP_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}

    _loinc_lookup_cache = raw
    return _loinc_lookup_cache


def get_loinc_code(test_name: str) -> Optional[str]:
    """
    Convenience helper for the save endpoint: returns just the LOINC
    code string for a test name, or None if there isn't a usable one
    (either the test isn't in loinc_codes.json at all, or it's there
    with "loinc": null -- see load_loinc_lookup() docstring for why
    that happens deliberately for a few tests).
    """
    entry = load_loinc_lookup().get(test_name)
    return entry["loinc"] if entry else None


def load_cvx_lookup(refresh: bool = False) -> Dict[str, dict]:
    """
    Build (or return the cached) vaccine-name -> CVX mapping, from
    data/cvx_codes.json.

    Same shape and reasoning as load_loinc_lookup(): each entry is a
    small object, not just a code string --
        {"cvx": "<code>", "status": "<mapping status>", "notes": "<why>"}
    -- because several vaccines have more than one clinically valid CVX
    code for different formulations/valencies/brands, deliberately
    reviewed and decided per-vaccine by Dr. Sameh rather than defaulted.

    Mapping status values (see cvx_codes.json for the full picture):
    EXACT, ACCEPTABLE_GENERIC_FORMULATION.

    Same fail-safe pattern as load_icd10_lookup() and load_loinc_lookup():
    a missing or malformed file returns an empty dict rather than
    raising, so vaccine_code is simply left unpopulated rather than
    breaking saves.
    """
    global _cvx_lookup_cache

    if _cvx_lookup_cache is not None and not refresh:
        return _cvx_lookup_cache

    try:
        raw = json.loads(_CVX_LOOKUP_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}

    _cvx_lookup_cache = raw
    return _cvx_lookup_cache


def get_cvx_code(vaccine_name: str) -> Optional[str]:
    """
    Convenience helper for the save endpoint: returns just the CVX code
    string for a vaccine name, or None if the vaccine isn't in
    cvx_codes.json at all -- see load_cvx_lookup() docstring for the
    entry shape.
    """
    entry = load_cvx_lookup().get(vaccine_name)
    return entry["cvx"] if entry else None


def load_vaccine_gazetteer(aliases: Optional[Dict[str, str]] = None,
                          refresh: bool = False) -> Gazetteer:
    """
    Build (or return the cached) vaccine-name vocabulary for the
    Immunization report type.

    Unlike the disease vocabulary (seeded from synthetic ground truth as a
    placeholder), this one comes from a REAL source: the Kuwait Ministry
    of Health's 2025 Childhood Immunization Schedule — data/vaccines.json.
    `aliases` isn't populated yet; add entries here once real report
    phrasing shows which shorthand terms ("Rota" vs "Rotavirus", "HBV" vs
    "Hepatitis B") actually need mapping, the same way region/disease
    aliases would be — don't guess ahead of the data.

    Returns an empty Gazetteer if the file is missing, so extraction falls
    back to the NER model entirely — same fail-safe behaviour as the
    other two gazetteers.
    """
    global _vaccine_gazetteer_cache

    if _vaccine_gazetteer_cache is not None and not refresh:
        return _vaccine_gazetteer_cache

    try:
        terms = json.loads(_VACCINE_VOCAB_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        terms = []

    _vaccine_gazetteer_cache = Gazetteer(terms, aliases=aliases)
    return _vaccine_gazetteer_cache


def clear_vaccine_cache() -> None:
    """Call after changing the vaccine reference data, and in tests."""
    global _vaccine_gazetteer_cache
    _vaccine_gazetteer_cache = None


def load_lab_test_gazetteer(aliases: Optional[Dict[str, str]] = None,
                            refresh: bool = False) -> Gazetteer:
    """
    Build (or return the cached) lab-test vocabulary for the Laboratory
    report type — data/lab_tests.json, a synthetic placeholder (like the
    disease gazetteer) covering the panel of tests realistic for this
    project's 10 tracked diseases. A real deployment would replace this
    with its own test catalogue.
    """
    global _lab_test_gazetteer_cache

    if _lab_test_gazetteer_cache is not None and not refresh:
        return _lab_test_gazetteer_cache

    try:
        terms = json.loads(_LAB_TEST_VOCAB_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        terms = []

    _lab_test_gazetteer_cache = Gazetteer(terms, aliases=aliases)
    return _lab_test_gazetteer_cache


def clear_lab_test_cache() -> None:
    global _lab_test_gazetteer_cache
    _lab_test_gazetteer_cache = None


def load_specimen_type_gazetteer(aliases: Optional[Dict[str, str]] = None,
                                 refresh: bool = False) -> Gazetteer:
    """Same pattern as load_lab_test_gazetteer, for specimen types."""
    global _specimen_type_gazetteer_cache

    if _specimen_type_gazetteer_cache is not None and not refresh:
        return _specimen_type_gazetteer_cache

    try:
        terms = json.loads(_SPECIMEN_TYPE_VOCAB_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        terms = []

    _specimen_type_gazetteer_cache = Gazetteer(terms, aliases=aliases)
    return _specimen_type_gazetteer_cache


def clear_specimen_type_cache() -> None:
    global _specimen_type_gazetteer_cache
    _specimen_type_gazetteer_cache = None
