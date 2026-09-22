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


def rule_based_confidence(found: Optional[bool] = None) -> dict:
    """
    Build a confidence entry for a field derived by fixed rules (dates,
    age, keyword matching) rather than a probabilistic model. There is no
    meaningful "score" for these — reporting one would imply a precision
    that isn't there.

    `found` is for the small set of fields that can silently fall back to
    a fabricated default when parsing fails — e.g. a required date field
    (report_date, administration_date, result_date) defaulting to
    date.today() instead of being left blank, because the schema doesn't
    allow None there. Pass found=True when the rule-based regex actually
    matched something in the text, found=False when the value being
    returned is that fabricated fallback — see needs_review() below for
    why this distinction has to exist. Omit it (the default) for
    rule-based fields with no such fallback, where a value is either
    genuinely parsed or left as plain Python None and the distinction
    doesn't apply.
    """
    entry = {"source": "rule_based", "score": None}
    if found is not None:
        entry["found"] = found
    return entry


LOW_CONFIDENCE_THRESHOLD = 0.6


def needs_review(confidence: dict, threshold: float = LOW_CONFIDENCE_THRESHOLD) -> bool:
    """
    True if any model-derived field is missing or scored below
    `threshold`, OR any rule-based field is explicitly marked
    found=False — a value that had to be fabricated (see
    rule_based_confidence()) because the underlying regex found nothing,
    rather than a genuinely-parsed rule-based result. Rule-based fields
    with no `found` key at all, or found=True, never trigger this on
    their own — only actual low-confidence model output, or a
    known-fabricated rule-based value, does. This is the single source
    of truth for the "needed_review" flag stored alongside every saved
    record, so the frontend badge logic and the database flag can never
    silently drift apart.
    """
    for entry in confidence.values():
        source = entry.get("source")
        if source == "rule_based":
            if entry.get("found") is False:
                return True
            continue
        if source != "model":
            continue
        score = entry.get("score")
        if score is None or score < threshold:
            return True
    return False
