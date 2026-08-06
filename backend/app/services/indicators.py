"""
Indicators layer: computed/composite metrics that cross-reference more
than one report type, separate from each report type's own per-type
dashboard (dashboard.html, immunization-dashboard.html,
laboratory-dashboard.html).

Kept in its own service module (not stuffed into main.py) because these
are cross-cutting, decision-facing metrics — sometimes joining across
report-type tables (like the first indicator below), sometimes a
breakdown of a single report type that its own per-type dashboard
doesn't already surface (like the second) — a different shape of logic
from a single report type's own dashboard-data endpoint either way.

First indicator: vaccination coverage % by region.
    coverage % = doses administered in a region / that region's total
    population (population_strata), the SAME denominator table the
    Notifiable Disease and Immunization dashboards already use for
    rate-per-100k — see app/main.py's `population_by_region` pattern.

Deliberately grouped by region only (not also by age_group, even though
population_strata has an age_group column) — population_strata's age
bands (0-4/5-14/15-24/...) are the Notifiable Disease dashboard's adult
buckets, not Immunization's under-2-focused month bands, so splitting
this indicator by age_group would compare doses against the wrong-shaped
denominator. Region-level totals avoid that mismatch entirely.
"""

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def vaccination_coverage_by_region(
    db: Session, vaccine_name: Optional[str] = None
) -> list[dict]:
    """
    Returns one row per region: population, doses_administered, coverage_pct.

    vaccine_name=None (default) counts doses of ANY vaccine per region —
    a general "how much immunization activity relative to population"
    view. Passing a specific vaccine_name narrows to that vaccine only;
    not called anywhere yet, but kept as a parameter since a real
    coverage target (e.g. "% of the population that received Hepatitis B
    dose 1") is always vaccine-specific, and the next Indicators step
    will likely need it.
    """
    params: dict = {}
    vaccine_filter = ""
    if vaccine_name:
        vaccine_filter = "AND vaccine_name = :vaccine_name"
        params["vaccine_name"] = vaccine_name

    rows = db.execute(
        text(
            f"""
            SELECT
                pop.region,
                pop.population,
                COALESCE(doses.dose_count, 0) AS doses_administered,
                ROUND(
                    COALESCE(doses.dose_count, 0)::numeric
                    / NULLIF(pop.population, 0) * 100,
                    2
                ) AS coverage_pct
            FROM (
                SELECT region, SUM(population) AS population
                FROM population_strata
                GROUP BY region
            ) pop
            LEFT JOIN (
                SELECT region, COUNT(*) AS dose_count
                FROM immunization_records
                WHERE 1=1 {vaccine_filter}
                GROUP BY region
            ) doses ON doses.region = pop.region
            ORDER BY pop.region
            """
        ),
        params,
    ).mappings()

    return [dict(row) for row in rows]


def test_positivity_by_region(
    db: Session, test_name: Optional[str] = None
) -> list[dict]:
    """
    Returns one row per region: positive, negative, resolved (=
    positive + negative), positivity_pct.

    positivity_pct = 100 * positive / (positive + negative) — pending and
    indeterminate results are excluded from the denominator, same
    convention already used for the single-number pct_positive in
    app/main.py's laboratory_dashboard_data, so this indicator's numbers
    stay consistent with what the Laboratory dashboard already reports
    (just broken down by region here, which that dashboard doesn't do —
    its own region breakdown is a raw test COUNT, not a positivity rate).

    test_name=None (default) pools every test type together per region.
    Passing a specific test_name narrows to that test only — not called
    anywhere yet, but real positivity tracking (e.g. "% positive for PCR
    - Influenza A specifically") is usually test-specific, same reasoning
    as vaccine_name on vaccination_coverage_by_region above.
    """
    params: dict = {}
    test_filter = ""
    if test_name:
        test_filter = "AND test_name = :test_name"
        params["test_name"] = test_name

    rows = db.execute(
        text(
            f"""
            SELECT
                region,
                SUM(CASE WHEN result = 'positive' THEN 1 ELSE 0 END) AS positive,
                SUM(CASE WHEN result = 'negative' THEN 1 ELSE 0 END) AS negative,
                SUM(CASE WHEN result IN ('positive', 'negative') THEN 1 ELSE 0 END) AS resolved,
                ROUND(
                    100.0 * SUM(CASE WHEN result = 'positive' THEN 1 ELSE 0 END)
                        / NULLIF(SUM(CASE WHEN result IN ('positive', 'negative') THEN 1 ELSE 0 END), 0),
                    2
                ) AS positivity_pct
            FROM laboratory_records
            WHERE 1=1 {test_filter}
            GROUP BY region
            ORDER BY region
            """
        ),
        params,
    ).mappings()

    return [dict(row) for row in rows]
