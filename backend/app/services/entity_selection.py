"""
Shared, report-type-agnostic entity selection helpers.

Used by every report type's extraction module (notifiable disease,
immunization, laboratory, ...) — this logic is not specific to any one
schema, so it lives here once instead of being copy-pasted per type.
"""

import re
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


def _text_after_entity_in_same_sentence(text: str, entity) -> str:
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


def _text_before_entity_in_same_sentence(text: str, entity) -> str:
    """
    Text preceding the entity, truncated at the LAST sentence ending within
    the window, so a negation cue belonging to a DIFFERENT (earlier)
    statement can't be attributed to this entity. Symmetric to
    _text_after_entity_in_same_sentence above.

    Real bug this fixes: found by testing the disease gazetteer against
    actual synthetic reports, not by inspection. "Dengue fever was ruled
    out on negative testing. Influenza confirmed by PCR." — the un-bounded
    40-char preceding window for "Influenza" contained "ruled out" (which
    describes Dengue, the PREVIOUS sentence), so the confirmed diagnosis
    was incorrectly read as negated. This affects both the NER path and
    the gazetteer path, since both call is_negated().
    """
    if entity.start is None:
        return ""
    window_start = max(0, entity.start - NEGATION_WINDOW_CHARS)
    window = text[window_start:entity.start]
    last_ending = -1
    for i, char in enumerate(window):
        if char in SENTENCE_ENDINGS:
            last_ending = i
    return window[last_ending + 1:].lower()


def is_negated(text: str, entity) -> bool:
    """
    Check whether `entity` is negated — either by a cue immediately before
    it, within the same sentence ("ruled out dengue"), or by one following
    it within the same sentence ("dengue was ruled out").

    Works with anything exposing `.start`/`.end` (an ExtractedEntity, or the
    lightweight _GazetteerHit below) — requires the character offset; if
    it's missing, this conservatively returns False (no position info means
    we cannot claim it's negated).
    """
    if entity.start is None:
        return False

    preceding = _text_before_entity_in_same_sentence(text, entity)
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


class _GazetteerHit:
    """
    Minimal stand-in for ExtractedEntity so a gazetteer (closed-vocabulary)
    match can reuse is_negated() without duplicating its negation-window
    logic. Only the attributes is_negated actually reads.
    """
    __slots__ = ("text", "start", "end", "label")

    def __init__(self, text: str, start: int, end: int, label: str = "gazetteer"):
        self.text = text
        self.start = start
        self.end = end
        self.label = label


def _find_all_term_occurrences(text: str, terms: List[str]) -> List[Tuple[str, int, int]]:
    """
    Find every whole-word, case-insensitive occurrence of any `terms` entry
    in `text`, with TRUE character offsets into `text` itself.

    Gazetteer.find() deliberately normalizes text before matching (lowers,
    collapses whitespace) to make matching forgiving — but that means its
    offsets are into the NORMALIZED string, not the original, and can't be
    reused for negation-window checks. This does its own matching instead,
    directly against the original text, specifically to keep offsets
    trustworthy for is_negated().

    Longest terms are tried first so a multi-word disease name matches
    before a shorter substring of it would.
    """
    sorted_terms = sorted((t for t in terms if t and t.strip()), key=len, reverse=True)
    matches: List[Tuple[str, int, int]] = []
    for term in sorted_terms:
        pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
        for m in pattern.finditer(text):
            matches.append((term, m.start(), m.end()))
    matches.sort(key=lambda item: item[1])
    return matches


def first_non_negated_gazetteer_term(
    text: str, terms: List[str]
) -> Tuple[Optional[str], int]:
    """
    Return the first `terms` entry appearing in `text` that is NOT negated,
    plus a count of skipped negated mentions — the gazetteer equivalent of
    first_non_negated_entity, for closed-vocabulary fields (e.g. disease
    name) matched against a known list instead of NER labels.

    Real bug this fixes: without this check, a disease gazetteer would
    extract "dengue" from "Dengue was ruled out; suspected typhoid" just as
    readily as the un-gazetteered NER path used to.
    """
    skipped = 0
    for term, start, end in _find_all_term_occurrences(text, terms):
        hit = _GazetteerHit(term, start, end)
        if is_negated(text, hit):
            skipped += 1
            continue
        return term, skipped
    return None, skipped
