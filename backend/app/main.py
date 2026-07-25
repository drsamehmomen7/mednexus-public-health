"""
Minimal FastAPI entry point.
"""

import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.schemas.notifiable_disease import NotifiableDiseaseCase
from app.services.extraction import extract_notifiable_disease
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
    Extracts a structured NotifiableDiseaseCase from raw report text.

    Returns a clear 503 (not a generic 500) if OpenMed's zero-shot NER
    extras are not installed on this machine yet, so the frontend can
    show a helpful message instead of a stack trace.
    """
    try:
        case = extract_notifiable_disease(request.text)
    except NerBackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"extracted": case}

