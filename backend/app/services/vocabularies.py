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
"""

from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.gazetteer import Gazetteer

# Cached because the vocabulary changes about never, and rebuilding it per
# extraction call would mean a database round trip per report.
_region_gazetteer_cache: Optional[Gazetteer] = None


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
        # No reference table yet (fresh database, or running before the
        # population scripts). Not an error — just means no vocabulary.
        rows = []

    _region_gazetteer_cache = Gazetteer(rows, aliases=aliases)
    return _region_gazetteer_cache


def clear_cache() -> None:
    """Call after changing the region reference data, and in tests."""
    global _region_gazetteer_cache
    _region_gazetteer_cache = None
