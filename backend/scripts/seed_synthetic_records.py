"""
One-off script: posts a handful of synthetic Notifiable Disease records to
the deployed Render backend's /save endpoint, so the Metabase dashboard
("Notifiable Disease Overview") has more than the single test record
(id=1) to show shape with.

Synthetic data only — no real patient data, per project ground rules.

Usage (from backend/, with venv activated):
    python scripts/seed_synthetic_records.py

Render's free tier spins down after inactivity, so the first request can
take up to ~50 seconds while the service wakes up. This is expected.
"""

import requests

API_URL = "https://mednexus-public-health-api.onrender.com/reports/notifiable-disease/save"

# A mix of diseases, Kuwait governorates, and confidence levels (some
# flagged needed_review=True, most not) so all 4 dashboard indicators
# show real variation instead of a single flat row.
RECORDS = [
    {
        "case": {
            "disease_name": "Measles",
            "diagnosis_status": "confirmed",
            "report_date": "2026-06-20",
            "patient_age": 8,
            "patient_sex": "female",
            "region": "Hawalli",
            "facility_name": "Mubarak Al-Kabeer Hospital",
            "lab_confirmed": True,
            "source_excerpt": "synthetic test record",
        },
        "confidence": {"disease_name": {"source": "model", "score": 0.95}},
    },
    {
        "case": {
            "disease_name": "Mumps",
            "diagnosis_status": "probable",
            "report_date": "2026-06-25",
            "patient_age": 14,
            "patient_sex": "male",
            "region": "Farwaniya",
            "facility_name": "Farwaniya Hospital",
            "lab_confirmed": False,
            "source_excerpt": "synthetic test record",
        },
        "confidence": {"disease_name": {"source": "model", "score": 0.42}},
    },
    {
        "case": {
            "disease_name": "Hepatitis A",
            "diagnosis_status": "confirmed",
            "report_date": "2026-07-02",
            "patient_age": 29,
            "patient_sex": "male",
            "region": "Ahmadi",
            "facility_name": "Ahmadi Hospital",
            "lab_confirmed": True,
            "source_excerpt": "synthetic test record",
        },
        "confidence": {"disease_name": {"source": "model", "score": 0.88}},
    },
    {
        "case": {
            "disease_name": "Typhoid",
            "diagnosis_status": "suspected",
            "report_date": "2026-07-05",
            "patient_age": 45,
            "patient_sex": "unknown",
            "region": "Jahra",
            "facility_name": "Jahra Hospital",
            "lab_confirmed": False,
            "source_excerpt": "synthetic test record",
        },
        "confidence": {"disease_name": {"source": "model", "score": 0.35}},
    },
    {
        "case": {
            "disease_name": "Chickenpox",
            "diagnosis_status": "confirmed",
            "report_date": "2026-07-10",
            "patient_age": 6,
            "patient_sex": "female",
            "region": "Al Asimah",
            "facility_name": "Amiri Hospital",
            "lab_confirmed": True,
            "source_excerpt": "synthetic test record",
        },
        "confidence": {"disease_name": {"source": "model", "score": 0.91}},
    },
    {
        "case": {
            "disease_name": "Rubella",
            "diagnosis_status": "probable",
            "report_date": "2026-07-15",
            "patient_age": 22,
            "patient_sex": "female",
            "region": "Mubarak Al-Kabeer",
            "facility_name": "Adan Hospital",
            "lab_confirmed": False,
            "source_excerpt": "synthetic test record",
        },
        "confidence": {"disease_name": {"source": "model", "score": 0.93}},
    },
]


def main():
    print(f"Seeding {len(RECORDS)} synthetic records to {API_URL}")
    print("(Render free tier may take ~50s to wake up on the first request)\n")

    for i, payload in enumerate(RECORDS, start=1):
        try:
            response = requests.post(API_URL, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            print(f"[{i}/{len(RECORDS)}] saved id={result.get('id')} "
                  f"({payload['case']['disease_name']}, {payload['case']['region']})")
        except requests.RequestException as exc:
            print(f"[{i}/{len(RECORDS)}] FAILED: {exc}")

    print("\nDone. Refresh the Metabase dashboard to see the new data.")


if __name__ == "__main__":
    main()
