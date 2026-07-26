"""
Minimal FastAPI entry point.
"""

import traceback
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.db_models import NotifiableDiseaseRecord
from app.schemas.notifiable_disease import NotifiableDiseaseCase
from app.services.confidence import needs_review
from app.services.extraction import extract_notifiable_disease_with_confidence
from app.services.ner_client import NerBackendUnavailable

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


class SaveNotifiableDiseaseRequest(BaseModel):
    case: NotifiableDiseaseCase
    # Optional: pass the confidence report back from the extract step so
    # it's stored for audit and used to compute needed_review. If omitted
    # (e.g. a record entered by hand with no prior extraction), the record
    # is saved without a review flag.
    confidence: Optional[dict] = None


@app.get("/health")
def health_check():
    """Simple endpoint to confirm the server is running."""
    return {"status": "ok", "service": "mednexus-public-health"}


@app.post("/reports/notifiable-disease/validate")
def validate_notifiable_disease_case(case: NotifiableDiseaseCase):
    """
    Accepts a JSON body matching NotifiableDiseaseCase and returns it back
    if valid. Validation-only stub, kept from the initial skeleton.
    """
    return {"received": case}


@app.post("/reports/notifiable-disease/extract")
def extract_notifiable_disease_report(request: ExtractRequest):
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
        case, confidence = extract_notifiable_disease_with_confidence(request.text)
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
        diagnosis_status=request.case.diagnosis_status.value,
        report_date=request.case.report_date,
        patient_age=request.case.patient_age,
        patient_sex=request.case.patient_sex.value,
        region=request.case.region,
        facility_name=request.case.facility_name,
        lab_confirmed=request.case.lab_confirmed,
        source_excerpt=request.case.source_excerpt,
        confidence=request.confidence,
        needed_review=needs_review(request.confidence) if request.confidence else False,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"saved": True, "id": record.id}

