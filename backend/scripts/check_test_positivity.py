"""
One-off manual check for the test positivity indicator
(app/services/indicators.py) — run this to sanity-check the numbers
against the real Render Postgres data.

Usage (from backend/, venv active, DATABASE_URL set to Render Postgres):
    python -m scripts.check_test_positivity
"""

from app.db import SessionLocal
from app.services.indicators import test_positivity_by_region


def main():
    db = SessionLocal()
    try:
        rows = test_positivity_by_region(db)
    finally:
        db.close()

    if not rows:
        print("No rows returned — laboratory_records may be empty.")
        return

    print(f"{'Region':<20}{'Positive':>10}{'Negative':>10}{'Resolved':>10}{'Positivity %':>14}")
    print("-" * 64)
    for row in rows:
        pct = row["positivity_pct"] if row["positivity_pct"] is not None else 0
        print(
            f"{row['region']:<20}"
            f"{row['positive']:>10,}"
            f"{row['negative']:>10,}"
            f"{row['resolved']:>10,}"
            f"{pct:>13.2f}%"
        )


if __name__ == "__main__":
    main()
