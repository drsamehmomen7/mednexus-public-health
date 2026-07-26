"""
Shared, report-type-agnostic entity selection helpers.

Used by every report type's extraction module (notifiable disease,
immunization, laboratory, ...) — this logic is not specific to any one
schema, so it lives here once instead of being copy-pasted per type.
"""

from typing import List, Optional, Tuple

from app.services.ner_client import ExtractedEntity

# Phrases that mean "the following mention does NOT apply to this patient".
# An entity immediately after one of these must never be selected as the
# patient's actual finding. Real bug this fixed: "Ruled out dengue...
# Suspected typhoid" extracted "dengue" (the excluded disease).
NEGATION_CUES = [
    "ruled out", "rule out", "r/o", "no evidence of", "excluded",
    "negative for", "denies", "not consistent with",
]
NEGATION_WINDOW_CHARS = 40


def first_entity(entities: List[ExtractedEntity], label: str) -> Optional[ExtractedEntity]:
    """Return the first entity matching `label`, with no negation check."""
    for entity in entities:
        if entity.label == label:
            return entity
    return None


def is_negated(text: str, entity: ExtractedEntity) -> bool:
    """
    Check whether `entity` is immediately preceded by a negation cue.

    Requires the entity's character offset — if the NER backend didn't
    provide start/end, this conservatively returns False (no position
    info means we cannot claim it's negated).
    """
    if entity.start is None:
        return False
    window_start = max(0, entity.start - NEGATION_WINDOW_CHARS)
    preceding = text[window_start:entity.start].lower()
    return any(cue in preceding for cue in NEGATION_CUES)


def first_non_negated_entity(
    entities: List[ExtractedEntity], label: str, text: str
) -> Tuple[Optional[ExtractedEntity], int]:
    """
    Return the first entity of `label` that is NOT preceded by a negation
    cue, plus a count of how many matching entities were skipped because
    they WERE negated (surface this in the confidence report so a ruled-out
    mention is visible to a reviewer rather than silently disappearing).
    """
    skipped = 0
    for entity in entities:
        if entity.label != label:
            continue
        if is_negated(text, entity):
            skipped += 1
            continue
        return entity, skipped
    return None, skipped
