"""
Generates realistic-looking notifiable disease reports as FREE TEXT, the way
clinicians actually write them — not as structured data.

Why free text: the whole point of this product is extracting structure from
messy clinical prose. Generating clean structured records would test nothing.
So each report is written in one of several clinician "voices", ranging from
a careful structured note to clinic shorthand ("34yo F, fever x3d, ?measles").

Why it isn't just random: random data produces a flat, meaningless dashboard.
This generator builds actual epidemiology:
  - A measles outbreak in one governorate over ~6 weeks, with a proper
    epidemic curve (slow start, peak, decline) — so the dashboard shows a
    real signal a decision-maker would react to.
  - Background sporadic cases of other diseases across the year.
  - Disease-specific age profiles (measles/chickenpox skew paediatric,
    hepatitis skews adult), seasonality (influenza in winter, typhoid and
    foodborne illness in summer), and realistic rates of lab confirmation,
    vaccination status, and outcome.
  - Regional case counts roughly proportional to population, so rates per
    100,000 are not absurd.

Outputs two things:
  1. data/synthetic_reports/*.txt   — one free-text report per file
  2. data/synthetic_reports/ground_truth.json — what each report actually
     says, so extraction accuracy can be measured later against a known
     answer rather than eyeballed.

SYNTHETIC DATA ONLY. No real patients, no real facilities, no real identifiers.
Facility names below are invented and deliberately generic.

Usage (from backend/):
    python -m scripts.generate_synthetic_reports            # default 500
    python -m scripts.generate_synthetic_reports --count 100
"""

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic_reports"

# Population weights drive how many cases each region gets, so rates per
# 100,000 stay plausible instead of every region having identical counts.
REGIONS = {
    "Al Asimah": 620_000,
    "Hawalli": 1_050_000,
    "Farwaniya": 1_180_000,
    "Ahmadi": 1_150_000,
    "Jahra": 620_000,
    "Mubarak Al-Kabeer": 360_000,
}

# Invented facility names, one set per region. Not real institutions.
FACILITIES = {
    "Al Asimah": ["Central District Hospital", "Qibla Health Centre", "North Clinic"],
    "Hawalli": ["Eastern General Hospital", "Salmiya Health Centre", "Bayan Clinic"],
    "Farwaniya": ["Western General Hospital", "Khaitan Health Centre", "Ardiya Clinic"],
    "Ahmadi": ["Southern General Hospital", "Fahaheel Health Centre", "Mangaf Clinic"],
    "Jahra": ["Northern General Hospital", "Jahra Health Centre", "Sulaibiya Clinic"],
    "Mubarak Al-Kabeer": ["Adan District Hospital", "Qurain Health Centre", "Messila Clinic"],
}

# Per-disease epidemiology. age_profile is a list of (age_range, weight).
DISEASES = {
    "Measles": {
        "age_profile": [((0, 4), 35), ((5, 14), 40), ((15, 24), 15), ((25, 44), 10)],
        "lab_confirm_rate": 0.65,
        "vaccine_relevant": True,
        "unvaccinated_rate": 0.70,
        "severe_rate": 0.15,
        "months": None,
        "lab_tests": ["measles IgM serology", "PCR", "serology"],
        "symptoms": ["fever", "maculopapular rash", "cough", "coryza", "conjunctivitis", "Koplik spots"],
    },
    "Chickenpox": {
        "age_profile": [((0, 4), 30), ((5, 14), 50), ((15, 24), 15), ((25, 44), 5)],
        "lab_confirm_rate": 0.20,
        "vaccine_relevant": True,
        "unvaccinated_rate": 0.55,
        "severe_rate": 0.05,
        "months": None,
        "lab_tests": ["PCR", "clinical diagnosis"],
        "symptoms": ["fever", "vesicular rash", "itching", "malaise"],
    },
    "Mumps": {
        "age_profile": [((5, 14), 45), ((15, 24), 35), ((25, 44), 20)],
        "lab_confirm_rate": 0.45,
        "vaccine_relevant": True,
        "unvaccinated_rate": 0.50,
        "severe_rate": 0.06,
        "months": None,
        "lab_tests": ["mumps IgM serology", "PCR"],
        "symptoms": ["parotid swelling", "fever", "jaw pain", "difficulty chewing"],
    },
    "Rubella": {
        "age_profile": [((5, 14), 35), ((15, 24), 35), ((25, 44), 30)],
        "lab_confirm_rate": 0.55,
        "vaccine_relevant": True,
        "unvaccinated_rate": 0.60,
        "severe_rate": 0.04,
        "months": None,
        "lab_tests": ["rubella IgM serology", "PCR"],
        "symptoms": ["mild rash", "low-grade fever", "posterior cervical lymphadenopathy"],
    },
    "Typhoid fever": {
        "age_profile": [((5, 14), 20), ((15, 24), 30), ((25, 44), 35), ((45, 64), 15)],
        "lab_confirm_rate": 0.60,
        "vaccine_relevant": False,
        "unvaccinated_rate": 0.0,
        "severe_rate": 0.20,
        "months": [5, 6, 7, 8, 9],
        "lab_tests": ["blood culture", "Widal test", "stool culture"],
        "symptoms": ["prolonged fever", "abdominal pain", "headache", "constipation", "malaise"],
    },
    "Hepatitis A": {
        "age_profile": [((5, 14), 25), ((15, 24), 25), ((25, 44), 35), ((45, 64), 15)],
        "lab_confirm_rate": 0.75,
        "vaccine_relevant": True,
        "unvaccinated_rate": 0.65,
        "severe_rate": 0.12,
        "months": None,
        "lab_tests": ["hepatitis A IgM", "LFTs", "serology"],
        "symptoms": ["jaundice", "dark urine", "nausea", "right upper quadrant pain", "fatigue"],
    },
    "Dengue fever": {
        "age_profile": [((15, 24), 25), ((25, 44), 45), ((45, 64), 25), ((65, 80), 5)],
        "lab_confirm_rate": 0.70,
        "vaccine_relevant": False,
        "unvaccinated_rate": 0.0,
        "severe_rate": 0.18,
        "months": [6, 7, 8, 9, 10],
        "lab_tests": ["NS1 antigen", "dengue IgM", "PCR"],
        "symptoms": ["high fever", "severe headache", "retro-orbital pain", "myalgia", "rash"],
    },
    "Influenza": {
        "age_profile": [((0, 4), 15), ((5, 14), 20), ((15, 24), 15), ((25, 44), 25), ((45, 64), 15), ((65, 85), 10)],
        "lab_confirm_rate": 0.50,
        "vaccine_relevant": True,
        "unvaccinated_rate": 0.75,
        "severe_rate": 0.10,
        "months": [11, 12, 1, 2, 3],
        "lab_tests": ["rapid influenza antigen", "PCR"],
        "symptoms": ["fever", "cough", "sore throat", "myalgia", "fatigue"],
    },
    "Salmonellosis": {
        "age_profile": [((0, 4), 20), ((5, 14), 20), ((15, 24), 20), ((25, 44), 25), ((45, 64), 15)],
        "lab_confirm_rate": 0.80,
        "vaccine_relevant": False,
        "unvaccinated_rate": 0.0,
        "severe_rate": 0.10,
        "months": [5, 6, 7, 8, 9],
        "lab_tests": ["stool culture", "PCR"],
        "symptoms": ["diarrhoea", "abdominal cramps", "fever", "vomiting"],
    },
    "Meningococcal disease": {
        "age_profile": [((0, 4), 30), ((5, 14), 20), ((15, 24), 30), ((25, 44), 20)],
        "lab_confirm_rate": 0.85,
        "vaccine_relevant": True,
        "unvaccinated_rate": 0.55,
        "severe_rate": 0.60,
        "months": None,
        "lab_tests": ["CSF culture", "blood culture", "PCR"],
        "symptoms": ["fever", "neck stiffness", "photophobia", "petechial rash", "altered consciousness"],
    },
}

# Split by what a person that age plausibly does. An earlier version put
# "student" in one bucket for everyone under 18, which produced 1-year-old
# students — the kind of detail that makes generated data obviously fake.
OCCUPATIONS_BY_AGE = {
    "preschool": [None, None, None, "nursery attendee"],
    "school_age": ["student", "student", None],
    "adult": ["teacher", "food handler", "nurse", "healthcare worker", "office worker",
              "driver", "engineer", "shop assistant", "childcare worker", "student",
              None, None, None],
    "elderly": ["retired", None, None],
}

TRAVEL_COUNTRIES = ["India", "Egypt", "Pakistan", "Philippines", "Bangladesh",
                    "Sri Lanka", "Turkey", "Thailand", "Nepal", "Indonesia"]


def weighted_choice(pairs):
    items, weights = zip(*pairs)
    return random.choices(items, weights=weights, k=1)[0]


def pick_age(profile):
    age_range = weighted_choice(profile)
    return random.randint(age_range[0], age_range[1])


def pick_occupation(age):
    if age < 5:
        bucket = "preschool"
    elif age < 18:
        bucket = "school_age"
    elif age >= 65:
        bucket = "elderly"
    else:
        bucket = "adult"
    return random.choice(OCCUPATIONS_BY_AGE[bucket])


def occupation_phrase(occupation, leading_comma=False):
    """'retired' is a state, not a job title — 'works as a retired' reads wrong."""
    if not occupation:
        return ""
    verb = "is" if occupation == "retired" else "works as a"
    phrase = f"{verb} {occupation}"
    return f", {phrase}," if leading_comma else phrase


def fmt_date(d, style):
    """Real reports don't use one date format. Neither does this."""
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


def build_case(disease_name, report_date, region, outbreak=False):
    """Builds the ground-truth facts for one case, before it's written up."""
    profile = DISEASES[disease_name]
    age = pick_age(profile["age_profile"])
    sex = random.choice(["male", "female"])
    onset_offset = random.randint(1, 12)
    onset_date = report_date - timedelta(days=onset_offset)

    lab_confirmed = random.random() < profile["lab_confirm_rate"]
    if lab_confirmed:
        diagnosis_status = "confirmed"
    else:
        diagnosis_status = random.choices(
            ["suspected", "probable"], weights=[65, 35], k=1
        )[0]

    if profile["vaccine_relevant"]:
        if random.random() < profile["unvaccinated_rate"]:
            vaccination_status = "not_vaccinated"
        else:
            vaccination_status = random.choices(
                ["vaccinated", "partially_vaccinated", "unknown"],
                weights=[55, 30, 15], k=1,
            )[0]
    else:
        vaccination_status = "unknown"

    severe = random.random() < profile["severe_rate"]
    if severe:
        outcome = random.choices(
            ["hospitalized", "recovering", "died"], weights=[60, 30, 10], k=1
        )[0]
    else:
        outcome = random.choices(
            ["recovered", "recovering", "unknown"], weights=[55, 35, 10], k=1
        )[0]

    # Travel is a plausible source for imported infections, and much less
    # likely inside a local outbreak cluster.
    travel_chance = 0.05 if outbreak else 0.18
    travel_related = random.random() < travel_chance
    travel_country = random.choice(TRAVEL_COUNTRIES) if travel_related else None

    return {
        "disease_name": disease_name,
        "diagnosis_status": diagnosis_status,
        "onset_date": onset_date.isoformat(),
        "report_date": report_date.isoformat(),
        "patient_age": age,
        "patient_sex": sex,
        "occupation": pick_occupation(age),
        "region": region,
        "facility_name": random.choice(FACILITIES[region]),
        "travel_related": travel_related,
        "travel_country": travel_country,
        "vaccination_status": vaccination_status,
        "outcome": outcome,
        "lab_confirmed": lab_confirmed,
        "lab_test_type": random.choice(profile["lab_tests"]) if lab_confirmed else None,
    }


# --- The four clinician "voices" -------------------------------------------

def write_structured(c, profile):
    """A careful clinician filling out the form properly."""
    ds = random.choice(DATE_STYLES)
    sym = ", ".join(random.sample(profile["symptoms"], k=min(3, len(profile["symptoms"]))))
    lines = [
        "NOTIFIABLE DISEASE REPORT",
        f"Reporting facility: {c['facility_name']}, {c['region']}",
        f"Date of report: {fmt_date(date.fromisoformat(c['report_date']), ds)}",
        "",
        f"Patient: {c['patient_age']}-year-old {c['patient_sex']}",
    ]
    if c["occupation"]:
        lines.append(f"Occupation: {c['occupation']}")
    lines += [
        f"Date of symptom onset: {fmt_date(date.fromisoformat(c['onset_date']), ds)}",
        f"Presenting symptoms: {sym}.",
        f"Suspected condition: {c['disease_name']}.",
    ]
    if c["lab_confirmed"]:
        lines.append(f"Laboratory: {c['lab_test_type']} positive. Diagnosis confirmed.")
    else:
        lines.append(f"Laboratory: {c['diagnosis_status']} case, results pending.")
    if profile["vaccine_relevant"]:
        vmap = {
            "not_vaccinated": "Patient is not vaccinated against this disease.",
            "vaccinated": "Patient has documented vaccination for this disease.",
            "partially_vaccinated": "Patient partially vaccinated (incomplete schedule).",
            "unknown": "Vaccination status not documented.",
        }
        lines.append(vmap[c["vaccination_status"]])
    if c["travel_related"]:
        lines.append(f"Travel history: recent travel to {c['travel_country']}.")
    else:
        lines.append("Travel history: none reported.")
    lines.append(f"Outcome at time of reporting: {c['outcome'].replace('_', ' ')}.")
    return "\n".join(lines)


def write_narrative(c, profile):
    """A prose clinical note — no headings, just paragraphs."""
    ds = random.choice(DATE_STYLES)
    sym = " and ".join(random.sample(profile["symptoms"], k=2))
    occ = occupation_phrase(c["occupation"], leading_comma=True)
    text = (
        f"A {c['patient_age']}-year-old {c['patient_sex']} patient{occ} presented to "
        f"{c['facility_name']} in {c['region']} on "
        f"{fmt_date(date.fromisoformat(c['report_date']), ds)}. "
        f"Symptoms began on {fmt_date(date.fromisoformat(c['onset_date']), ds)} with {sym}. "
    )
    if c["lab_confirmed"]:
        text += f"{c['lab_test_type'].capitalize()} returned positive, confirming {c['disease_name']}. "
    else:
        text += f"{c['disease_name']} is {c['diagnosis_status']}; laboratory results are still awaited. "
    if c["travel_related"]:
        text += f"The patient returned from {c['travel_country']} shortly before onset. "
    if profile["vaccine_relevant"] and c["vaccination_status"] == "not_vaccinated":
        text += "There is no record of vaccination against this disease. "
    if c["outcome"] == "died":
        text += "The patient subsequently died."
    elif c["outcome"] == "hospitalized":
        text += "The patient has been admitted for inpatient management."
    elif c["outcome"] == "recovered":
        text += "The patient has since recovered."
    else:
        text += "The patient remains under observation."
    return text


def write_shorthand(c, profile):
    """Clinic shorthand — abbreviations, fragments, minimal punctuation."""
    sym = random.choice(profile["symptoms"])
    sex_abbr = "M" if c["patient_sex"] == "male" else "F"
    onset = date.fromisoformat(c["onset_date"])
    rep = date.fromisoformat(c["report_date"])
    days = (rep - onset).days
    parts = [
        f"{c['patient_age']}yo {sex_abbr}, c/o {sym} x{days}d.",
        f"Seen {fmt_date(rep, random.choice(['short_slash', 'slash', 'month_name']))} at {c['facility_name']}, {c['region']}.",
    ]
    if c["lab_confirmed"]:
        parts.append(f"{c['lab_test_type']} +ve -> {c['disease_name']} confirmed.")
    elif c["diagnosis_status"] == "probable":
        # "?X" is shorthand for query/suspected only. Writing it for probable
        # cases too made the text carry no probable/suspected distinction at
        # all, so extraction was scored wrong for reading it correctly.
        parts.append(f"Probable {c['disease_name']}. Labs pending.")
    else:
        parts.append(f"?{c['disease_name']}. Labs pending.")
    if profile["vaccine_relevant"] and c["vaccination_status"] == "not_vaccinated":
        parts.append("No vacc hx.")
    if c["travel_related"]:
        parts.append(f"Travel hx: {c['travel_country']}.")
    if c["outcome"] == "hospitalized":
        parts.append("Admitted.")
    elif c["outcome"] == "died":
        parts.append("Pt died.")
    return " ".join(parts)


def write_with_differential(c, profile):
    """
    Includes a ruled-out differential diagnosis — deliberately, because
    negation handling is the extraction's hardest case and needs to appear
    in the test data, not just in unit tests.
    """
    ds = random.choice(DATE_STYLES)
    others = [d for d in DISEASES if d != c["disease_name"]]
    excluded = random.choice(others)
    sym = ", ".join(random.sample(profile["symptoms"], k=2))
    text = (
        f"{c['patient_age']}-year-old {c['patient_sex']}, presented "
        f"{fmt_date(date.fromisoformat(c['report_date']), ds)} at {c['facility_name']}, "
        f"{c['region']}. Onset {fmt_date(date.fromisoformat(c['onset_date']), ds)} with {sym}. "
        f"{excluded} was ruled out on negative testing. "
    )
    if c["lab_confirmed"]:
        text += f"{c['disease_name']} confirmed by {c['lab_test_type']}. "
    else:
        text += f"Working diagnosis {c['disease_name']} ({c['diagnosis_status']}), awaiting confirmation. "
    if c["occupation"]:
        verb = "is" if c["occupation"] == "retired" else "works as a"
        text += f"Patient {verb} {c['occupation']}. "
    if c["outcome"] in ("hospitalized", "died"):
        text += "Admitted for management." if c["outcome"] == "hospitalized" else "Fatal outcome."
    return text


WRITERS = [
    (write_structured, 30),
    (write_narrative, 30),
    (write_shorthand, 25),
    (write_with_differential, 15),
]


def render(case):
    profile = DISEASES[case["disease_name"]]
    writer = weighted_choice(WRITERS)
    return writer(case, profile)


# --- Case scheduling: this is what makes the data epidemiological ----------

def generate_cases(count, start, end):
    cases = []
    days_span = (end - start).days

    # 1. A measles outbreak: one region, ~6 weeks, with an epidemic curve.
    outbreak_region = "Farwaniya"
    outbreak_start = start + timedelta(days=random.randint(60, days_span - 60))
    outbreak_n = max(20, int(count * 0.12))
    # Weekly shape: slow build, peak, decline — a classic curve.
    curve = [0.06, 0.14, 0.24, 0.26, 0.18, 0.12]
    for week_index, share in enumerate(curve):
        n_week = round(outbreak_n * share)
        for _ in range(n_week):
            d = outbreak_start + timedelta(days=week_index * 7 + random.randint(0, 6))
            if d > end:
                continue
            cases.append(build_case("Measles", d, outbreak_region, outbreak=True))

    # 2. Background sporadic cases everywhere else.
    region_names = list(REGIONS)
    region_weights = list(REGIONS.values())
    disease_names = list(DISEASES)

    while len(cases) < count:
        disease = random.choice(disease_names)
        months = DISEASES[disease]["months"]
        for _ in range(40):  # try to land in-season before giving up
            d = start + timedelta(days=random.randint(0, days_span))
            if months is None or d.month in months:
                break
        region = random.choices(region_names, weights=region_weights, k=1)[0]
        cases.append(build_case(disease, d, region))

    cases.sort(key=lambda c: c["report_date"])
    return cases[:count]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=500, help="How many reports to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed, for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)

    end = date(2026, 7, 20)
    start = end - timedelta(days=540)  # ~18 months, so year filtering is meaningful

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

    by_disease = {}
    for c in cases:
        by_disease[c["disease_name"]] = by_disease.get(c["disease_name"], 0) + 1

    print(f"Generated {len(cases)} reports in {OUTPUT_DIR}")
    print(f"Date range: {cases[0]['report_date']} to {cases[-1]['report_date']}\n")
    print("Cases by disease:")
    for name, n in sorted(by_disease.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {name}")
    print("\nground_truth.json written — use it to measure extraction accuracy.")


if __name__ == "__main__":
    main()
