"""
One-time (but safe to re-run) migration: adds the nullable batch_label
column to all three report tables if it's missing.

Why this exists as a standalone script rather than being folded into
init_db(): Base.metadata.create_all() (what init_db() calls) only
creates tables that don't exist yet — it never alters an EXISTING
table to add a column a changed model now expects. Any time the Render
database resets (see docs/decisions-log.md, 2026-07-28 and 2026-07-30
incidents) and the resulting fresh table gets created from an OLDER
snapshot of db_models.py than the one currently on disk, this is the
fix — not a full drop-and-recreate.

Uses ADD COLUMN IF NOT EXISTS, so running this against a database that
already has the column is a harmless no-op.

Usage (from backend/, venv active, DATABASE_URL set):
    python -m scripts.add_batch_label_column
"""

from app.db import engine
from sqlalchemy import text

TABLES = [
    "notifiable_disease_records",
    "immunization_records",
    "laboratory_records",
]


def main() -> None:
    with engine.connect() as conn:
        for table in TABLES:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS batch_label VARCHAR"))
        conn.commit()
        print("ALTER TABLE ran for all three. Checking now:\n")

        result = conn.execute(text(
            "SELECT table_name FROM information_schema.columns WHERE column_name = 'batch_label'"
        ))
        found = {row[0] for row in result}

        for table in TABLES:
            status = "OK" if table in found else "MISSING"
            print(f"  {table:<28} batch_label -> {status}")


if __name__ == "__main__":
    main()
