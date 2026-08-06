"""
One-off manual check for the vaccination coverage indicator
(app/services/indicators.py) — run this to sanity-check the numbers
against the real Render Postgres data before the indicator has any
route or frontend wired up to it.

Usage (from backend/, venv active, DATABASE_URL set to Render Postgres
— either $env:DATABASE_URL or backend/.env, same as starting the
backend normally):
    python -m scripts.check_vaccination_coverage
"""

from app.db import SessionLocal
from app.services.indicators import vaccination_coverage_by_region


def main():
    db = SessionLocal()
    try:
        rows = vaccination_coverage_by_region(db)
    finally:
        db.close()

    if not rows:
        print("No rows returned — population_strata may be empty.")
        return

    print(f"{'Region':<20}{'Population':>12}{'Doses':>10}{'Coverage %':>12}")
    print("-" * 54)
    for row in rows:
        print(
            f"{row['region']:<20}"
            f"{row['population']:>12,}"
            f"{row['doses_administered']:>10,}"
            f"{(row['coverage_pct'] if row['coverage_pct'] is not None else 0):>11.2f}%"
        )


if __name__ == "__main__":
    main()
