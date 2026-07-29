"""
Runs the REAL extraction pipeline over the generated synthetic
immunization reports, saves each result to the database, and measures
accuracy against the known ground truth. Mirrors
load_synthetic_reports.py's approach exactly — see that file's docstring
for why this isn't a shortcut (loading ground_truth.json straight into
the database would test nothing except the dashboard).

Expect this to be slow: GLiNER inference runs per report, and each save is
a round trip to Postgres. Progress is printed continuously, and --limit
exists to try a small batch first.

Usage (from backend/, venv active, DATABASE_URL set):
    python -m scripts.load_immunization_reports --limit 10    # try a few first
    python -m scripts.load_immunization_reports               # full run
    python -m scripts.load_immunization_reports --no-save     # measure only
"""

import argparse
import json
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from app.db import SessionLocal, init_db
from app.db_models import SavedImmunizationRecord
from app.services.confidence import needs_review
from app.services.immunization_extraction import extract_immunization_with_confidence
from app.services.ner_client import NerBackendUnavailable
from app.services.vocabularies import load_region_gazetteer, load_vaccine_gazetteer

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "immunization_reports"
GROUND_TRUTH = DATA_DIR / "ground_truth.json"

# Fields the extraction pipeline currently attempts. vaccine_code and
# lot_number are in the schema but not extracted yet — vaccine_code needs
# terminology normalization (not built), and lot_number, while
# occasionally regex-able, wasn't part of this pass; listed separately so
# the gap is visible rather than silently ignored.
EXTRACTED_FIELDS = [
    "vaccine_name",
    "dose_number",
    "administration_date",
    "route",
    "patient_age",
    "patient_age_months",
    "region",
    "facility_name",
    "adverse_event_reported",
    "adverse_event_severity",
    "adverse_event_description",
]

NOT_YET_EXTRACTED = [
    "vaccine_code",
    "lot_number",
]


def normalize(value):
    """Loose comparison: case and surrounding punctuation shouldn't count as errors."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip().strip(".,;:").lower()


def compare(extracted_record, truth):
    """Returns {field: (is_correct, extracted_value, true_value)}."""
    result = {}
    for field in EXTRACTED_FIELDS:
        got = getattr(extracted_record, field, None)
        if hasattr(got, "value"):  # enum
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
        print("Run: python -m scripts.generate_immunization_reports")
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

    # Same region vocabulary as Notifiable Disease — one deployment, one
    # region list, shared across report types.
    vocab_session = SessionLocal()
    try:
        region_gazetteer = load_region_gazetteer(vocab_session)
    finally:
        vocab_session.close()

    if region_gazetteer:
        print(f"Region vocabulary loaded: {len(region_gazetteer)} regions.\n")
    else:
        print("No region vocabulary found — falling back to the NER model.\n")

    vaccine_gazetteer = load_vaccine_gazetteer()
    if vaccine_gazetteer:
        print(f"Vaccine vocabulary loaded: {len(vaccine_gazetteer)} vaccines.\n")
    else:
        print("No vaccine vocabulary found — falling back to the NER model.\n")

    db = None if args.no_save else SessionLocal()

    try:
        for i, entry in enumerate(records, start=1):
            text = entry["text"]
            truth = entry["truth"]

            try:
                record, confidence = extract_immunization_with_confidence(
                    text,
                    region_gazetteer=region_gazetteer,
                    vaccine_gazetteer=vaccine_gazetteer,
                )
            except NerBackendUnavailable as exc:
                print(f"\nGLiNER unavailable: {exc}")
                print("Run scripts/download_gliner_model.py first.")
                return
            except Exception as exc:  # keep going; one bad report shouldn't end the run
                failed += 1
                print(f"  [{i}] extraction failed: {type(exc).__name__}: {exc}")
                continue

            for field, (is_correct, got, expected) in compare(record, truth).items():
                if is_correct:
                    correct_counts[field] += 1
                elif len(mismatches[field]) < 5:
                    mismatches[field].append((entry["file"], got, expected))

            review_needed = needs_review(confidence) if confidence else False
            if review_needed:
                flagged_for_review += 1

            if db is not None:
                db.add(SavedImmunizationRecord(
                    vaccine_name=record.vaccine_name,
                    vaccine_code=record.vaccine_code,
                    dose_number=record.dose_number,
                    lot_number=record.lot_number,
                    administration_date=record.administration_date,
                    route=record.route.value,
                    patient_age=record.patient_age,
                    patient_age_months=record.patient_age_months,
                    region=record.region,
                    facility_name=record.facility_name,
                    adverse_event_reported=record.adverse_event_reported,
                    adverse_event_severity=record.adverse_event_severity.value,
                    adverse_event_description=record.adverse_event_description,
                    source_excerpt=text[:400],
                    confidence=confidence,
                    needed_review=review_needed,
                ))
                saved += 1
                if saved % 25 == 0:
                    db.commit()  # commit in batches, not per row

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

    print("\nNOT ATTEMPTED BY EXTRACTION YET (present in the report text at")
    print("least sometimes, but the pipeline has no logic for them yet):")
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
