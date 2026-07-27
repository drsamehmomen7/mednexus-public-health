"""
Runs the REAL extraction pipeline over the generated synthetic reports,
saves each result to the database, and measures accuracy against the known
ground truth.

This is deliberately not a shortcut. It would be far faster to load
ground_truth.json straight into the database, but that would test nothing
except the dashboard. Running the actual pipeline over 500 reports is the
first honest measurement of how good the extraction really is — and because
ground_truth.json records what each report actually said, accuracy can be
reported as a number per field rather than eyeballed.

Expect this to be slow: GLiNER inference runs per report, and each save is a
round trip to Postgres. 500 reports takes roughly 20-30 minutes. Progress is
printed continuously, and --limit exists to try a small batch first.

Accuracy caveat worth understanding when reading the output: a field counts
as correct only on exact match. Region and facility in particular are judged
harshly — extracting "Ardiya Clinic" when the truth is "Ardiya Clinic," (with
punctuation) counts as wrong. Treat the numbers as a floor, not a ceiling,
and read the sample mismatches printed at the end before concluding a field
is broken.

Usage (from backend/, venv active, DATABASE_URL set):
    python -m scripts.load_synthetic_reports --limit 10    # try a few first
    python -m scripts.load_synthetic_reports               # full run
    python -m scripts.load_synthetic_reports --no-save     # measure only
"""

import argparse
import json
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from app.db import SessionLocal, init_db
from app.db_models import NotifiableDiseaseRecord
from app.services.confidence import needs_review
from app.services.extraction import extract_notifiable_disease_with_confidence
from app.services.ner_client import NerBackendUnavailable
from app.services.vocabularies import load_region_gazetteer

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic_reports"
GROUND_TRUTH = DATA_DIR / "ground_truth.json"

# Fields the extraction pipeline currently attempts. Fields the generator
# writes into the text but extraction doesn't handle yet (vaccination status,
# travel, occupation, outcome, onset date) are listed separately so the gap
# is visible in the output rather than silently ignored.
EXTRACTED_FIELDS = [
    "disease_name",
    "diagnosis_status",
    "report_date",
    "patient_age",
    "region",
    "facility_name",
    "lab_confirmed",
]

NOT_YET_EXTRACTED = [
    "onset_date",
    "patient_sex",
    "occupation",
    "travel_related",
    "travel_country",
    "vaccination_status",
    "outcome",
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


def compare(extracted_case, truth):
    """Returns {field: (is_correct, extracted_value, true_value)}."""
    result = {}
    for field in EXTRACTED_FIELDS:
        got = getattr(extracted_case, field, None)
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
        print("Run: python scripts/generate_synthetic_reports.py --count 500")
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

    # The region vocabulary comes from the deployment's own reference data.
    # Region is a closed vocabulary, so exact matching beats zero-shot NER;
    # without this, roughly 15% of reports came back with region "Unknown"
    # because the model couldn't split "Ardiya Clinic, Farwaniya".
    vocab_session = SessionLocal()
    try:
        region_gazetteer = load_region_gazetteer(vocab_session)
    finally:
        vocab_session.close()

    if region_gazetteer:
        print(f"Region vocabulary loaded: {len(region_gazetteer)} regions.\n")
    else:
        print("No region vocabulary found — falling back to the NER model.\n")

    db = None if args.no_save else SessionLocal()

    try:
        for i, entry in enumerate(records, start=1):
            text = entry["text"]
            truth = entry["truth"]

            try:
                case, confidence = extract_notifiable_disease_with_confidence(
                    text, region_gazetteer=region_gazetteer
                )
            except NerBackendUnavailable as exc:
                print(f"\nGLiNER unavailable: {exc}")
                print("Run scripts/download_gliner_model.py first.")
                return
            except Exception as exc:  # keep going; one bad report shouldn't end the run
                failed += 1
                print(f"  [{i}] extraction failed: {type(exc).__name__}: {exc}")
                continue

            for field, (is_correct, got, expected) in compare(case, truth).items():
                if is_correct:
                    correct_counts[field] += 1
                elif len(mismatches[field]) < 5:
                    mismatches[field].append((entry["file"], got, expected))

            review_needed = needs_review(confidence) if confidence else False
            if review_needed:
                flagged_for_review += 1

            if db is not None:
                # Extraction fills what it can; fields it doesn't handle yet
                # fall back to the schema defaults rather than being invented.
                db.add(NotifiableDiseaseRecord(
                    disease_name=case.disease_name,
                    icd10_code=case.icd10_code,
                    diagnosis_status=case.diagnosis_status.value,
                    onset_date=case.onset_date,
                    report_date=case.report_date,
                    patient_age=case.patient_age,
                    patient_sex=case.patient_sex.value,
                    occupation=case.occupation,
                    region=case.region,
                    facility_name=case.facility_name,
                    travel_related=case.travel_related,
                    travel_country=case.travel_country,
                    vaccination_status=case.vaccination_status.value,
                    outcome=case.outcome.value,
                    lab_confirmed=case.lab_confirmed,
                    lab_test_type=case.lab_test_type,
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
        print(f"  {field:<20} {pct:>5.1f}%  {n:>4}/{total}  {bar}")

    print("\nNOT ATTEMPTED BY EXTRACTION YET (present in the report text,")
    print("but the pipeline has no logic for them — this is the gap list):")
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
