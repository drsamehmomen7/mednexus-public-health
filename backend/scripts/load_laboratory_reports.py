"""
Runs the REAL extraction pipeline over the generated synthetic
laboratory reports, saves each result to the database, and measures
accuracy against the known ground truth. Mirrors
load_synthetic_reports.py / load_immunization_reports.py exactly.

Usage (from backend/, venv active, DATABASE_URL set):
    python -m scripts.load_laboratory_reports --limit 10    # try a few first
    python -m scripts.load_laboratory_reports               # full run
    python -m scripts.load_laboratory_reports --no-save     # measure only
"""

import argparse
import json
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from app.db import SessionLocal, init_db
from app.db_models import SavedLaboratoryRecord
from app.services.confidence import needs_review
from app.services.laboratory_extraction import extract_laboratory_with_confidence
from app.services.ner_client import NerBackendUnavailable
from app.services.vocabularies import (
    load_disease_gazetteer,
    load_lab_test_gazetteer,
    load_region_gazetteer,
    load_specimen_type_gazetteer,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "laboratory_reports"
GROUND_TRUTH = DATA_DIR / "ground_truth.json"

EXTRACTED_FIELDS = [
    "test_name",
    "specimen_type",
    "result",
    "pathogen_identified",
    "specimen_collection_date",
    "result_date",
    "patient_age",
    "region",
    "facility_name",
]

# test_code needs terminology normalization (LOINC), not built yet.
NOT_YET_EXTRACTED = ["test_code"]


def normalize(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip().strip(".,;:").lower()


def compare(extracted_report, truth):
    result = {}
    for field in EXTRACTED_FIELDS:
        got = getattr(extracted_report, field, None)
        if hasattr(got, "value"):
            got = got.value
        expected = truth.get(field)
        result[field] = (normalize(got) == normalize(expected), got, expected)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N reports")
    parser.add_argument("--no-save", action="store_true", help="Measure accuracy without writing to the database")
    args = parser.parse_args()

    if not GROUND_TRUTH.exists():
        print(f"No ground truth found at {GROUND_TRUTH}")
        print("Run: python -m scripts.generate_laboratory_reports")
        return

    records = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    if args.limit:
        records = records[: args.limit]

    if not args.no_save:
        init_db()

    correct_counts = defaultdict(int)
    mismatches = defaultdict(list)
    saved = 0
    failed = 0
    flagged_for_review = 0
    started = time.time()

    print(f"Processing {len(records)} reports through the real extraction pipeline.")
    print("This is slow by design — GLiNER runs per report.\n")

    vocab_session = SessionLocal()
    try:
        region_gazetteer = load_region_gazetteer(vocab_session)
    finally:
        vocab_session.close()

    if region_gazetteer:
        print(f"Region vocabulary loaded: {len(region_gazetteer)} regions.\n")
    else:
        print("No region vocabulary found — falling back to the NER model.\n")

    disease_gazetteer = load_disease_gazetteer()
    lab_test_gazetteer = load_lab_test_gazetteer()
    specimen_gazetteer = load_specimen_type_gazetteer()
    print(f"Lab test vocabulary loaded: {len(lab_test_gazetteer)} tests.")
    print(f"Specimen type vocabulary loaded: {len(specimen_gazetteer)} types.\n")

    db = None if args.no_save else SessionLocal()

    try:
        for i, entry in enumerate(records, start=1):
            text = entry["text"]
            truth = entry["truth"]

            try:
                report, confidence = extract_laboratory_with_confidence(
                    text,
                    region_gazetteer=region_gazetteer,
                    disease_gazetteer=disease_gazetteer,
                    lab_test_gazetteer=lab_test_gazetteer,
                    specimen_type_gazetteer=specimen_gazetteer,
                )
            except NerBackendUnavailable as exc:
                print(f"\nGLiNER unavailable: {exc}")
                print("Run scripts/download_gliner_model.py first.")
                return
            except Exception as exc:
                failed += 1
                print(f"  [{i}] extraction failed: {type(exc).__name__}: {exc}")
                continue

            for field, (is_correct, got, expected) in compare(report, truth).items():
                if is_correct:
                    correct_counts[field] += 1
                elif len(mismatches[field]) < 5:
                    mismatches[field].append((entry["file"], got, expected))

            review_needed = needs_review(confidence) if confidence else False
            if review_needed:
                flagged_for_review += 1

            if db is not None:
                db.add(SavedLaboratoryRecord(
                    test_name=report.test_name,
                    test_code=report.test_code,
                    specimen_type=report.specimen_type,
                    result=report.result.value,
                    pathogen_identified=report.pathogen_identified,
                    specimen_collection_date=report.specimen_collection_date,
                    result_date=report.result_date,
                    patient_age=report.patient_age,
                    region=report.region,
                    facility_name=report.facility_name,
                    source_excerpt=text[:400],
                    confidence=confidence,
                    needed_review=review_needed,
                ))
                saved += 1
                if saved % 25 == 0:
                    db.commit()

            if i % 10 == 0 or i == len(records):
                elapsed = time.time() - started
                rate = i / elapsed if elapsed else 0
                remaining = (len(records) - i) / rate if rate else 0
                print(f"  {i}/{len(records)} processed "
                      f"({elapsed/60:.1f} min elapsed, ~{remaining/60:.1f} min left)")

        if db is not None:
            db.commit()
    finally:
        if db is not None:
            db.close()

    total = len(records) - failed
    elapsed = time.time() - started

    print(f"\n{'=' * 58}")
    print(f"Processed {total} reports in {elapsed/60:.1f} minutes")
    if not args.no_save:
        print(f"Saved to database: {saved}")
    print(f"Flagged as needing human review: {flagged_for_review} "
          f"({100*flagged_for_review/total:.1f}%)" if total else "")
    print(f"{'=' * 58}\n")

    print("EXTRACTION ACCURACY (exact match against ground truth)\n")
    for field in EXTRACTED_FIELDS:
        n = correct_counts[field]
        pct = 100 * n / total if total else 0
        bar = "#" * int(pct / 5)
        print(f"  {field:<26} {pct:>5.1f}%  {n:>4}/{total}  {bar}")

    print("\nNOT ATTEMPTED BY EXTRACTION YET:")
    for field in NOT_YET_EXTRACTED:
        print(f"  - {field}")

    print("\nSAMPLE MISMATCHES (up to 5 per field — read these before")
    print("concluding a field is broken; some are formatting, not failure):\n")
    for field in EXTRACTED_FIELDS:
        if mismatches[field]:
            print(f"  {field}:")
            for filename, got, expected in mismatches[field]:
                print(f"    {filename}: got {got!r}, expected {expected!r}")
            print()


if __name__ == "__main__":
    main()
