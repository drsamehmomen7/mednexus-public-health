"""
Extraction orchestrator for Immunization reports.

Same hybrid strategy as Notifiable Disease, reusing the shared services
rather than copying them:
- Dates and ages: rule-based (deterministic, auditable) — see
  rule_based.py. patient_age_months matters here in a way it never did
  for Notifiable Disease: most of the immunization schedule (birth
  through 18 months) is naturally stated in months, and a whole-year age
  is nearly meaningless for that range — see extract_age_months.
- dose_number, route, adverse_event_*: also rule-based — closed,
  small-vocabulary fields with a consistent phrasing pattern across
  voices, the same reasoning as diagnosis_status/lab_confirmed for
  Notifiable Disease.
- vaccine_name and region: closed vocabulary, matched via a gazetteer —
  see gazetteer.py / vocabularies.py. Unlike disease_name, vaccine_name
  does NOT need negation-aware matching: a report describing an
  administered dose is not the place a vaccine gets "ruled out" the way
  a diagnosis can be.
- facility_name: NER only (no gazetteer yet), same as Notifiable Disease.

The vaccine gazetteer is a REAL source (Kuwait MOH 2025 schedule), not a
placeholder derived from synthetic data the way the disease gazetteer is
— see docs/decisions-log.md. A new/unlisted vaccine still falls back to
NER the same way an unlisted disease does; that fallback path is
untested here (all 500 synthetic reports use only the 12 scheduled
vaccines), so treat it as unverified until real report variety exercises
it.

The NER call is dependency-injected (`ner_fn` parameter) so this function,
and its tests, do not require the real OpenMed/GLiNER install to run.
"""

from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from app.schemas.immunization import AdverseEventSeverity, ImmunizationRecord, InjectionRoute
from app.services.confidence import model_confidence, rule_based_confidence
from app.services.entity_selection import first_entity
from app.services.gazetteer import Gazetteer
from app.services.ner_client import ExtractedEntity, extract_entities
from app.services.rule_based import (
    extract_adverse_event,
    extract_age,
    extract_age_months,
    extract_dose_number,
    extract_first_date,
    extract_route,
)

NER_LABELS = ["vaccine", "region", "facility"]

RULE_BASED_FIELDS = (
    "administration_date", "patient_age", "patient_age_months",
    "dose_number", "route", "adverse_event_reported",
    "adverse_event_severity", "adverse_event_description",
)


def _strip_trailing_region(facility_name: Optional[str], region_gazetteer: Optional[Gazetteer]) -> Optional[str]:
    """
    GLiNER's zero-shot "facility" label sometimes swallows the region too
    when they're written on one comma-separated line ("Facility: Central
    District Hospital, Al Asimah") — confirmed against a real 500-report
    GLiNER run, where this was the ONLY source of facility_name error
    (99.0% -> expected 100%). Region is a known, closed vocabulary, so
    stripping a trailing ", <known region>" is safe: it only ever fires
    when the suffix is an actual region name, never on a real facility
    name that happens to contain a comma for some other reason.
    """
    if not facility_name or not region_gazetteer:
        return facility_name
    for region_term in region_gazetteer.terms:
        suffix = f", {region_term}"
        if facility_name.endswith(suffix):
            return facility_name[: -len(suffix)].strip()
    return facility_name


def extract_immunization_with_confidence(
    text: str,
    ner_fn: Callable[..., List[ExtractedEntity]] = extract_entities,
    region_gazetteer: Optional[Gazetteer] = None,
    vaccine_gazetteer: Optional[Gazetteer] = None,
) -> Tuple[ImmunizationRecord, Dict[str, dict]]:
    """
    Extract an ImmunizationRecord, plus a per-field confidence report.

    `region_gazetteer` / `vaccine_gazetteer` are optional and hold this
    deployment's known regions / vaccines. When supplied, each takes
    precedence over the NER model for its field, because both are CLOSED
    vocabularies and exact matching beats zero-shot guessing on those.
    When not supplied, behaviour falls back to NER only, so this function
    still works standalone.
    """
    entities = ner_fn(text, labels=NER_LABELS, domain="biomedical")

    vaccine_entity = first_entity(entities, "vaccine")
    region_entity = first_entity(entities, "region")
    facility_entity = first_entity(entities, "facility")

    gazetteer_region = region_gazetteer.find(text) if region_gazetteer else None
    gazetteer_vaccine = vaccine_gazetteer.find(text) if vaccine_gazetteer else None

    administration_date = extract_first_date(text)
    age_months = extract_age_months(text)
    # Years is derived from months when the report is infant-phrased,
    # rather than trying extract_age() first — a report saying "2-month-
    # old" won't also say "0-year-old", so extract_age() would find
    # nothing there anyway; deriving from months is the reliable path.
    patient_age = (age_months // 12) if age_months is not None else extract_age(text)
    dose_number = extract_dose_number(text)
    route = extract_route(text)
    adverse_reported, adverse_severity, adverse_description = extract_adverse_event(text)

    record = ImmunizationRecord(
        vaccine_name=(
            gazetteer_vaccine or (vaccine_entity.text if vaccine_entity else "Unknown")
        ),
        dose_number=dose_number,
        administration_date=administration_date or date.today(),
        route=(InjectionRoute(route) if route else InjectionRoute.UNKNOWN),
        patient_age=patient_age,
        patient_age_months=age_months,
        region=(gazetteer_region or (region_entity.text if region_entity else "Unknown")),
        facility_name=_strip_trailing_region(
            facility_entity.text if facility_entity else None, region_gazetteer
        ),
        adverse_event_reported=adverse_reported,
        adverse_event_severity=AdverseEventSeverity(adverse_severity),
        adverse_event_description=adverse_description,
        source_excerpt=text[:200],
    )

    confidence = {
        "vaccine_name": (
            {"source": "gazetteer", "found": True}
            if gazetteer_vaccine
            else model_confidence(vaccine_entity)
        ),
        "region": (
            {"source": "gazetteer", "found": True}
            if gazetteer_region
            else model_confidence(region_entity)
        ),
        "facility_name": model_confidence(facility_entity),
        **{field: rule_based_confidence() for field in RULE_BASED_FIELDS},
    }

    return record, confidence


def extract_immunization(
    text: str,
    ner_fn: Callable[..., List[ExtractedEntity]] = extract_entities,
    region_gazetteer: Optional[Gazetteer] = None,
    vaccine_gazetteer: Optional[Gazetteer] = None,
) -> ImmunizationRecord:
    """
    Extract an ImmunizationRecord from raw report text.

    Thin wrapper kept for consistency with extract_notifiable_disease.
    For confidence scores per field, use
    extract_immunization_with_confidence instead.
    """
    record, _confidence = extract_immunization_with_confidence(
        text,
        ner_fn=ner_fn,
        region_gazetteer=region_gazetteer,
        vaccine_gazetteer=vaccine_gazetteer,
    )
    return record
