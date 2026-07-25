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
from typing import Callable, List, Optional

from app.schemas.notifiable_disease import DiagnosisStatus, NotifiableDiseaseCase
from app.services.ner_client import ExtractedEntity, extract_entities
from app.services.rule_based import extract_age, extract_first_date

NER_LABELS = ["disease", "region", "facility"]

_STATUS_KEYWORDS = {
    DiagnosisStatus.CONFIRMED: ["confirmed", "positive", "lab-confirmed"],
    DiagnosisStatus.PROBABLE: ["probable", "likely"],
    DiagnosisStatus.SUSPECTED: ["suspected", "possible", "query"],
}


def _first_entity_text(entities: List[ExtractedEntity], label: str) -> Optional[str]:
    for entity in entities:
        if entity.label == label:
            return entity.text
    return None


def _infer_diagnosis_status(text: str) -> DiagnosisStatus:
    lowered = text.lower()
    for status, keywords in _STATUS_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return status
    # Default to the most cautious option when no keyword is found —
    # a human reviewer should confirm rather than the system assuming
    # a stronger status than the text supports.
    return DiagnosisStatus.SUSPECTED


def extract_notifiable_disease(
    text: str,
    ner_fn: Callable[..., List[ExtractedEntity]] = extract_entities,
) -> NotifiableDiseaseCase:
    """
    Extract a NotifiableDiseaseCase from raw report text.

    Fields that cannot be found (e.g. no region mentioned) fall back to
    sane defaults or raise via pydantic validation — this function does
    not invent data that is not supported by the text.
    """
    entities = ner_fn(text, labels=NER_LABELS, domain="biomedical")

    disease_name = _first_entity_text(entities, "disease") or "Unknown"
    region = _first_entity_text(entities, "region") or "Unknown"
    facility_name = _first_entity_text(entities, "facility")

    report_date = extract_first_date(text)
    patient_age = extract_age(text)

    return NotifiableDiseaseCase(
        disease_name=disease_name,
        diagnosis_status=_infer_diagnosis_status(text),
        report_date=report_date or date.today(),
        patient_age=patient_age,
        region=region,
        facility_name=facility_name,
        lab_confirmed="confirmed" in text.lower() or "pcr" in text.lower(),
        source_excerpt=text[:200],
    )
