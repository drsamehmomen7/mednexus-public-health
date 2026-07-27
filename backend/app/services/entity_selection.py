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

# Cues that appear AFTER the entity instead of before it: "Hepatitis A was
# ruled out", "dengue serology negative". Checking only preceding text meant
# these reports had the excluded disease extracted as the diagnosis — the
# same clinically dangerous error, just phrased the other way round.
TRAILING_NEGATION_CUES = [
    "ruled out", "was ruled out", "excluded", "was excluded",
    "negative", "not detected", "was not detected", "unlikely",
]

NEGATION_WINDOW_CHARS = 40
# Trailing cues are only trusted within the entity's own sentence. Without
# that bound, "Measles confirmed. Rubella negative." would read the negation
# belonging to Rubella as negating Measles.
SENTENCE_ENDINGS = ".;\n"
TRAILING_WINDOW_CHARS = 60


def first_entity(entities: List[ExtractedEntity], label: str) -> Optional[ExtractedEntity]:
    """Return the first entity matching `label`, with no negation check."""
    for entity in entities:
        if entity.label == label:
            return entity
    return None


def _text_after_entity_in_same_sentence(text: str, entity: ExtractedEntity) -> str:
    """
    Text following the entity, truncated at the first sentence ending, so a
    negation belonging to the NEXT statement can't be attributed to this one.
    """
    start = entity.end if entity.end is not None else entity.start
    if start is None:
        return ""
    window = text[start:start + TRAILING_WINDOW_CHARS]
    for i, char in enumerate(window):
        if char in SENTENCE_ENDINGS:
            return window[:i].lower()
    return window.lower()


def is_negated(text: str, entity: ExtractedEntity) -> bool:
    """
    Check whether `entity` is negated — either by a cue immediately before
    it ("ruled out dengue") or by one following it within the same sentence
    ("dengue was ruled out").

    Requires the entity's character offset — if the NER backend didn't
    provide start/end, this conservatively returns False (no position
    info means we cannot claim it's negated).
    """
    if entity.start is None:
        return False

    window_start = max(0, entity.start - NEGATION_WINDOW_CHARS)
    preceding = text[window_start:entity.start].lower()
    if any(cue in preceding for cue in NEGATION_CUES):
        return True

    following = _text_after_entity_in_same_sentence(text, entity)
    return any(cue in following for cue in TRAILING_NEGATION_CUES)


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
