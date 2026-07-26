"""
Extraction orchestrator for Notifiable Disease reports.

Hybrid strategy (matches the project's rules + AI philosophy):
- Dates and ages: rule-based (deterministic, auditable) — see rule_based.py
- Diagnosis status (suspected/probable/confirmed): closed vocabulary,
  handled with keyword rules rather than a model — more reliable for a
  fixed small set of values than asking an NER model to classify it.
- Disease name and region: open vocabulary, extracted via OpenMed's
  zero-shot NER — see ner_client.py

The NER call is dependency-injected (`ner_fn` parameter) so this function,
and its tests, do not require the real OpenMed/GLiNER install to run.
"""

from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from app.schemas.notifiable_disease import DiagnosisStatus, NotifiableDiseaseCase
from app.services.ner_client import ExtractedEntity, extract_entities
from app.services.rule_based import extract_age, extract_first_date

NER_LABELS = ["disease", "region", "facility"]

# Fields not in this dict were derived by fixed rules (dates, age, keyword
# matching), not a probabilistic model — there is no "confidence score" for
# those in the same sense, so the API reports them as "rule_based" rather
# than inventing a fake number.
RULE_BASED_FIELDS = {"report_date", "patient_age", "diagnosis_status", "lab_confirmed"}

_STATUS_KEYWORDS = {
    DiagnosisStatus.CONFIRMED: ["confirmed", "positive", "lab-confirmed"],
    DiagnosisStatus.PROBABLE: ["probable", "likely"],
    DiagnosisStatus.SUSPECTED: ["suspected", "possible", "query"],
}

# Phrases that mean "the following diagnosis does NOT apply" — a disease
# mention immediately after one of these must never be treated as the
# patient's diagnosis. This was a real bug: "Ruled out dengue... Suspected
# typhoid" extracted "dengue" (the excluded disease) as disease_name.
_NEGATION_CUES = [
    "ruled out", "rule out", "r/o", "no evidence of", "excluded",
    "negative for", "denies", "not consistent with",
]
_NEGATION_WINDOW_CHARS = 40


def _first_entity(entities: List[ExtractedEntity], label: str) -> Optional[ExtractedEntity]:
    for entity in entities:
        if entity.label == label:
            return entity
    return None


def _is_negated(text: str, entity: ExtractedEntity) -> bool:
    """
    Check whether `entity` is immediately preceded by a negation cue
    (e.g. "ruled out dengue"). Requires the entity's character offset —
    if the NER backend didn't provide start/end, this conservatively
    returns False (no info means we cannot claim it's negated).
    """
    if entity.start is None:
        return False
    window_start = max(0, entity.start - _NEGATION_WINDOW_CHARS)
    preceding = text[window_start:entity.start].lower()
    return any(cue in preceding for cue in _NEGATION_CUES)


def _first_non_negated_entity(
    entities: List[ExtractedEntity], label: str, text: str
) -> Tuple[Optional[ExtractedEntity], int]:
    """
    Return the first entity of `label` that is NOT preceded by a negation
    cue, plus a count of how many matching entities were skipped because
    they WERE negated (surfaced in the confidence report so a reviewer
    can see a ruled-out mention existed, rather than it silently vanishing).
    """
    skipped = 0
    for entity in entities:
        if entity.label != label:
            continue
        if _is_negated(text, entity):
            skipped += 1
            continue
        return entity, skipped
    return None, skipped


def _infer_diagnosis_status(text: str) -> DiagnosisStatus:
    lowered = text.lower()

    # A pending or awaited result means the patient's OWN case is not yet
    # confirmed — this must be checked before the keyword scan below,
    # because a report can say "confirmed" only about a contact's case
    # ("contact w/ confirmed case"), not the patient being described.
    if any(kw in lowered for kw in ["pending", "awaiting result", "results awaited"]):
        return DiagnosisStatus.SUSPECTED

    for status, keywords in _STATUS_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return status
    # Default to the most cautious option when no keyword is found —
    # a human reviewer should confirm rather than the system assuming
    # a stronger status than the text supports.
    return DiagnosisStatus.SUSPECTED


def _infer_lab_confirmed(text: str) -> bool:
    lowered = text.lower()
    if "pending" in lowered:
        # A test that was sent but not resulted yet is not a lab
        # confirmation, even if "PCR" or "confirmed" appear elsewhere
        # in the same sentence (e.g. describing a contact's case).
        return False
    return "confirmed" in lowered or "pcr" in lowered


def extract_notifiable_disease_with_confidence(
    text: str,
    ner_fn: Callable[..., List[ExtractedEntity]] = extract_entities,
) -> Tuple[NotifiableDiseaseCase, Dict[str, dict]]:
    """
    Extract a NotifiableDiseaseCase, plus a per-field confidence report.

    The confidence report exists for exactly one reason: a human reviewer
    should be able to see which fields the model is unsure about (and which
    fields are not model-derived at all) before the record is trusted for
    statistics or export. This is not optional polish — see the project's
    de-identification tool discussion on human-in-the-loop review.
    """
    entities = ner_fn(text, labels=NER_LABELS, domain="biomedical")

    # Disease name specifically uses negation-aware selection: picking a
    # "ruled out" disease as the diagnosis is a clinically dangerous error,
    # not just a display inconvenience. Region/facility don't get this yet
    # (negation is far rarer for those) — see decisions log.
    disease_entity, negated_disease_count = _first_non_negated_entity(entities, "disease", text)
    region_entity = _first_entity(entities, "region")
    facility_entity = _first_entity(entities, "facility")

    report_date = extract_first_date(text)
    patient_age = extract_age(text)

    case = NotifiableDiseaseCase(
        disease_name=(disease_entity.text if disease_entity else "Unknown"),
        diagnosis_status=_infer_diagnosis_status(text),
        report_date=report_date or date.today(),
        patient_age=patient_age,
        region=(region_entity.text if region_entity else "Unknown"),
        facility_name=(facility_entity.text if facility_entity else None),
        lab_confirmed=_infer_lab_confirmed(text),
        source_excerpt=text[:200],
    )

    disease_confidence = (
        {"source": "model", "score": disease_entity.score}
        if disease_entity else {"source": "model", "score": None, "note": "not found in text"}
    )
    if negated_disease_count:
        disease_confidence["note"] = (
            f"{negated_disease_count} mention(s) excluded as negated "
            "(e.g. 'ruled out') — review original text"
        )

    confidence = {
        "disease_name": disease_confidence,
        "region": (
            {"source": "model", "score": region_entity.score}
            if region_entity else {"source": "model", "score": None, "note": "not found in text"}
        ),
        "facility_name": (
            {"source": "model", "score": facility_entity.score}
            if facility_entity else {"source": "model", "score": None, "note": "not found in text"}
        ),
        "report_date": {"source": "rule_based", "score": None},
        "patient_age": {"source": "rule_based", "score": None},
        "diagnosis_status": {"source": "rule_based", "score": None},
        "lab_confirmed": {"source": "rule_based", "score": None},
    }

    return case, confidence


def extract_notifiable_disease(
    text: str,
    ner_fn: Callable[..., List[ExtractedEntity]] = extract_entities,
) -> NotifiableDiseaseCase:
    """
    Extract a NotifiableDiseaseCase from raw report text.

    Thin wrapper kept for backwards compatibility (existing tests and
    callers use this signature). For confidence scores per field, use
    extract_notifiable_disease_with_confidence instead.
    """
    case, _confidence = extract_notifiable_disease_with_confidence(text, ner_fn=ner_fn)
    return case
