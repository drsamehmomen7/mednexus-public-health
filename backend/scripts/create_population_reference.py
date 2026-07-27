"""
One-off script: creates a small reference table, region_population, and
fills it with approximate 2025 official population estimates for
Kuwait's six governorates. Used to compute "rate per 100,000" in the
Metabase dashboard — this data is public demographic reference data
(not patient data), so it's fine to use real figures rather than
synthetic placeholders.

Population figures: approximate 2025 official estimates (rounded),
sourced from public reporting on Kuwait's governorates.

Usage (from backend/, with venv activated and DATABASE_URL set to the
Render Postgres connection string):
    python scripts/create_population_reference.py
"""

from sqlalchemy import text
from app.db import engine

POPULATIONS = {
    "Al Asimah": 620_000,
    "Hawalli": 1_050_000,
    "Farwaniya": 1_180_000,
    "Ahmadi": 1_150_000,
    "Jahra": 620_000,
    "Mubarak Al-Kabeer": 360_000,
}

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS region_population (
    region VARCHAR PRIMARY KEY,
    population INTEGER NOT NULL
);
"""

UPSERT_SQL = """
INSERT INTO region_population (region, population)
VALUES (:region, :population)
ON CONFLICT (region) DO UPDATE SET population = EXCLUDED.population;
"""


def main():
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))
        for region, population in POPULATIONS.items():
            conn.execute(text(UPSERT_SQL), {"region": region, "population": population})

    print(f"region_population table ready with {len(POPULATIONS)} rows.")


if __name__ == "__main__":
    main()
