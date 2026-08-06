"""
One-off cleanup: empties immunization_records and laboratory_records
before a clean re-load. Needed because load_immunization_reports.py and
load_laboratory_reports.py only INSERT — they never clear existing rows
first, so running --limit 10 as a trial and then the full run (without
clearing in between) leaves 10 duplicated records behind.

Does NOT touch notifiable_disease_records — that table was never
re-loaded in this session and is untouched/correct at 501 rows.

Usage (from backend/, venv active, DATABASE_URL set to Render Postgres):
    python -m scripts.clear_immunization_and_lab_records
"""

from sqlalchemy import text
from app.db import SessionLocal


def main():
    db = SessionLocal()
    try:
        imm_before = db.execute(text("SELECT COUNT(*) FROM immunization_records")).scalar()
        lab_before = db.execute(text("SELECT COUNT(*) FROM laboratory_records")).scalar()
        print(f"Before: immunization_records={imm_before}, laboratory_records={lab_before}")

        db.execute(text("DELETE FROM immunization_records"))
        db.execute(text("DELETE FROM laboratory_records"))
        db.commit()

        print("Both tables cleared. Now re-run the full loaders once each:")
        print("  python -m scripts.load_immunization_reports")
        print("  python -m scripts.load_laboratory_reports")
    finally:
        db.close()


if __name__ == "__main__":
    main()
