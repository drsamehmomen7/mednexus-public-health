"""
Shared helpers for building the per-field confidence report returned
alongside every extracted report type.

Kept in one place so the shape of a confidence entry (source, score,
optional note) stays identical across report types — a reviewer looking
at any report type's output should see the same structure.
"""

from typing import Optional

from app.services.ner_client import ExtractedEntity


def model_confidence(entity: Optional[ExtractedEntity], negated_count: int = 0) -> dict:
    """
    Build a confidence entry for a model (NER)-derived field.

    `negated_count` > 0 means one or more matching mentions existed but
    were excluded as negated (e.g. "ruled out") — surfaced as a note so
    that information isn't silently lost.
    """
    if entity is None:
        return {"source": "model", "score": None, "note": "not found in text"}

    entry = {"source": "model", "score": entity.score}
    if negated_count:
        entry["note"] = (
            f"{negated_count} mention(s) excluded as negated "
            "(e.g. 'ruled out') — review original text"
        )
    return entry


def rule_based_confidence() -> dict:
    """
    Build a confidence entry for a field derived by fixed rules (dates,
    age, keyword matching) rather than a probabilistic model. There is no
    meaningful "score" for these — reporting one would imply a precision
    that isn't there.
    """
    return {"source": "rule_based", "score": None}
