"""
Lightweight report-type detection: given raw report text, guesses which
report type it is (Notifiable Disease vs Immunization today; more report
types add another entry to SIGNAL_KEYWORDS and another gazetteer check
here as they're built).

Deliberately NOT a model. Reuses the SAME closed-vocabulary gazetteers
already built for extraction (disease names, vaccine names) — if a
report mentions two known vaccines and zero known diseases, it's an
immunization report; the extraction pipeline already knows this
vocabulary, so detection gets it for free instead of needing a
classifier trained separately.

This is a best-effort heuristic, not a certainty: real-world documents
can mention a disease name inside an immunization report (e.g. "given
for prevention of Hepatitis A") or vice versa. That's exactly why the
UI surfaces the detected type as a suggestion the person confirms or
overrides, never as a silent, unreviewable decision.
"""

import re
from typing import Dict, Optional, Tuple

from app.services.gazetteer import Gazetteer

# Structural words each report type's own generator uses across every
# voice (structured/narrative/shorthand) — a secondary signal alongside
# gazetteer term matches, so detection isn't solely dependent on the
# specific disease/vaccine name matching this deployment's known lists.
_DISEASE_SIGNAL_WORDS = [
    "notifiable", "diagnosis", "confirmed", "suspected", "probable",
    "onset", "lab-confirmed", "case report",
]
_IMMUNIZATION_SIGNAL_WORDS = [
    "vaccine", "vaccination", "dose", "administered", "immunization",
    "aefi", "adverse event following immunization", "booster",
]

_WORD_BOUNDARY = r"(?<!\w){}(?!\w)"


def _count_signal_words(text: str, words) -> int:
    lowered = text.lower()
    return sum(
        1 for w in words
        if re.search(_WORD_BOUNDARY.format(re.escape(w)), lowered)
    )


def detect_report_type(
    text: str,
    disease_gazetteer: Optional[Gazetteer] = None,
    vaccine_gazetteer: Optional[Gazetteer] = None,
) -> Tuple[str, Dict[str, int]]:
    """
    Returns (detected_type, scores) where detected_type is
    "notifiable" | "immunization" | "unknown", and scores shows the raw
    numbers behind the call — surfaced to the reviewer so "why did it
    guess that" is never a mystery.

    Gazetteer term matches count double relative to signal words: an
    exact match against a known disease/vaccine name is stronger
    evidence than a generic word like "dose" appearing once.
    """
    disease_terms = disease_gazetteer.find_all(text) if disease_gazetteer else []
    vaccine_terms = vaccine_gazetteer.find_all(text) if vaccine_gazetteer else []

    disease_score = 2 * len(disease_terms) + _count_signal_words(text, _DISEASE_SIGNAL_WORDS)
    immunization_score = 2 * len(vaccine_terms) + _count_signal_words(text, _IMMUNIZATION_SIGNAL_WORDS)

    scores = {
        "notifiable": disease_score,
        "immunization": immunization_score,
        "matched_diseases": disease_terms,
        "matched_vaccines": vaccine_terms,
    }

    if disease_score == 0 and immunization_score == 0:
        return "unknown", scores
    if disease_score == immunization_score:
        return "unknown", scores
    return ("notifiable" if disease_score > immunization_score else "immunization"), scores
