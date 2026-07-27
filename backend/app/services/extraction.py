"""
Extraction orchestrator for Notifiable Disease reports.

Hybrid strategy (matches the project's rules + AI philosophy):
- Dates and ages: rule-based (deterministic, auditable) — see rule_based.py
- Diagnosis status (suspected/probable/confirmed): closed vocabulary,
  handled with keyword rules rather than a model.
- Region AND disease name: closed vocabulary, matched via a gazetteer —
  see gazetteer.py / vocabularies.py. Disease was added after the
  500-report load showed disease_name at 84.8% vs 100% for every other
  gazetteer-backed field: GLiNER sometimes labels a symptom ("myalgia")
  as "disease", or finds no disease entity at all. Both fields fall back
  to OpenMed's zero-shot NER — see ner_client.py — only when no gazetteer
  is supplied or nothing in it matches. See docs/decisions-log.md.
- Negation-aware entity selection and confidence-report building are
  shared, report-type-agnostic helpers — see entity_selection.py and
  confidence.py. Other report types should reuse those, not copy them.

The NER call is dependency-injected (`ner_fn` parameter) so this function,
and its tests, do not require the real OpenMed/GLiNER install to run.
"""

from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from app.schemas.notifiable_disease import DiagnosisStatus, NotifiableDiseaseCase, PatientSex
from app.services.confidence import model_confidence, rule_based_confidence
from app.services.entity_selection import (
    first_entity,
    first_non_negated_entity,
    first_non_negated_gazetteer_term,
)
from app.services.gazetteer import Gazetteer
from app.services.ner_client import ExtractedEntity, extract_entities
from app.services.rule_based import extract_age, extract_first_date, extract_sex

NER_LABELS = ["disease", "region", "facility"]

RULE_BASED_FIELDS = ("report_date", "patient_age", "patient_sex", "diagnosis_status", "lab_confirmed")

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

    form_labels = [
        "suspected condition", "suspected disease", "suspected diagnosis",
        "probable condition", "probable diagnosis", "condition suspected",
    ]
    for label in form_labels:
        lowered = lowered.replace(label, " ")

    for status in (DiagnosisStatus.PROBABLE, DiagnosisStatus.SUSPECTED):
        if any(keyword in lowered for keyword in _STATUS_KEYWORDS[status]):
            return status

    if not has_pending and any(
        keyword in lowered for keyword in _STATUS_KEYWORDS[DiagnosisStatus.CONFIRMED]
    ):
        return DiagnosisStatus.CONFIRMED

    return DiagnosisStatus.SUSPECTED


def _infer_lab_confirmed(text: str) -> bool:
    lowered = text.lower()
    if any(
        kw in lowered
        for kw in ["pending", "awaiting result", "results awaited", "awaiting confirmation"]
    ):
        return False

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
    disease_gazetteer: Optional[Gazetteer] = None,
) -> Tuple[NotifiableDiseaseCase, Dict[str, dict]]:
    """
    Extract a NotifiableDiseaseCase, plus a per-field confidence report.

    `region_gazetteer` / `disease_gazetteer` are optional and hold this
    deployment's known regions / notifiable diseases. When supplied, each
    takes precedence over the NER model for its field, because both are
    CLOSED vocabularies and exact matching beats zero-shot guessing on
    those. When not supplied, behaviour is unchanged from the NER-only
    path, so this function still works standalone and stays free of any
    country-specific knowledge.
    """
    entities = ner_fn(text, labels=NER_LABELS, domain="biomedical")

    disease_entity, negated_disease_count = first_non_negated_entity(entities, "disease", text)
    region_entity = first_entity(entities, "region")
    facility_entity = first_entity(entities, "facility")

    gazetteer_region = region_gazetteer.find(text) if region_gazetteer else None

    gazetteer_disease, gazetteer_negated_count = (
        first_non_negated_gazetteer_term(text, disease_gazetteer.terms)
        if disease_gazetteer else (None, 0)
    )

    report_date = extract_first_date(text)
    patient_age = extract_age(text)
    patient_sex = extract_sex(text)

    case = NotifiableDiseaseCase(
        disease_name=(
            gazetteer_disease or (disease_entity.text if disease_entity else "Unknown")
        ),
        diagnosis_status=_infer_diagnosis_status(text),
        report_date=report_date or date.today(),
        patient_age=patient_age,
        patient_sex=(PatientSex(patient_sex) if patient_sex else PatientSex.UNKNOWN),
        region=(gazetteer_region or (region_entity.text if region_entity else "Unknown")),
        facility_name=(facility_entity.text if facility_entity else None),
        lab_confirmed=_infer_lab_confirmed(text),
        source_excerpt=text[:200],
    )

    confidence = {
        "disease_name": (
            {"source": "gazetteer", "found": True, "negated_skipped": gazetteer_negated_count}
            if gazetteer_disease
            else model_confidence(disease_entity, negated_disease_count)
        ),
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
    disease_gazetteer: Optional[Gazetteer] = None,
) -> NotifiableDiseaseCase:
    """
    Extract a NotifiableDiseaseCase from raw report text.

    Thin wrapper kept for backwards compatibility. For confidence scores
    per field, use extract_notifiable_disease_with_confidence instead.
    """
    case, _confidence = extract_notifiable_disease_with_confidence(
        text,
        ner_fn=ner_fn,
        region_gazetteer=region_gazetteer,
        disease_gazetteer=disease_gazetteer,
    )
    return case
