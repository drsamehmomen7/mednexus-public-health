"""
Creates `population_strata`: population broken down by region x age group x
sex, so "rate per 100,000" can be computed for EVERY dashboard breakdown
(by sex, by age group, by region), not just the region one.

IMPORTANT — how these numbers were derived, and their limits:
- Governorate totals are real: approximate official 2025 estimates.
- The age-group and sex SPLIT within each governorate is NOT published at
  governorate level anywhere public. What is published is the national
  distribution. So national proportions are applied uniformly to every
  governorate.
- That means: regional totals are solid, but the age/sex split per region
  is a modelled approximation, not an official figure. It is good enough
  to make rates comparable and directionally meaningful; it is NOT good
  enough to quote as an official statistic.
- Kuwait's sex ratio is heavily male-skewed (~61% male nationally) because
  of the expatriate labour force, and that skew is concentrated in working
  ages. The age-specific sex splits below reflect that rather than
  applying one flat 61/39 ratio to every age band.

Replace this whole table if/when real stratified data becomes available.

Usage (from backend/, venv active, DATABASE_URL set to Render Postgres):
    python -m scripts.create_population_strata
"""

from sqlalchemy import text
from app.db import engine

# Approximate 2025 official estimates per governorate.
REGION_TOTALS = {
    "Al Asimah": 620_000,
    "Hawalli": 1_050_000,
    "Farwaniya": 1_180_000,
    "Ahmadi": 1_150_000,
    "Jahra": 620_000,
    "Mubarak Al-Kabeer": 360_000,
}

# National age distribution (share of total population), matching the exact
# age buckets the dashboard groups by. Derived from published national age
# structure; normalised to sum to 1.0.
AGE_SHARES = {
    "0-4": 0.053,
    "5-14": 0.143,
    "15-24": 0.107,
    "25-44": 0.359,
    "45-64": 0.303,
    "65+": 0.035,
}

# Share of each age band that is male. Working ages skew heavily male due
# to the expatriate labour force; childhood and old age are near balanced.
MALE_SHARE_BY_AGE = {
    "0-4": 0.52,
    "5-14": 0.55,
    "15-24": 0.55,
    "25-44": 0.70,
    "45-64": 0.68,
    "65+": 0.45,
}

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS population_strata (
    region VARCHAR NOT NULL,
    age_group VARCHAR NOT NULL,
    sex VARCHAR NOT NULL,
    population INTEGER NOT NULL,
    PRIMARY KEY (region, age_group, sex)
);
"""

UPSERT_SQL = """
INSERT INTO population_strata (region, age_group, sex, population)
VALUES (:region, :age_group, :sex, :population)
ON CONFLICT (region, age_group, sex)
DO UPDATE SET population = EXCLUDED.population;
"""


def build_rows():
    rows = []
    for region, region_total in REGION_TOTALS.items():
        for age_group, age_share in AGE_SHARES.items():
            band_total = region_total * age_share
            male_share = MALE_SHARE_BY_AGE[age_group]
            rows.append({
                "region": region,
                "age_group": age_group,
                "sex": "male",
                "population": round(band_total * male_share),
            })
            rows.append({
                "region": region,
                "age_group": age_group,
                "sex": "female",
                "population": round(band_total * (1 - male_share)),
            })
    return rows


def main():
    rows = build_rows()
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))
        for row in rows:
            conn.execute(text(UPSERT_SQL), row)

    total = sum(r["population"] for r in rows)
    print(f"population_strata ready with {len(rows)} rows.")
    print(f"Total population represented: {total:,}")


if __name__ == "__main__":
    main()
