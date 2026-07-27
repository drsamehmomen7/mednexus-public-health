"""
Adds the columns introduced when the schema was extended to match standard
notifiable-disease reporting forms (WHO IDSR / UKHSA / CDC).

Why this script exists: `init_db()` calls SQLAlchemy's `create_all`, which
creates missing TABLES but never alters existing ones. The
notifiable_disease_records table already exists on Render with the original
column set, so new columns have to be added explicitly.

This is a stopgap. Once real data exists, switch to Alembic migrations
rather than hand-written ALTER scripts — noted in db.py too.

Every statement uses IF NOT EXISTS, so running this twice is harmless.

Usage (from backend/, venv active, DATABASE_URL set to Render Postgres):
    python -m scripts.add_extended_case_columns
"""

from sqlalchemy import text
from app.db import engine

# (column name, SQL type, default clause)
NEW_COLUMNS = [
    ("icd10_code", "VARCHAR", ""),
    ("onset_date", "DATE", ""),
    ("occupation", "VARCHAR", ""),
    ("travel_related", "BOOLEAN", ""),
    ("travel_country", "VARCHAR", ""),
    ("vaccination_status", "VARCHAR", "DEFAULT 'unknown'"),
    ("outcome", "VARCHAR", "DEFAULT 'unknown'"),
    ("lab_test_type", "VARCHAR", ""),
]


def main():
    with engine.begin() as conn:
        for name, sql_type, default in NEW_COLUMNS:
            conn.execute(
                text(
                    f"ALTER TABLE notifiable_disease_records "
                    f"ADD COLUMN IF NOT EXISTS {name} {sql_type} {default}"
                )
            )
            print(f"  ensured column: {name} ({sql_type})")

        # Existing rows predate these columns, so the two non-null-by-intent
        # status fields would otherwise be NULL rather than 'unknown'.
        conn.execute(
            text(
                """
                UPDATE notifiable_disease_records
                SET vaccination_status = COALESCE(vaccination_status, 'unknown'),
                    outcome = COALESCE(outcome, 'unknown')
                """
            )
        )

    print(f"\nDone — {len(NEW_COLUMNS)} columns ensured on notifiable_disease_records.")


if __name__ == "__main__":
    main()
