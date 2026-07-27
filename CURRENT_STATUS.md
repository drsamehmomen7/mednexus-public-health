# Current Status — read this first in any new chat

Last updated: 2026-07-27

## Where we are right now

Notifiable Disease is end-to-end complete, with a custom dashboard and a
measured accuracy figure. Pipeline: raw text -> GLiNER NER + gazetteer +
rule-based fields -> confidence report -> editable review UI -> Render
Postgres -> dashboard.

**Extraction accuracy is 100% on all seven extracted fields** (20-report
sample, exact match against known ground truth). It was disease_name 80%,
region 85%, diagnosis_status 80% before the fixes described in the
2026-07-27 decisions-log entries.

**Dashboard is a custom page in our own frontend, not Metabase.**
`frontend/prototype/dashboard.html` (Chart.js, reuses `style.css`), fed by
`GET /reports/notifiable-disease/dashboard-data`. Four controls combining
with AND: disease, year, region, measure (count vs rate per 100,000). Five
charts plus four summary metrics. Metabase was tried and dropped — see the
2026-07-27 decisions-log entry.

**IMMEDIATE NEXT STEP — this is the one thing to do first:**
500 synthetic reports have been generated but NOT yet loaded into the
database. The database still holds only the original 8 records. Run:

    cd C:\mednexus-public-health\backend
    python -m scripts.load_synthetic_reports

Takes roughly 20-30 minutes (GLiNER runs per report, plus a round trip to
Render per batch). It prints per-field accuracy at the end. Once it
finishes, open the dashboard — it should show the measles outbreak the
generator built into the data.

After that, open questions in rough priority order:
1. Extraction doesn't attempt seven fields the reports DO contain:
   onset_date, patient_sex, occupation, travel_related, travel_country,
   vaccination_status, outcome. The loader prints this gap list every run.
   onset_date matters most — epidemic curves should use symptom onset,
   not report date.
2. "Flagged as needing human review" came back 0% on clean samples. Either
   the model is genuinely confident or the threshold is too permissive.
   Check against the full 500 before trusting it.
3. Only then: more report types (Immunization next, reusing
   entity_selection.py / confidence.py / gazetteer.py), or terminology
   normalization (ICD-10 / LOINC).

Docx file upload is **descoped entirely**, not deferred — the workflow is
free-text only, no file upload, no live hospital system integration.

## What's already working (locally)

- Full extraction pipeline for **Notifiable Disease** report type: raw
  text → GLiNER-based NER + rule-based fields → confidence report →
  editable review UI → save to Postgres.
- 69 backend tests passing (`pytest tests/ -v` from `backend/`).
- Negation-aware extraction in BOTH directions ("ruled out dengue" and
  "dengue was ruled out"), bounded to the sentence so a negation can't leak
  onto a neighbouring diagnosis.
- Closed-vocabulary matching for region via a data-driven gazetteer —
  regions come from population_strata, never hardcoded in extraction.
- 500 synthetic free-text reports + ground_truth.json in
  `backend/data/synthetic_reports/` (regenerate with
  `python scripts/generate_synthetic_reports.py --count 500`).
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
- The 500 generated reports are NOT loaded into the database yet — it
  still holds 8 records. See "immediate next step" above.
- Seven fields present in report text that extraction doesn't attempt yet
  (onset_date, patient_sex, occupation, travel_*, vaccination_status,
  outcome).
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
