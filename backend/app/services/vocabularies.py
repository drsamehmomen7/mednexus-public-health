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

_DISEASE_VOCAB_PATH = Path(__file__).resolve().parents[2] / "data" / "notifiable_diseases.json"
_VACCINE_VOCAB_PATH = Path(__file__).resolve().parents[2] / "data" / "vaccines.json"


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
