"""
Extraction orchestrator for Laboratory reports.

Same hybrid strategy as the other two report types:
- test_name and specimen_type: closed vocabulary, matched via gazetteers
  seeded from data/lab_tests.json and data/specimen_types.json — both
  synthetic placeholders (like the disease gazetteer), covering the
  panel realistic for this project's 10 tracked diseases. No
  negation-awareness needed, same reasoning as vaccine_name: a lab
  report states which test was run, not one that got "ruled out".
- pathogen_identified: REUSES the disease gazetteer already built for
  Notifiable Disease — a positive lab result identifies one of the SAME
  tracked pathogens, so there's no separate vocabulary to maintain. Only
  populated when the result is positive; a gazetteer hit on a disease
  name elsewhere in the text (e.g. naming which disease the test panel
  is FOR) must not be read as "identified" when the result is negative.
- result: rule-based keyword match (positive/negative/indeterminate/
  pending) — closed, small vocabulary, same reasoning as
  diagnosis_status for Notifiable Disease.
- specimen_collection_date / result_date: rule-based, keyword-anchored
  to disambiguate the two dates every report states — see
  rule_based.py's extract_specimen_collection_date /
  extract_result_date docstrings for how the anchor windows avoid
  reading one date as the other.
- region and facility_name: same gazetteer/NER pattern as the other two
  report types.

The NER call is dependency-injected (`ner_fn` parameter) so this function,
and its tests, do not require the real OpenMed/GLiNER install to run.
"""

from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from app.schemas.laboratory import LaboratoryReport, TestResult
from app.services.confidence import model_confidence, rule_based_confidence
from app.services.entity_selection import first_entity
from app.services.gazetteer import Gazetteer
from app.services.ner_client import ExtractedEntity, extract_entities
from app.services.rule_based import (
    extract_age,
    extract_lab_result,
    extract_result_date,
    extract_specimen_collection_date,
)

NER_LABELS = ["region", "facility"]

RULE_BASED_FIELDS = (
    "specimen_collection_date", "result_date", "patient_age", "result",
)


def extract_laboratory_with_confidence(
    text: str,
    ner_fn: Callable[..., List[ExtractedEntity]] = extract_entities,
    region_gazetteer: Optional[Gazetteer] = None,
    disease_gazetteer: Optional[Gazetteer] = None,
    lab_test_gazetteer: Optional[Gazetteer] = None,
    specimen_type_gazetteer: Optional[Gazetteer] = None,
) -> Tuple[LaboratoryReport, Dict[str, dict]]:
    """
    Extract a LaboratoryReport, plus a per-field confidence report.

    Four gazetteers, each optional and independently overridable — when
    supplied, each closed-vocabulary field prefers its exact match over
    NER; when not supplied, that field falls back to "not found" (there
    is no NER label trained for test_name/specimen_type in this
    project, unlike disease/vaccine, so without a gazetteer these two
    fields simply won't resolve — a real deployment should always
    supply lab_test_gazetteer and specimen_type_gazetteer).
    """
    entities = ner_fn(text, labels=NER_LABELS, domain="biomedical")

    region_entity = first_entity(entities, "region")
    facility_entity = first_entity(entities, "facility")

    gazetteer_region = region_gazetteer.find(text) if region_gazetteer else None
    gazetteer_test_name = lab_test_gazetteer.find(text) if lab_test_gazetteer else None
    gazetteer_specimen_type = specimen_type_gazetteer.find(text) if specimen_type_gazetteer else None

    result = extract_lab_result(text)
    specimen_collection_date = extract_specimen_collection_date(text)
    result_date_value = extract_result_date(text)
    patient_age = extract_age(text)

    # Pathogen is only "identified" on a positive result — a gazetteer
    # hit on a disease name elsewhere in the text (e.g. the test panel's
    # own name, "Influenza PCR") is not evidence the pathogen was found
    # if the result itself is negative/indeterminate/pending.
    pathogen_identified = None
    if result == "positive" and disease_gazetteer:
        pathogen_identified = disease_gazetteer.find(text)

    report = LaboratoryReport(
        test_name=(gazetteer_test_name or "Unknown"),
        test_code=None,
        specimen_type=gazetteer_specimen_type,
        result=(TestResult(result) if result else TestResult.PENDING),
        pathogen_identified=pathogen_identified,
        specimen_collection_date=specimen_collection_date,
        result_date=(result_date_value or specimen_collection_date or date.today()),
        patient_age=patient_age,
        region=(gazetteer_region or (region_entity.text if region_entity else "Unknown")),
        facility_name=(facility_entity.text if facility_entity else None),
        source_excerpt=text[:200],
    )

    confidence = {
        "test_name": (
            {"source": "gazetteer", "found": True}
            if gazetteer_test_name
            else {"source": "gazetteer", "found": False}
        ),
        "specimen_type": (
            {"source": "gazetteer", "found": True}
            if gazetteer_specimen_type
            else {"source": "gazetteer", "found": False}
        ),
        "pathogen_identified": (
            {"source": "gazetteer", "found": True}
            if pathogen_identified
            else {"source": "gazetteer", "found": False}
        ),
        "region": (
            {"source": "gazetteer", "found": True}
            if gazetteer_region
            else model_confidence(region_entity)
        ),
        "facility_name": model_confidence(facility_entity),
        **{field: rule_based_confidence() for field in RULE_BASED_FIELDS},
    }

    return report, confidence


def extract_laboratory(
    text: str,
    ner_fn: Callable[..., List[ExtractedEntity]] = extract_entities,
    region_gazetteer: Optional[Gazetteer] = None,
    disease_gazetteer: Optional[Gazetteer] = None,
    lab_test_gazetteer: Optional[Gazetteer] = None,
    specimen_type_gazetteer: Optional[Gazetteer] = None,
) -> LaboratoryReport:
    """
    Extract a LaboratoryReport from raw report text.

    Thin wrapper kept for consistency with extract_notifiable_disease /
    extract_immunization. For confidence scores per field, use
    extract_laboratory_with_confidence instead.
    """
    report, _confidence = extract_laboratory_with_confidence(
        text,
        ner_fn=ner_fn,
        region_gazetteer=region_gazetteer,
        disease_gazetteer=disease_gazetteer,
        lab_test_gazetteer=lab_test_gazetteer,
        specimen_type_gazetteer=specimen_type_gazetteer,
    )
    return report
