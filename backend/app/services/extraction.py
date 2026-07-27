"""
Extraction orchestrator for Notifiable Disease reports.

Hybrid strategy (matches the project's rules + AI philosophy):
- Dates and ages: rule-based (deterministic, auditable) — see rule_based.py
- Diagnosis status (suspected/probable/confirmed): closed vocabulary,
  handled with keyword rules rather than a model — more reliable for a
  fixed small set of values than asking an NER model to classify it.
- Disease name and region: open vocabulary, extracted via OpenMed's
  zero-shot NER — see ner_client.py
- Negation-aware entity selection and confidence-report building are
  shared, report-type-agnostic helpers — see entity_selection.py and
  confidence.py. Other report types should reuse those, not copy them.

The NER call is dependency-injected (`ner_fn` parameter) so this function,
and its tests, do not require the real OpenMed/GLiNER install to run.
"""

from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from app.schemas.notifiable_disease import DiagnosisStatus, NotifiableDiseaseCase
from app.services.confidence import model_confidence, rule_based_confidence
from app.services.entity_selection import first_entity, first_non_negated_entity
from app.services.gazetteer import Gazetteer
from app.services.ner_client import ExtractedEntity, extract_entities
from app.services.rule_based import extract_age, extract_first_date

NER_LABELS = ["disease", "region", "facility"]

# Fields derived by fixed rules, not a model — used to build their
# confidence entries below without repeating each field name twice.
RULE_BASED_FIELDS = ("report_date", "patient_age", "diagnosis_status", "lab_confirmed")

_STATUS_KEYWORDS = {
    DiagnosisStatus.CONFIRMED: ["confirmed", "positive", "lab-confirmed"],
    DiagnosisStatus.PROBABLE: ["probable", "likely"],
    DiagnosisStatus.SUSPECTED: ["suspected", "possible", "query"],
}


def _infer_diagnosis_status(text: str) -> DiagnosisStatus:
    lowered = text.lower()

    has_pending = any(
        kw in lowered
        for kw in ["pending", "awaiting result", "results awaited", "awaiting confirmation"]
    )

    # Structured report templates print a heading like "Suspected condition:"
    # for EVERY case, including confirmed ones — the actual classification
    # appears further down ("Diagnosis confirmed"). Treating the heading as a
    # classification made every templated report come back suspected, which
    # is exactly the kind of error that looks plausible and stays hidden.
    form_labels = [
        "suspected condition", "suspected disease", "suspected diagnosis",
        "probable condition", "probable diagnosis", "condition suspected",
    ]
    for label in form_labels:
        lowered = lowered.replace(label, " ")

    # Check explicit classifications first. A clinician who wrote "probable"
    # or "suspected" has already made a cautious judgement, and a pending lab
    # result doesn't contradict it — "probable case, results pending" is a
    # probable case, not a suspected one.
    for status in (DiagnosisStatus.PROBABLE, DiagnosisStatus.SUSPECTED):
        if any(keyword in lowered for keyword in _STATUS_KEYWORDS[status]):
            return status

    # "Confirmed" is the one status a pending result DOES override: the word
    # may belong to a contact's case ("contact w/ confirmed case") rather
    # than the patient's own, and claiming confirmation the text doesn't
    # support is the dangerous direction to err in.
    if not has_pending and any(
        keyword in lowered for keyword in _STATUS_KEYWORDS[DiagnosisStatus.CONFIRMED]
    ):
        return DiagnosisStatus.CONFIRMED

    # Default to the most cautious option when no keyword is found —
    # a human reviewer should confirm rather than the system assuming
    # a stronger status than the text supports.
    return DiagnosisStatus.SUSPECTED


def _infer_lab_confirmed(text: str) -> bool:
    lowered = text.lower()
    if any(
        kw in lowered
        for kw in ["pending", "awaiting result", "results awaited", "awaiting confirmation"]
    ):
        # A test that was sent but not resulted yet is not a lab
        # confirmation, even if "PCR" or "confirmed" appear elsewhere
        # in the same sentence (e.g. describing a contact's case).
        return False

    # Reports rarely use one fixed phrase for a positive result. Real notes
    # say "confirming X", "culture +ve", "serology positive" — none of which
    # contain the literal word "confirmed". Matching only that word silently
    # dropped genuine lab confirmations.
    #
    # The order matters: negated phrases are stripped FIRST, because several
    # of them contain a positive marker as a substring ("non-reactive" holds
    # "reactive", "not confirmed" holds "confirmed"). Scanning for positives
    # before removing these would read a negative result as a positive one.
    negated_phrases = [
        "non-reactive", "nonreactive", "not confirmed", "not positive",
        "negative", "-ve", "ruled out", "excluded",
    ]
    for phrase in negated_phrases:
        lowered = lowered.replace(phrase, " ")

    positive_markers = ["confirmed", "confirming", "+ve", "positive", "reactive"]
    if any(marker in lowered for marker in positive_markers):
        return True

    return "pcr" in lowered


def extract_notifiable_disease_with_confidence(
    text: str,
    ner_fn: Callable[..., List[ExtractedEntity]] = extract_entities,
    region_gazetteer: Optional[Gazetteer] = None,
) -> Tuple[NotifiableDiseaseCase, Dict[str, dict]]:
    """
    Extract a NotifiableDiseaseCase, plus a per-field confidence report.

    The confidence report exists for exactly one reason: a human reviewer
    should be able to see which fields the model is unsure about (and which
    fields are not model-derived at all) before the record is trusted for
    statistics or export. This is not optional polish — see the project's
    de-identification tool discussion on human-in-the-loop review.

    `region_gazetteer` is optional and holds the deployment's known list of
    administrative regions. When supplied it takes precedence over the NER
    model for the region field, because region is a CLOSED vocabulary and
    exact matching beats zero-shot guessing on those. When it isn't supplied
    the behaviour is unchanged, so this function still works standalone and
    stays free of any country-specific knowledge — the list is data passed
    in by the caller, never hardcoded here.
    """
    entities = ner_fn(text, labels=NER_LABELS, domain="biomedical")

    # Disease name specifically uses negation-aware selection: picking a
    # "ruled out" disease as the diagnosis is a clinically dangerous error,
    # not just a display inconvenience. Region/facility don't get this yet
    # (negation is far rarer for those) — see decisions log.
    disease_entity, negated_disease_count = first_non_negated_entity(entities, "disease", text)
    region_entity = first_entity(entities, "region")
    facility_entity = first_entity(entities, "facility")

    # Region: prefer an exact match against the known vocabulary, and fall
    # back to whatever the model found. Reports write the location as
    # "Ardiya Clinic, Farwaniya", and the model frequently attributed the
    # whole phrase to the facility and returned no region at all.
    gazetteer_region = region_gazetteer.find(text) if region_gazetteer else None

    report_date = extract_first_date(text)
    patient_age = extract_age(text)

    case = NotifiableDiseaseCase(
        disease_name=(disease_entity.text if disease_entity else "Unknown"),
        diagnosis_status=_infer_diagnosis_status(text),
        report_date=report_date or date.today(),
        patient_age=patient_age,
        region=(gazetteer_region or (region_entity.text if region_entity else "Unknown")),
        facility_name=(facility_entity.text if facility_entity else None),
        lab_confirmed=_infer_lab_confirmed(text),
        source_excerpt=text[:200],
    )

    confidence = {
        "disease_name": model_confidence(disease_entity, negated_disease_count),
        # A gazetteer hit is an exact match against a known list, not a
        # probabilistic guess — report it as such rather than attaching a
        # model score it didn't come from.
        "region": (
            {"source": "gazetteer", "found": True}
            if gazetteer_region
            else model_confidence(region_entity)
        ),
        "facility_name": model_confidence(facility_entity),
        **{field: rule_based_confidence() for field in RULE_BASED_FIELDS},
    }

    return case, confidence


def extract_notifiable_disease(
    text: str,
    ner_fn: Callable[..., List[ExtractedEntity]] = extract_entities,
    region_gazetteer: Optional[Gazetteer] = None,
) -> NotifiableDiseaseCase:
    """
    Extract a NotifiableDiseaseCase from raw report text.

    Thin wrapper kept for backwards compatibility (existing tests and
    callers use this signature). For confidence scores per field, use
    extract_notifiable_disease_with_confidence instead.
    """
    case, _confidence = extract_notifiable_disease_with_confidence(
        text, ner_fn=ner_fn, region_gazetteer=region_gazetteer
    )
    return case
