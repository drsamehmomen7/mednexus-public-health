"""
Minimal FastAPI entry point.
"""

import traceback
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.db_models import NotifiableDiseaseRecord, SavedImmunizationRecord
from app.schemas.immunization import ImmunizationRecord
from app.schemas.notifiable_disease import NotifiableDiseaseCase
from app.services.confidence import needs_review
from app.services.document_parsing import UnsupportedDocumentType, extract_text
from app.services.extraction import extract_notifiable_disease_with_confidence
from app.services.immunization_extraction import extract_immunization_with_confidence
from app.services.ner_client import NerBackendUnavailable
from app.services.report_type_detection import detect_report_type
from app.services.vocabularies import (
    load_disease_gazetteer,
    load_region_gazetteer,
    load_vaccine_gazetteer,
)
from sqlalchemy import text

app = FastAPI(title="MedNexus Public Health API", version="0.1.0")

# Local development only: the static frontend prototype is opened directly
# as a file (or served from a different port), so the browser treats it as
# a different origin. Tighten this before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    # Prototype-phase only: creates tables if they don't exist yet. Switch
    # to Alembic migrations once real data exists — see db.py.
    init_db()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Without this, an unexpected (non-HTTPException) error produces a plain
    500 response that Starlette generates OUTSIDE the CORS middleware —
    so the browser reports a confusing "CORS policy" error instead of the
    real problem. This handler keeps CORS headers on error responses too,
    and prints the full traceback to this terminal so we can see the
    actual cause.
    """
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


class ExtractRequest(BaseModel):
    text: str


class DetectTypeRequest(BaseModel):
    text: str


class SaveNotifiableDiseaseRequest(BaseModel):
    case: NotifiableDiseaseCase
    # Optional: pass the confidence report back from the extract step so
    # it's stored for audit and used to compute needed_review. If omitted
    # (e.g. a record entered by hand with no prior extraction), the record
    # is saved without a review flag.
    confidence: Optional[dict] = None
    # Optional: which batch/cohort this record belongs to. None means
    # "original bulk data" — the dashboard's default, unfiltered view.
    batch_label: Optional[str] = None


class SaveImmunizationRequest(BaseModel):
    record: ImmunizationRecord
    confidence: Optional[dict] = None
    batch_label: Optional[str] = None


@app.get("/health")
def health_check():
    """Simple endpoint to confirm the server is running."""
    return {"status": "ok", "service": "mednexus-public-health"}


@app.post("/reports/parse-document")
async def parse_document(file: UploadFile = File(...)):
    """
    Extracts plain text from an uploaded document (DOCX/TXT today), so
    the frontend can feed the result into the same extract flow it
    already uses for pasted text. Deliberately does NOT extract
    structured fields or guess the report type here — one endpoint, one
    job. Call /reports/detect-type next with the returned text.
    """
    file_bytes = await file.read()
    try:
        extracted_text = extract_text(file.filename, file_bytes)
    except UnsupportedDocumentType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    if not extracted_text.strip():
        raise HTTPException(
            status_code=422,
            detail="No readable text found in that document.",
        )

    return {"text": extracted_text}


@app.post("/reports/detect-type")
def detect_type(request: DetectTypeRequest):
    """
    Guesses which report type a piece of text is, using the SAME
    gazetteers extraction already relies on (see
    services/report_type_detection.py for why this isn't a separate
    model). Always a suggestion for the reviewer to confirm, never
    applied silently — the frontend shows this before running extraction.
    """
    detected_type, scores = detect_report_type(
        request.text,
        disease_gazetteer=load_disease_gazetteer(),
        vaccine_gazetteer=load_vaccine_gazetteer(),
    )
    return {"detected_type": detected_type, "scores": scores}


@app.post("/reports/notifiable-disease/validate")
def validate_notifiable_disease_case(case: NotifiableDiseaseCase):
    """
    Accepts a JSON body matching NotifiableDiseaseCase and returns it back
    if valid. Validation-only stub, kept from the initial skeleton.
    """
    return {"received": case}


@app.post("/reports/notifiable-disease/extract")
def extract_notifiable_disease_report(
    request: ExtractRequest,
    db: Session = Depends(get_db),
):
    """
    Extracts a structured NotifiableDiseaseCase from raw report text, plus
    a per-field confidence report so a human reviewer can see which fields
    were model-derived (with a score) versus rule-derived (dates, age),
    and which fields were not found in the text at all.

    Returns a clear 503 (not a generic 500) if OpenMed's zero-shot NER
    extras are not installed on this machine yet, so the frontend can
    show a helpful message instead of a stack trace.
    """
    try:
        # Region and disease name are both closed vocabularies for any given
        # deployment, so they're matched against the configured lists rather
        # than guessed by the model. The lists are data (see
        # services/vocabularies.py), so no country-specific values enter the
        # extraction logic itself.
        case, confidence = extract_notifiable_disease_with_confidence(
            request.text,
            region_gazetteer=load_region_gazetteer(db),
            disease_gazetteer=load_disease_gazetteer(),
        )
    except NerBackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"extracted": case, "confidence": confidence}


@app.post("/reports/notifiable-disease/save")
def save_notifiable_disease_record(
    request: SaveNotifiableDiseaseRequest,
    db: Session = Depends(get_db),
):
    """
    Persist a record AFTER human review — this is the "reviewed and
    trusted" store that a BI tool (Metabase) reads from, not a raw
    extraction log. Whatever the reviewer edited in the UI should already
    be reflected in `request.case` by the time this is called.
    """
    record = NotifiableDiseaseRecord(
        disease_name=request.case.disease_name,
        icd10_code=request.case.icd10_code,
        diagnosis_status=request.case.diagnosis_status.value,
        onset_date=request.case.onset_date,
        report_date=request.case.report_date,
        patient_age=request.case.patient_age,
        patient_sex=request.case.patient_sex.value,
        occupation=request.case.occupation,
        region=request.case.region,
        facility_name=request.case.facility_name,
        travel_related=request.case.travel_related,
        travel_country=request.case.travel_country,
        vaccination_status=request.case.vaccination_status.value,
        outcome=request.case.outcome.value,
        lab_confirmed=request.case.lab_confirmed,
        lab_test_type=request.case.lab_test_type,
        source_excerpt=request.case.source_excerpt,
        confidence=request.confidence,
        needed_review=needs_review(request.confidence) if request.confidence else False,
        batch_label=request.batch_label,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"saved": True, "id": record.id}


@app.get("/reports/notifiable-disease/batches")
def list_notifiable_disease_batches(db: Session = Depends(get_db)):
    """
    Distinct batch labels saved so far, with how many records are in
    each — lets the frontend offer "add to an existing batch" instead of
    only ever creating new ones. NULL (unbatched / original bulk data) is
    never listed here — it's the implicit default, not something you'd
    pick from a list of named batches.
    """
    rows = db.execute(
        text(
            """
            SELECT batch_label, COUNT(*) AS record_count
            FROM notifiable_disease_records
            WHERE batch_label IS NOT NULL
            GROUP BY batch_label ORDER BY batch_label
            """
        )
    ).mappings()
    return {"batches": [dict(r) for r in rows]}


@app.post("/reports/immunization/extract")
def extract_immunization_report(
    request: ExtractRequest,
    db: Session = Depends(get_db),
):
    """
    Extracts a structured ImmunizationRecord from raw report text, plus a
    per-field confidence report. Mirrors
    /reports/notifiable-disease/extract exactly — see that endpoint's
    docstring for the region-gazetteer reasoning, which applies the same
    way to vaccine_name here.
    """
    try:
        record, confidence = extract_immunization_with_confidence(
            request.text,
            region_gazetteer=load_region_gazetteer(db),
            vaccine_gazetteer=load_vaccine_gazetteer(),
        )
    except NerBackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"extracted": record, "confidence": confidence}


@app.post("/reports/immunization/save")
def save_immunization_record(
    request: SaveImmunizationRequest,
    db: Session = Depends(get_db),
):
    """
    Persist a record AFTER human review — same "reviewed and trusted"
    store convention as save_notifiable_disease_record above.
    """
    record = SavedImmunizationRecord(
        vaccine_name=request.record.vaccine_name,
        vaccine_code=request.record.vaccine_code,
        dose_number=request.record.dose_number,
        lot_number=request.record.lot_number,
        administration_date=request.record.administration_date,
        route=request.record.route.value,
        patient_age=request.record.patient_age,
        patient_age_months=request.record.patient_age_months,
        region=request.record.region,
        facility_name=request.record.facility_name,
        adverse_event_reported=request.record.adverse_event_reported,
        adverse_event_severity=request.record.adverse_event_severity.value,
        adverse_event_description=request.record.adverse_event_description,
        source_excerpt=request.record.source_excerpt,
        confidence=request.confidence,
        needed_review=needs_review(request.confidence) if request.confidence else False,
        batch_label=request.batch_label,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"saved": True, "id": record.id}


@app.get("/reports/immunization/batches")
def list_immunization_batches(db: Session = Depends(get_db)):
    """Same purpose as list_notifiable_disease_batches, for immunization."""
    rows = db.execute(
        text(
            """
            SELECT batch_label, COUNT(*) AS record_count
            FROM immunization_records
            WHERE batch_label IS NOT NULL
            GROUP BY batch_label ORDER BY batch_label
            """
        )
    ).mappings()
    return {"batches": [dict(r) for r in rows]}


@app.get("/reports/notifiable-disease/dashboard-data")
def notifiable_disease_dashboard_data(
    disease: Optional[str] = None,
    year: Optional[int] = None,
    region: Optional[str] = None,
    batch: Optional[str] = None,
    measure: str = "count",
    db: Session = Depends(get_db),
):
    """
    Returns everything the dashboard page needs in one JSON payload.

    All three filters (disease, year, region) combine with AND — any
    combination is valid, and omitting one means "all". `measure` is
    either "count" (raw case counts) or "rate" (cases per 100,000
    population), and it applies to EVERY breakdown, not just the regional
    one — that's why population is stored stratified by region x age
    group x sex in `population_strata` (see
    scripts/create_population_strata.py, including the caveat that the
    age/sex split within a region is modelled, not official).

    Rate denominators respect the active filters: filtering to one region
    divides by that region's population only, not the national total.
    """
    filters = []
    params: dict = {}
    if disease:
        filters.append("disease_name = :disease")
        params["disease"] = disease
    if year:
        filters.append("EXTRACT(YEAR FROM report_date) = :year")
        params["year"] = year
    if region:
        filters.append("region = :region")
        params["region"] = region
    if batch:
        filters.append("batch_label = :batch")
        params["batch"] = batch
    where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""

    age_bucket_sql = """
        CASE
            WHEN patient_age IS NULL THEN 'Unknown'
            WHEN patient_age < 5 THEN '0-4'
            WHEN patient_age < 15 THEN '5-14'
            WHEN patient_age < 25 THEN '15-24'
            WHEN patient_age < 45 THEN '25-44'
            WHEN patient_age < 65 THEN '45-64'
            ELSE '65+'
        END
    """

    # --- population denominators, respecting the region filter ---------
    pop_filters = []
    pop_params: dict = {}
    if region:
        pop_filters.append("region = :region")
        pop_params["region"] = region
    pop_where = ("WHERE " + " AND ".join(pop_filters)) if pop_filters else ""

    total_population = db.execute(
        text(f"SELECT SUM(population) FROM population_strata {pop_where}"),
        pop_params,
    ).scalar() or 0

    population_by_region = {
        row["region"]: row["population"]
        for row in db.execute(
            text(
                """
                SELECT region, SUM(population) AS population
                FROM population_strata GROUP BY region
                """
            )
        ).mappings()
    }
    population_by_sex = {
        row["sex"]: row["population"]
        for row in db.execute(
            text(
                f"""
                SELECT sex, SUM(population) AS population
                FROM population_strata {pop_where} GROUP BY sex
                """
            ),
            pop_params,
        ).mappings()
    }
    population_by_age = {
        row["age_group"]: row["population"]
        for row in db.execute(
            text(
                f"""
                SELECT age_group, SUM(population) AS population
                FROM population_strata {pop_where} GROUP BY age_group
                """
            ),
            pop_params,
        ).mappings()
    }

    def as_rate(count: int, population: Optional[int]) -> Optional[float]:
        """Cases per 100,000. None when we have no denominator to divide by."""
        if not population:
            return None
        return round(100000.0 * count / population, 2)

    def apply_measure(rows, population_lookup, key):
        """
        Adds a `value` field each chart plots directly, so the frontend
        never has to know which measure is active.
        """
        for row in rows:
            count = row["case_count"]
            if measure == "rate":
                row["value"] = as_rate(count, population_lookup.get(row[key]))
            else:
                row["value"] = count
        return rows

    # --- headline numbers ----------------------------------------------
    total_cases = db.execute(
        text(f"SELECT COUNT(*) FROM notifiable_disease_records {where_clause}"),
        params,
    ).scalar() or 0

    pct_needing_review = db.execute(
        text(
            f"""
            SELECT ROUND(
                100.0 * SUM(CASE WHEN needed_review THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0), 1
            )
            FROM notifiable_disease_records {where_clause}
            """
        ),
        params,
    ).scalar()

    regions_reporting = db.execute(
        text(
            f"""
            SELECT COUNT(DISTINCT region)
            FROM notifiable_disease_records {where_clause}
            """
        ),
        params,
    ).scalar() or 0

    # --- breakdowns -----------------------------------------------------
    cases_by_disease = [
        dict(row)
        for row in db.execute(
            text(
                f"""
                SELECT disease_name AS label, COUNT(*) AS case_count
                FROM notifiable_disease_records {where_clause}
                GROUP BY disease_name ORDER BY case_count DESC
                """
            ),
            params,
        ).mappings()
    ]
    # Disease isn't a population subgroup — its denominator is whoever the
    # current filters cover, so every bar shares the same denominator.
    for row in cases_by_disease:
        row["value"] = (
            as_rate(row["case_count"], total_population)
            if measure == "rate"
            else row["case_count"]
        )

    cases_by_region = apply_measure(
        [
            dict(row)
            for row in db.execute(
                text(
                    f"""
                    SELECT region AS label, COUNT(*) AS case_count
                    FROM notifiable_disease_records {where_clause}
                    GROUP BY region ORDER BY case_count DESC
                    """
                ),
                params,
            ).mappings()
        ],
        population_by_region,
        "label",
    )

    cases_by_sex = apply_measure(
        [
            dict(row)
            for row in db.execute(
                text(
                    f"""
                    SELECT patient_sex AS label, COUNT(*) AS case_count
                    FROM notifiable_disease_records {where_clause}
                    GROUP BY patient_sex ORDER BY case_count DESC
                    """
                ),
                params,
            ).mappings()
        ],
        population_by_sex,
        "label",
    )

    cases_by_age_group = [
        dict(row)
        for row in db.execute(
            text(
                f"""
                SELECT {age_bucket_sql} AS label,
                       COUNT(*) AS case_count,
                       MIN(COALESCE(patient_age, -1)) AS sort_key
                FROM notifiable_disease_records {where_clause}
                GROUP BY label ORDER BY sort_key
                """
            ),
            params,
        ).mappings()
    ]
    apply_measure(cases_by_age_group, population_by_age, "label")
    for row in cases_by_age_group:
        row.pop("sort_key", None)

    cases_over_time = [
        dict(row)
        for row in db.execute(
            text(
                f"""
                SELECT date_trunc('week', report_date) AS week, COUNT(*) AS case_count
                FROM notifiable_disease_records {where_clause}
                GROUP BY 1 ORDER BY 1
                """
            ),
            params,
        ).mappings()
    ]
    for row in cases_over_time:
        row["label"] = row.pop("week").date().isoformat()
        row["value"] = (
            as_rate(row["case_count"], total_population)
            if measure == "rate"
            else row["case_count"]
        )

    # --- filter options, so the frontend doesn't hardcode them ----------
    available_diseases = [
        r[0] for r in db.execute(
            text("SELECT DISTINCT disease_name FROM notifiable_disease_records ORDER BY 1")
        )
    ]
    available_regions = [
        r[0] for r in db.execute(text("SELECT region FROM population_strata GROUP BY region ORDER BY 1"))
    ]
    available_years = [
        int(r[0]) for r in db.execute(
            text(
                """
                SELECT DISTINCT EXTRACT(YEAR FROM report_date)
                FROM notifiable_disease_records ORDER BY 1 DESC
                """
            )
        )
    ]
    available_batches = [
        r[0] for r in db.execute(
            text(
                """
                SELECT DISTINCT batch_label FROM notifiable_disease_records
                WHERE batch_label IS NOT NULL ORDER BY 1
                """
            )
        )
    ]

    return {
        "measure": measure,
        "filters": {"disease": disease, "year": year, "region": region, "batch": batch},
        "options": {
            "diseases": available_diseases,
            "regions": available_regions,
            "years": available_years,
            "batches": available_batches,
        },
        "summary": {
            "total_cases": total_cases,
            "pct_needing_review": pct_needing_review,
            "regions_reporting": regions_reporting,
            "rate_per_100k": as_rate(total_cases, total_population),
            "population_covered": total_population,
        },
        "cases_by_disease": cases_by_disease,
        "cases_by_region": cases_by_region,
        "cases_by_sex": cases_by_sex,
        "cases_by_age_group": cases_by_age_group,
        "cases_over_time": cases_over_time,
    }


@app.get("/reports/immunization/dashboard-data")
def immunization_dashboard_data(
    vaccine: Optional[str] = None,
    year: Optional[int] = None,
    region: Optional[str] = None,
    batch: Optional[str] = None,
    measure: str = "count",
    db: Session = Depends(get_db),
):
    """
    Returns everything the Immunization dashboard page needs in one JSON
    payload. Mirrors notifiable_disease_dashboard_data's shape and
    filter-combination logic (vaccine/year/region all AND together;
    `measure` is "count" or "rate" per 100,000, same population_strata
    denominators) — see that endpoint's docstring for the population
    reasoning, which applies unchanged here.

    The age-band breakdown is Immunization-specific rather than reused
    from Notifiable Disease: nearly the entire schedule happens before a
    child's 2nd birthday, so the disease dashboard's 0-4/5-14/... buckets
    would put almost every dose in one bucket. This buckets by
    patient_age_months first (where the report stated it that way), then
    falls back to patient_age in years for anything month-based ages
    don't apply to (school-age boosters).
    """
    filters = []
    params: dict = {}
    if vaccine:
        filters.append("vaccine_name = :vaccine")
        params["vaccine"] = vaccine
    if year:
        filters.append("EXTRACT(YEAR FROM administration_date) = :year")
        params["year"] = year
    if region:
        filters.append("region = :region")
        params["region"] = region
    if batch:
        filters.append("batch_label = :batch")
        params["batch"] = batch
    where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""

    age_band_sql = """
        CASE
            WHEN patient_age_months IS NOT NULL AND patient_age_months <= 2 THEN 'Birth-2mo'
            WHEN patient_age_months IS NOT NULL AND patient_age_months <= 6 THEN '3-6mo'
            WHEN patient_age_months IS NOT NULL AND patient_age_months <= 18 THEN '7-18mo'
            WHEN patient_age IS NULL THEN 'Unknown'
            WHEN patient_age < 3 THEN '2-3y'
            WHEN patient_age < 10 THEN '3-9y'
            WHEN patient_age < 16 THEN '10-15y'
            ELSE '16-18y'
        END
    """
    age_band_sort_sql = """
        CASE
            WHEN patient_age_months IS NOT NULL AND patient_age_months <= 2 THEN 0
            WHEN patient_age_months IS NOT NULL AND patient_age_months <= 6 THEN 1
            WHEN patient_age_months IS NOT NULL AND patient_age_months <= 18 THEN 2
            WHEN patient_age IS NULL THEN 99
            WHEN patient_age < 3 THEN 3
            WHEN patient_age < 10 THEN 4
            WHEN patient_age < 16 THEN 5
            ELSE 6
        END
    """

    # --- population denominators, respecting the region filter ---------
    pop_filters = []
    pop_params: dict = {}
    if region:
        pop_filters.append("region = :region")
        pop_params["region"] = region
    pop_where = ("WHERE " + " AND ".join(pop_filters)) if pop_filters else ""

    total_population = db.execute(
        text(f"SELECT SUM(population) FROM population_strata {pop_where}"),
        pop_params,
    ).scalar() or 0

    population_by_region = {
        row["region"]: row["population"]
        for row in db.execute(
            text(
                """
                SELECT region, SUM(population) AS population
                FROM population_strata GROUP BY region
                """
            )
        ).mappings()
    }

    def as_rate(count: int, population: Optional[int]) -> Optional[float]:
        """Doses per 100,000. None when we have no denominator to divide by."""
        if not population:
            return None
        return round(100000.0 * count / population, 2)

    def apply_measure(rows, population_lookup, key):
        for row in rows:
            count = row["dose_count"]
            if measure == "rate":
                row["value"] = as_rate(count, population_lookup.get(row[key]))
            else:
                row["value"] = count
        return rows

    # --- headline numbers ----------------------------------------------
    total_doses = db.execute(
        text(f"SELECT COUNT(*) FROM immunization_records {where_clause}"),
        params,
    ).scalar() or 0

    pct_adverse_events = db.execute(
        text(
            f"""
            SELECT ROUND(
                100.0 * SUM(CASE WHEN adverse_event_reported THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0), 1
            )
            FROM immunization_records {where_clause}
            """
        ),
        params,
    ).scalar()

    regions_reporting = db.execute(
        text(
            f"""
            SELECT COUNT(DISTINCT region)
            FROM immunization_records {where_clause}
            """
        ),
        params,
    ).scalar() or 0

    # --- breakdowns -----------------------------------------------------
    doses_by_vaccine = [
        dict(row)
        for row in db.execute(
            text(
                f"""
                SELECT vaccine_name AS label, COUNT(*) AS dose_count
                FROM immunization_records {where_clause}
                GROUP BY vaccine_name ORDER BY dose_count DESC
                """
            ),
            params,
        ).mappings()
    ]
    for row in doses_by_vaccine:
        row["value"] = (
            as_rate(row["dose_count"], total_population)
            if measure == "rate"
            else row["dose_count"]
        )

    doses_by_region = apply_measure(
        [
            dict(row)
            for row in db.execute(
                text(
                    f"""
                    SELECT region AS label, COUNT(*) AS dose_count
                    FROM immunization_records {where_clause}
                    GROUP BY region ORDER BY dose_count DESC
                    """
                ),
                params,
            ).mappings()
        ],
        population_by_region,
        "label",
    )

    doses_by_age_band = [
        dict(row)
        for row in db.execute(
            text(
                f"""
                SELECT {age_band_sql} AS label,
                       COUNT(*) AS dose_count,
                       MIN({age_band_sort_sql}) AS sort_key
                FROM immunization_records {where_clause}
                GROUP BY label ORDER BY sort_key
                """
            ),
            params,
        ).mappings()
    ]
    for row in doses_by_age_band:
        row["value"] = (
            as_rate(row["dose_count"], total_population)
            if measure == "rate"
            else row["dose_count"]
        )
        row.pop("sort_key", None)

    doses_over_time = [
        dict(row)
        for row in db.execute(
            text(
                f"""
                SELECT date_trunc('week', administration_date) AS week, COUNT(*) AS dose_count
                FROM immunization_records {where_clause}
                GROUP BY 1 ORDER BY 1
                """
            ),
            params,
        ).mappings()
    ]
    for row in doses_over_time:
        row["label"] = row.pop("week").date().isoformat()
        row["value"] = (
            as_rate(row["dose_count"], total_population)
            if measure == "rate"
            else row["dose_count"]
        )

    adverse_events_by_severity = [
        dict(row)
        for row in db.execute(
            text(
                f"""
                SELECT adverse_event_severity AS label, COUNT(*) AS dose_count
                FROM immunization_records {where_clause}
                GROUP BY adverse_event_severity ORDER BY dose_count DESC
                """
            ),
            params,
        ).mappings()
    ]
    for row in adverse_events_by_severity:
        row["value"] = row["dose_count"]

    # --- filter options, so the frontend doesn't hardcode them ----------
    available_vaccines = [
        r[0] for r in db.execute(
            text("SELECT DISTINCT vaccine_name FROM immunization_records ORDER BY 1")
        )
    ]
    available_regions = [
        r[0] for r in db.execute(text("SELECT region FROM population_strata GROUP BY region ORDER BY 1"))
    ]
    available_years = [
        int(r[0]) for r in db.execute(
            text(
                """
                SELECT DISTINCT EXTRACT(YEAR FROM administration_date)
                FROM immunization_records ORDER BY 1 DESC
                """
            )
        )
    ]
    available_batches = [
        r[0] for r in db.execute(
            text(
                """
                SELECT DISTINCT batch_label FROM immunization_records
                WHERE batch_label IS NOT NULL ORDER BY 1
                """
            )
        )
    ]

    return {
        "measure": measure,
        "filters": {"vaccine": vaccine, "year": year, "region": region, "batch": batch},
        "options": {
            "vaccines": available_vaccines,
            "regions": available_regions,
            "years": available_years,
            "batches": available_batches,
        },
        "summary": {
            "total_doses": total_doses,
            "pct_adverse_events": pct_adverse_events,
            "regions_reporting": regions_reporting,
            "rate_per_100k": as_rate(total_doses, total_population),
            "population_covered": total_population,
        },
        "doses_by_vaccine": doses_by_vaccine,
        "doses_by_region": doses_by_region,
        "doses_by_age_band": doses_by_age_band,
        "doses_over_time": doses_over_time,
        "adverse_events_by_severity": adverse_events_by_severity,
    }
