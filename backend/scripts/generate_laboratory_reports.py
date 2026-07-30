"""
Generates realistic-looking laboratory reports as FREE TEXT. Mirrors
generate_synthetic_reports.py / generate_immunization_reports.py's
conventions (same regions/facilities, same date-format variety, same
"write ground truth first, then render text" structure).

Each report describes ONE test result for ONE of this project's 10
tracked notifiable diseases — the test/specimen pairings
(DISEASE_TEST_MAP below) are a reasonable clinical match, not invented
at random (a CSF culture for meningitis, a stool culture for
salmonellosis, serology for the viral exanthems, etc.).

Result distribution is deliberately skewed toward positive/negative
over indeterminate/pending, matching how a NOTIFIABLE DISEASE lab
report stream actually looks — most reports exist because a targeted
test was ordered on a suspected case, not as general screening.

SYNTHETIC DATA ONLY. No real patients, no real facilities, no real identifiers.

Usage (from backend/):
    python -m scripts.generate_laboratory_reports            # default 500
    python -m scripts.generate_laboratory_reports --count 100
"""

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "laboratory_reports"

REGIONS = {
    "Al Asimah": 620_000,
    "Hawalli": 1_050_000,
    "Farwaniya": 1_180_000,
    "Ahmadi": 1_150_000,
    "Jahra": 620_000,
    "Mubarak Al-Kabeer": 360_000,
}
FACILITIES = {
    "Al Asimah": ["Central District Hospital", "Qibla Health Centre", "North Clinic"],
    "Hawalli": ["Eastern General Hospital", "Salmiya Health Centre", "Bayan Clinic"],
    "Farwaniya": ["Western General Hospital", "Khaitan Health Centre", "Ardiya Clinic"],
    "Ahmadi": ["Southern General Hospital", "Fahaheel Health Centre", "Mangaf Clinic"],
    "Jahra": ["Northern General Hospital", "Jahra Health Centre", "Sulaibiya Clinic"],
    "Mubarak Al-Kabeer": ["Adan District Hospital", "Qurain Health Centre", "Messila Clinic"],
}

# (test_name, specimen_type) options per disease — a report picks one at
# random when that disease is selected. pathogen_identified, when the
# result is positive, is always the disease name itself (verbatim match
# against notifiable_diseases.json, so the SAME disease gazetteer used
# for Notifiable Disease extraction works here unchanged).
DISEASE_TEST_MAP = {
    "Influenza": [("Influenza PCR", "Nasopharyngeal Swab"), ("Influenza Rapid Antigen Test", "Nasopharyngeal Swab")],
    "Measles": [("Measles IgM Serology", "Serum")],
    "Rubella": [("Rubella IgM Serology", "Serum")],
    "Meningococcal disease": [("Meningococcal CSF Culture", "CSF"), ("Meningococcal Gram Stain", "CSF")],
    "Salmonellosis": [("Salmonella Stool Culture", "Stool")],
    "Typhoid fever": [("Typhoid Widal Test", "Blood"), ("Typhoid Blood Culture", "Blood")],
    "Dengue fever": [("Dengue NS1 Antigen Test", "Blood"), ("Dengue IgM Serology", "Serum")],
    "Chickenpox": [("Chickenpox PCR", "Vesicle Fluid")],
    "Mumps": [("Mumps IgM Serology", "Serum")],
    "Hepatitis A": [("Hepatitis A IgM Serology", "Serum")],
}

RESULT_WEIGHTS = [("positive", 50), ("negative", 32), ("indeterminate", 6), ("pending", 12)]

LOT_PREFIXES = ["LAB", "MOH"]


def fmt_date(d, style):
    if style == "iso":
        return d.isoformat()
    if style == "slash":
        return d.strftime("%d/%m/%Y")
    if style == "short_slash":
        return f"{d.day}/{d.month}/{str(d.year)[2:]}"
    if style == "month_name":
        return d.strftime("%d %b %Y")
    return d.strftime("%d %B %Y")


DATE_STYLES = ["iso", "slash", "short_slash", "month_name", "long_month"]


def weighted_choice(pairs):
    items, weights = zip(*pairs)
    return random.choices(items, weights=weights, k=1)[0]


def build_case(result_date, region):
    disease = random.choice(list(DISEASE_TEST_MAP))
    test_name, specimen_type = random.choice(DISEASE_TEST_MAP[disease])
    result = weighted_choice(RESULT_WEIGHTS)
    pathogen_identified = disease if result == "positive" else None

    turnaround_days = random.randint(1, 5)
    specimen_collection_date = result_date - timedelta(days=turnaround_days)

    patient_age = random.randint(1, 85)

    return {
        "test_name": test_name,
        "test_code": None,
        "specimen_type": specimen_type,
        "result": result,
        "pathogen_identified": pathogen_identified,
        "specimen_collection_date": specimen_collection_date.isoformat(),
        "result_date": result_date.isoformat(),
        "patient_age": patient_age,
        "region": region,
        "facility_name": random.choice(FACILITIES[region]),
    }


RESULT_PHRASES = {
    "positive": "Positive",
    "negative": "Negative",
    "indeterminate": "Indeterminate — repeat testing recommended",
    "pending": "Pending",
}


def write_structured(c):
    ds = random.choice(DATE_STYLES)
    lines = [
        "LABORATORY REPORT",
        f"Facility: {c['facility_name']}, {c['region']}",
        f"Specimen Collection Date: {fmt_date(date.fromisoformat(c['specimen_collection_date']), ds)}",
        f"Result Date: {fmt_date(date.fromisoformat(c['result_date']), ds)}",
        "",
        f"Patient Age: {c['patient_age']} years",
        f"Specimen Type: {c['specimen_type']}",
        f"Test: {c['test_name']}",
        f"Result: {RESULT_PHRASES[c['result']]}",
    ]
    if c["pathogen_identified"]:
        lines.append(f"Pathogen Identified: {c['pathogen_identified']}")
    return "\n".join(lines)


def write_narrative(c):
    ds = random.choice(DATE_STYLES)
    text = (
        f"{c['patient_age']}-year-old patient had a {c['specimen_type'].lower()} specimen "
        f"collected on {fmt_date(date.fromisoformat(c['specimen_collection_date']), ds)} for "
        f"{c['test_name']} at {c['facility_name']}, {c['region']}. "
        f"Result finalized {fmt_date(date.fromisoformat(c['result_date']), ds)}: {RESULT_PHRASES[c['result']].lower()}"
    )
    if c["pathogen_identified"]:
        text += f", identifying {c['pathogen_identified']}"
    text += ". "
    return text


def write_shorthand(c):
    coll = date.fromisoformat(c["specimen_collection_date"])
    res = date.fromisoformat(c["result_date"])
    parts = [
        f"{c['patient_age']}yo, {c['test_name']}, {c['specimen_type']} specimen.",
        f"Collected {fmt_date(coll, random.choice(['short_slash', 'slash', 'month_name']))}, "
        f"result {fmt_date(res, random.choice(['short_slash', 'slash', 'month_name']))}: "
        f"{RESULT_PHRASES[c['result']]}.",
        f"{c['facility_name']}, {c['region']}.",
    ]
    if c["pathogen_identified"]:
        parts.append(f"{c['pathogen_identified']} identified.")
    return " ".join(parts)


WRITERS = [
    (write_structured, 40),
    (write_narrative, 35),
    (write_shorthand, 25),
]


def render(case):
    writer = weighted_choice(WRITERS)
    return writer(case)


def generate_cases(count, start, end):
    cases = []
    region_names = list(REGIONS)
    region_weights = list(REGIONS.values())
    days_span = (end - start).days

    while len(cases) < count:
        result_date = start + timedelta(days=random.randint(0, days_span))
        region = random.choices(region_names, weights=region_weights, k=1)[0]
        cases.append(build_case(result_date, region))

    cases.sort(key=lambda c: c["result_date"])
    return cases[:count]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=500, help="How many reports to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed, for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)

    end = date(2026, 7, 20)
    start = end - timedelta(days=540)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUTPUT_DIR.glob("report_*.txt"):
        old.unlink()

    cases = generate_cases(args.count, start, end)

    ground_truth = []
    for i, case in enumerate(cases, start=1):
        text = render(case)
        filename = f"report_{i:04d}.txt"
        (OUTPUT_DIR / filename).write_text(text, encoding="utf-8")
        ground_truth.append({"file": filename, "text": text, "truth": case})

    (OUTPUT_DIR / "ground_truth.json").write_text(
        json.dumps(ground_truth, indent=2), encoding="utf-8"
    )

    by_result = {}
    for c in cases:
        by_result[c["result"]] = by_result.get(c["result"], 0) + 1

    print(f"Generated {len(cases)} reports in {OUTPUT_DIR}")
    print(f"Date range: {cases[0]['result_date']} to {cases[-1]['result_date']}\n")
    print("Cases by result:")
    for name, n in sorted(by_result.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {name}")
    print("\nground_truth.json written — use it to measure extraction accuracy.")


if __name__ == "__main__":
    main()
