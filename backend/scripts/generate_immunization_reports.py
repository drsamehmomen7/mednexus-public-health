"""
Generates realistic-looking immunization reports as FREE TEXT, the way a
clinic nurse or vaccination registry entry actually reads — not as
structured data. Mirrors generate_synthetic_reports.py's approach and
conventions (same regions/facilities, same date-format variety, same
"write ground truth first, then render text" structure).

The schedule itself is NOT invented — it's transcribed directly from the
Kuwait Ministry of Health's 2025 Childhood Immunization Schedule (the PDF
provided for this project), so ages, vaccines, and doses are realistic
rather than guessed. Two decisions made explicitly, not accidentally:

- Pregnant-mother Tdap doses are OUT OF SCOPE for this generator — the
  "patient" for those is the mother, not a child, and mixing adult and
  paediatric age profiles into one age-in-years field would be more
  confusing than useful for a first version. Only the paediatric/school
  schedule (birth through 16-18 years) is modelled.
- patient_age is recorded in YEARS ONLY (per the schema, and per this
  project's own decision to keep it that way rather than add a
  patient_age_months field) — meaning every dose given before a child's
  first birthday will show patient_age as 0. That's expected, not a bug;
  dose_number and the vaccine/age-band context carry the real signal for
  infant records, the same way a birth certificate's "0 years old" is
  true but not very informative on its own.
- Each report describes ONE vaccine administration event (one dose of one
  vaccine), matching the schema's one-record-per-event design and the
  same convention used for Notifiable Disease reports. Real immunization
  registries work the same way: a same-day visit giving three vaccines
  produces three separate entries, not one entry listing three vaccines.
  Some reports mention the OTHER vaccines given at the same visit as
  flavour text (for realism), but ground truth only tracks the one
  vaccine the report is actually about.

Outputs two things:
  1. data/immunization_reports/*.txt   — one free-text report per file
  2. data/immunization_reports/ground_truth.json — what each report
     actually says, so extraction accuracy can be measured against a
     known answer, the same way the Notifiable Disease pipeline is.

SYNTHETIC DATA ONLY. No real patients, no real facilities, no real identifiers.

Usage (from backend/):
    python -m scripts.generate_immunization_reports            # default 500
    python -m scripts.generate_immunization_reports --count 100
"""

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "immunization_reports"

# Same six governorates and facility names as the Notifiable Disease
# generator, for consistency across report types sharing one dashboard.
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

# Transcribed from the Kuwait MOH 2025 Childhood Immunization Schedule.
# Each entry: (age_in_days, age_in_months_or_None, [(vaccine,
# dose_number_or_None, route, other_vaccines_same_visit)]).
#
# age_in_months is the schedule's OWN age label (2, 3, 4, 6, 12, 18 months)
# for anything before a child's 2nd birthday — populated as
# patient_age_months in the ground truth and used to phrase the report
# text ("2-month-old"), because "0-year-old" is technically true but
# communicates almost nothing for this age range. It's None from age 2
# onward, where stating age in whole years is how these are actually
# recorded (a 2-year-old, not a "24-month-old").
#
# dose_number is None for single-dose or booster-only vaccines where
# numbering the primary series doesn't apply (BCG, Meningococcal ACWY,
# DTaP, MMRV) — Tdap's two school boosters ARE numbered (1, 2) since
# there are genuinely two of them to distinguish.
SCHEDULE = [
    (1,    0,    [("Hepatitis B", 1, "intramuscular", [])]),
    (60,   2,    [("Hexa", 1, "intramuscular", ["Pneumococcal", "Rota"]),
                  ("Pneumococcal", 1, "intramuscular", ["Hexa", "Rota"]),
                  ("Rota", 1, "oral", ["Hexa", "Pneumococcal"])]),
    (90,   3,    [("BCG", None, "intradermal", [])]),
    (120,  4,    [("Hexa", 2, "intramuscular", ["Pneumococcal", "Rota"]),
                  ("Pneumococcal", 2, "intramuscular", ["Hexa", "Rota"]),
                  ("Rota", 2, "oral", ["Hexa", "Pneumococcal"])]),
    (180,  6,    [("Hexa", 3, "intramuscular", ["Pneumococcal", "Rota"]),
                  ("Pneumococcal", 3, "intramuscular", ["Hexa", "Rota"]),
                  ("Rota", 3, "oral", ["Hexa", "Pneumococcal"])]),
    (365,  12,   [("OPV", 1, "oral", ["MMR", "Varicella", "Meningococcal ACWY"]),
                  ("MMR", 1, "subcutaneous", ["OPV", "Varicella", "Meningococcal ACWY"]),
                  ("Varicella", 1, "subcutaneous", ["OPV", "MMR", "Meningococcal ACWY"]),
                  ("Meningococcal ACWY", None, "intramuscular", ["OPV", "MMR", "Varicella"])]),
    (545,  18,   [("OPV", 2, "oral", ["Hexa", "Pneumococcal"]),
                  ("Hexa", 4, "intramuscular", ["OPV", "Pneumococcal"]),
                  ("Pneumococcal", 4, "intramuscular", ["OPV", "Hexa"])]),
    (730,  None, [("MMRV", 1, "subcutaneous", [])]),
    (1277, None, [("DTaP", None, "intramuscular", [])]),
    (3900, None, [("Tdap", 1, "intramuscular", [])]),   # ~10-12 years
    (6200, None, [("Tdap", 2, "intramuscular", [])]),   # ~16-18 years
]

ROUTE_ABBR = {
    "intramuscular": "I.M.", "subcutaneous": "S.C.", "oral": "Oral",
    "intradermal": "I.D.", "intranasal": "intranasal",
}

# Adverse events are the exception, not the rule, and almost always mild
# when they occur — matching how AEFI (adverse event following
# immunization) reporting actually skews in practice.
ADVERSE_EVENT_RATE = 0.06
ADVERSE_EVENT_SEVERITY_WEIGHTS = [("mild", 75), ("moderate", 20), ("severe", 5)]
# Split by age so a 16-year-old's Tdap booster doesn't read as infant
# "fussiness" — same principle as OCCUPATIONS_BY_AGE in the disease
# generator (age-inappropriate detail is what makes generated text read
# as obviously fake).
ADVERSE_EVENT_DESCRIPTIONS_INFANT = {
    "mild": ["low-grade fever", "mild redness at injection site", "mild fussiness", "mild swelling at injection site"],
    "moderate": ["fever above 39C", "prolonged crying over 3 hours", "marked swelling at injection site"],
    "severe": ["febrile seizure", "anaphylaxis", "hospitalization"],
}
ADVERSE_EVENT_DESCRIPTIONS_OLDER = {
    "mild": ["low-grade fever", "mild soreness at injection site", "mild headache", "mild redness at injection site"],
    "moderate": ["fever above 39C", "marked swelling at injection site", "generalized malaise"],
    "severe": ["anaphylaxis", "hospitalization", "syncope requiring observation"],
}

LOT_PREFIXES = ["KW", "MOH", "IMZ"]


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


def build_case(admin_date, region):
    """Builds the ground-truth facts for one vaccination event."""
    age_days, age_months, options = random.choice(SCHEDULE)
    vaccine_name, dose_number, route, co_administered = random.choice(options)

    patient_age = age_days // 365  # whole years, always populated
    patient_age_months = age_months  # None once years is the natural way to state it

    is_infant = age_months is not None
    adverse_event = random.random() < ADVERSE_EVENT_RATE
    severity = weighted_choice(ADVERSE_EVENT_SEVERITY_WEIGHTS) if adverse_event else "none"
    if adverse_event:
        descriptions = ADVERSE_EVENT_DESCRIPTIONS_INFANT if is_infant else ADVERSE_EVENT_DESCRIPTIONS_OLDER
        description = random.choice(descriptions[severity])
    else:
        description = None

    lot_number = f"{random.choice(LOT_PREFIXES)}-{random.randint(10000, 99999)}"

    return {
        "vaccine_name": vaccine_name,
        "dose_number": dose_number,
        "lot_number": lot_number,
        "administration_date": admin_date.isoformat(),
        "route": route,
        "patient_age": patient_age,
        "patient_age_months": patient_age_months,
        "region": region,
        "facility_name": random.choice(FACILITIES[region]),
        "adverse_event_reported": adverse_event,
        "adverse_event_severity": severity,
        "adverse_event_description": description,
        "_co_administered": co_administered,  # flavour text only, not a ground-truth field
    }


def age_phrase(c):
    """'2-month-old' for infants, '16-year-old' otherwise — matches how
    these ages are actually stated, not a mechanical years-only rendering."""
    if c["patient_age_months"] is not None:
        if c["patient_age_months"] == 0:
            return "newborn"
        return f"{c['patient_age_months']}-month-old"
    return f"{c['patient_age']}-year-old"


def age_phrase_short(c):
    """Shorthand form: '2mo' / '16yo' — same distinction as age_phrase,
    but terse, matching the clinic-shorthand voice's abbreviation style."""
    if c["patient_age_months"] is not None:
        return "newborn" if c["patient_age_months"] == 0 else f"{c['patient_age_months']}mo"
    return f"{c['patient_age']}yo"


def dose_phrase(vaccine, dose_number):
    if dose_number is None:
        return f"{vaccine} vaccine"
    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th (booster)"}.get(dose_number, f"{dose_number}th")
    return f"{ordinal} dose of {vaccine} vaccine"


def write_structured(c):
    """A nurse filling out the immunization register properly."""
    ds = random.choice(DATE_STYLES)
    lines = [
        "IMMUNIZATION RECORD",
        f"Facility: {c['facility_name']}, {c['region']}",
        f"Date of administration: {fmt_date(date.fromisoformat(c['administration_date']), ds)}",
        "",
        f"Patient age: {age_phrase(c)}",
        f"Vaccine administered: {dose_phrase(c['vaccine_name'], c['dose_number'])}",
        f"Route: {ROUTE_ABBR[c['route']]}",
        f"Lot number: {c['lot_number']}",
    ]
    if c["_co_administered"]:
        lines.append(f"Given concurrently with: {', '.join(c['_co_administered'])}")
    if c["adverse_event_reported"]:
        lines.append(
            f"Adverse event following immunization: {c['adverse_event_description']} "
            f"({c['adverse_event_severity']})."
        )
    else:
        lines.append("No adverse event reported.")
    return "\n".join(lines)


def write_narrative(c):
    """Prose clinical note — no headings, just paragraphs."""
    ds = random.choice(DATE_STYLES)
    text = (
        f"{age_phrase(c)} patient received the "
        f"{dose_phrase(c['vaccine_name'], c['dose_number'])} at {c['facility_name']}, "
        f"{c['region']} on {fmt_date(date.fromisoformat(c['administration_date']), ds)}, "
        f"administered {ROUTE_ABBR[c['route']].lower().rstrip('.')}. "
    )
    if c["_co_administered"]:
        text += f"Given at the same visit as {' and '.join(c['_co_administered'])}. "
    if c["adverse_event_reported"]:
        text += f"Patient developed {c['adverse_event_description']} following the dose ({c['adverse_event_severity']}). "
    else:
        text += "No adverse reaction was observed. "
    return text


def write_shorthand(c):
    """Clinic shorthand — abbreviations, fragments, minimal punctuation."""
    rep = date.fromisoformat(c["administration_date"])
    parts = [
        f"{age_phrase_short(c)}, {dose_phrase(c['vaccine_name'], c['dose_number'])}, "
        f"{ROUTE_ABBR[c['route']]}, lot {c['lot_number']}.",
        f"Given {fmt_date(rep, random.choice(['short_slash', 'slash', 'month_name']))} "
        f"at {c['facility_name']}, {c['region']}.",
    ]
    if c["_co_administered"]:
        parts.append(f"Also given: {', '.join(c['_co_administered'])}.")
    if c["adverse_event_reported"]:
        parts.append(f"AEFI: {c['adverse_event_description']} ({c['adverse_event_severity']}).")
    else:
        parts.append("No AEFI.")
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
        admin_date = start + timedelta(days=random.randint(0, days_span))
        region = random.choices(region_names, weights=region_weights, k=1)[0]
        cases.append(build_case(admin_date, region))

    cases.sort(key=lambda c: c["administration_date"])
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
        truth = {k: v for k, v in case.items() if not k.startswith("_")}
        ground_truth.append({"file": filename, "text": text, "truth": truth})

    (OUTPUT_DIR / "ground_truth.json").write_text(
        json.dumps(ground_truth, indent=2), encoding="utf-8"
    )

    by_vaccine = {}
    for c in cases:
        by_vaccine[c["vaccine_name"]] = by_vaccine.get(c["vaccine_name"], 0) + 1

    print(f"Generated {len(cases)} reports in {OUTPUT_DIR}")
    print(f"Date range: {cases[0]['administration_date']} to {cases[-1]['administration_date']}\n")
    print("Cases by vaccine:")
    for name, n in sorted(by_vaccine.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {name}")
    print("\nground_truth.json written — use it to measure extraction accuracy.")


if __name__ == "__main__":
    main()
