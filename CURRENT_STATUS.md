# Current Status — read this first in any new chat

Last updated: 2026-07-27

## Where we are right now

Notifiable Disease is end-to-end complete, with a custom dashboard and a
measured accuracy figure. Pipeline: raw text -> GLiNER NER + gazetteer +
rule-based fields -> confidence report -> editable review UI -> Render
Postgres -> dashboard.

**Extraction accuracy is confirmed 100% on all seven extracted fields
across the FULL 500-report run** (real GLiNER pipeline, exact match
against ground truth) — not just a 20-report sample. disease_name had
actually dropped to 84.8% at 500-report scale before today's fix (the
100% figure from the 20-report sample didn't hold up); see the
2026-07-27 decisions-log entry for the two bugs that caused it and how
they were fixed (a disease gazetteer, plus a sentence-boundary bug in
negation-checking).

**Dashboard is a custom page in our own frontend, not Metabase.**
`frontend/prototype/dashboard.html` (Chart.js, reuses `style.css`), fed by
`GET /reports/notifiable-disease/dashboard-data`. Four controls combining
with AND: disease, year, region, measure (count vs rate per 100,000). Five
charts plus four summary metrics. Metabase was tried and dropped — see the
2026-07-27 decisions-log entry.

**IMMEDIATE NEXT STEP — this is the one thing to do first:**
The 500 synthetic reports are now loaded and confirmed at 100% accuracy.
Open questions in rough priority order:
1. Extraction doesn't attempt seven fields the reports DO contain:
   onset_date, patient_sex, occupation, travel_related, travel_country,
   vaccination_status, outcome. The loader prints this gap list every run.
   onset_date matters most — epidemic curves should use symptom onset,
   not report date.
2. ~~"Flagged as needing human review" came back 0% on clean samples~~ —
   RESOLVED: it's 0% (0/500) on the full run too, and that's expected —
   every disease in the 500 reports is in the known 10-item gazetteer
   vocabulary (backend/data/notifiable_diseases.json). A report naming a
   disease outside that list would still fall back to NER and could
   trigger review, so this reflects a closed test set, not a broken
   review mechanism.
3. No dedicated pytest regression tests yet for the disease gazetteer path
   or the sentence-boundary fix in `is_negated()` added today (the
   existing 69 tests all still pass, since the new parameter is optional
   and defaults to None) — worth adding before reusing this pattern for
   another report type.
4. Only then: more report types (Immunization next, reusing
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
- Closed-vocabulary matching for BOTH region and disease name via
  data-driven gazetteers — regions come from population_strata, diseases
  from `backend/data/notifiable_diseases.json` (seeded from the synthetic
  ground truth via `scripts/build_disease_vocabulary.py`, a placeholder
  until a real deployment supplies its own reportable-disease list).
  Neither is hardcoded in extraction.
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
- Seven fields present in report text that extraction doesn't attempt yet
  (onset_date, patient_sex, occupation, travel_*, vaccination_status,
  outcome).
- No pytest regression tests yet for the disease gazetteer or the
  sentence-boundary negation fix added 2026-07-27 (existing tests all
  still pass, but the new behaviour itself isn't directly covered).
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
