# MedNexus Public Health — Architecture (Living Document)

Status: Extraction pipeline working (Notifiable Disease type) — closing the loop to a dashboard next
Last updated: 2026-07-26

## 1. Purpose

A platform-independent module that ingests public health reports (notifiable
disease case reports, immunization records, laboratory reports, syndromic
surveillance, outbreak reports), extracts structured fields, and prepares
data for statistics and indicators.

This is a separate project from the MedNexus de-identification tool, but
shares its visual identity and long-term engine-agnostic principles.

## 2. Short-Term Roadmap (agreed 2026-07-26)

This is the current execution plan, in order. Do not skip ahead to the
dashboard before the data store and API exist — there is nothing for a
dashboard to visualize without them.

1. **Data store**: PostgreSQL (not SQLite — Metabase and Render both work
   with it more directly), plus a save endpoint that persists a record
   after human review confirms it.
2. **Deployment plumbing**: connect GitHub to Render, deploy the backend
   there as a trial, using synthetic data only — never real patient data
   during this trial phase.
3. **Dashboard via Metabase** (not Superset, not built from scratch): open
   source, self-hostable, no license cost, single-container deploy — far
   less operational complexity than Superset (which needs several
   interdependent services) for the value this stage needs. Connect it to
   the Postgres store and build the first 3-4 indicators: case counts by
   disease, by region, and the percentage of records that needed manual
   review (a data-quality indicator unique to this pipeline).

Key architectural point behind this plan: the extraction/review tool runs
locally per clinician machine (patient-level data, high sensitivity), but
the dashboard is a different kind of consumer — a decision-maker needs
aggregated data from many facilities in one place, so it belongs on one
central server, not replicated per device. Only reviewed, aggregated data
should ever reach that central server/Render during the trial.

## 3. Current Phase: Static UI Prototype

No backend yet. The frontend prototype (`frontend/prototype/`) is a static
HTML/CSS/JS page used to validate the interaction flow before any extraction
logic is written.

Flow: select report type → provide input (paste/upload) → request extraction
→ view structured result.

## 4. Report Types (initial set)

| Type | Description |
|---|---|
| Notifiable Disease | Individual case reports for mandatory-reporting infectious diseases |
| Immunization | Vaccination records: dose, lot, date, coverage |
| Laboratory | Test results feeding surveillance/case confirmation |
| Syndromic | Symptom-based reports for early outbreak detection |
| Outbreak / Cluster | Group-level reports for a detected outbreak event |

Full field definitions per type live in `docs/report-types.md` (to be
populated as extraction schemas are designed).

## 5. Planned Pipeline

1. Report ingestion (file/text input, later batch + API)
2. Structured extraction (rules + AI hybrid, per report type) — done for
   Notifiable Disease, including confidence reporting and negation-aware
   selection
3. Terminology normalization (ICD-10, LOINC, vaccine codes) — not started
4. Persistence + statistics and indicators — in progress (see roadmap above)
5. Forecasting (deferred until stages 1-4 are validated)

## 6. Open Decisions

Tracked in `docs/decisions-log.md`. Add an entry any time a structural
choice is made — do not let decisions live only in chat history.
