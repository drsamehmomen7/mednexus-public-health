# Current Status — read this first in any new chat

Last updated: 2026-07-27

## Where we are right now

The Notifiable Disease report type is end-to-end complete and has its own
custom dashboard. Pipeline: raw text -> GLiNER NER + rule-based fields ->
confidence report -> editable review UI -> save to Render Postgres ->
appears immediately on the dashboard.

**The dashboard is now a custom page in our own frontend, not Metabase.**
`frontend/prototype/dashboard.html` (Chart.js, reuses `style.css` so it
matches the product's green identity), fed by
`GET /reports/notifiable-disease/dashboard-data`. Four controls that all
combine with AND: disease, year, region, and measure (case count vs rate
per 100,000). Five charts: by disease, by region, over time, by age
group, by sex — plus four summary metrics. Measure applies to every
breakdown, which is why population is stored stratified by region x age
group x sex in `population_strata`.

Metabase was used for two days and then dropped — see the 2026-07-27
entry in decisions-log.md for the full reasoning. Short version: it can't
be styled to match the product, which matters because this dashboard is
meant to be shown to decision-makers, not just used internally. All the
indicator SQL carried over unchanged; only the rendering layer was
replaced. Metabase can still be run locally if wanted (`C:\metabase\
metabase.jar`, Java 21+, not in this repo) but is no longer part of the
workflow.

Docx file upload was **descoped entirely**, not deferred: the workflow is
free-text only (a clinician types or pastes a report, extracts, saves),
with no file upload and no live hospital system integration.

**Open question for the next session**: is the Notifiable Disease domain
now mature enough to show a decision-maker — which would justify moving
on to more report types (Immunization next) — or is more depth needed
first? Ask rather than assuming. One known gap either way: only 8 records
exist, which is too few to demonstrate anything convincingly.

## What's already working (locally)

- Full extraction pipeline for **Notifiable Disease** report type: raw
  text → GLiNER-based NER + rule-based fields → confidence report →
  editable review UI → save to Postgres.
- 41 backend tests passing (`pytest tests/ -v` from `backend/`).
- Negation-aware extraction (won't pick a "ruled out" diagnosis) and
  needed_review flagging (low-confidence fields flagged for a human).
- Frontend prototype (static HTML/CSS/JS) at `frontend/prototype/`,
  green-themed, distinct from the sibling de-identification tool.
- Custom dashboard at `frontend/prototype/dashboard.html` — four combined
  filters, five Chart.js charts, count/rate toggle.

## What's not built yet

- Immunization, Laboratory, Syndromic, Outbreak report types (schemas
  exist in `backend/app/schemas/`, no extraction logic yet — reuse
  `entity_selection.py` and `confidence.py`, don't reimplement them).
- Terminology normalization (ICD-10, LOINC, vaccine codes).
- File upload of any kind — deliberately out of scope; workflow is
  free-text only (see Where we are right now).
- Frontend is not yet pointed at the deployed Render URL — still hardcoded
  to `http://127.0.0.1:8001` in both `app.js` and `dashboard.html`.
- Only 8 records in the database — enough to prove the pipeline, too few
  to demonstrate epidemiological patterns to anyone.
- Dashboard refresh takes 3-4s: ~12 separate queries against Render's
  free-tier Postgres in Oregon. Latency, not a code problem.

## Local dev routine (two terminals, every session)

See `README.md`. Terminal 1 (backend, port 8001) needs `$env:DATABASE_URL`
set to the Render external connection string before starting uvicorn, so
saves and dashboard queries hit the same database — otherwise it falls
back to a local Postgres URL that isn't set up. Terminal 2: frontend
static server, port 5500 (serves both `index.html` and `dashboard.html`).
Never open the HTML files as a `file://` path (CORS/private-network
blocking). Metabase (Terminal 3) is no longer part of the routine.

## Key ground rules established (see docs/decisions-log.md for full reasoning)

- Core schemas stay system-agnostic — no country/ministry-specific logic
  in extraction or normalization. Ministry integrations (DHIS2, etc.) are
  optional adapters layered on top, never a dependency.
- Never put real patient data on Render or any shared/cloud service —
  synthetic data only until access control is properly designed.
- `backend/models/` (GLiNER weights) and `venv/` are gitignored —
  reproducible via `scripts/download_gliner_model.py`, not committed.
- Commit after every complete, tested change — not at end of day. See
  decisions-log.md's most recent entries for exactly what's changed and why.

## How to resume in a new chat

Paste this file, or just say "continue the MedNexus public health project"
and share the GitHub repo: https://github.com/drsamehmomen7/mednexus-public-health
