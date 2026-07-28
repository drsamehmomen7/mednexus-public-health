# Current Status — read this first in any new chat

Last updated: 2026-07-28

## Where we are right now

Notifiable Disease is end-to-end complete, with a custom dashboard and a
measured accuracy figure. Pipeline: raw text -> GLiNER NER + gazetteer +
rule-based fields -> confidence report -> editable review UI -> Render
Postgres -> dashboard.

**Extraction accuracy is confirmed 100% on all NINE extracted fields
across the FULL 500-report run** (real GLiNER pipeline, exact match
against ground truth), including onset_date and patient_sex — not just a
20-report sample. disease_name had actually dropped to 84.8% at
500-report scale before the 2026-07-27 fix (the 100% figure from the
20-report sample didn't hold up); see that day's decisions-log entries
for the two bugs that caused it and how they were fixed (a disease
gazetteer, plus a sentence-boundary bug in negation-checking).

**onset_date is now extracted too** (2026-07-28) — two different
phrasings depending on report style: prose states it directly ("Onset
2025-03-04", "Symptoms began on..."), while clinical shorthand states a
DURATION instead ("c/o cough x12d") and onset is computed as report_date
minus that many days. 100% on all 500 reports. This was the last of the
"core patient/timing" fields — remaining gaps (occupation, travel_*,
vaccination_status, outcome) are lower-priority contextual fields, not
needed for the epidemic-curve/demographic charts already on the
dashboard.

**The Render Postgres database reset (2026-07-28)** — cause not fully
confirmed. Free-tier Render Postgres databases are hard-deleted 30 days
after creation + a 14-day grace period, no backups; that was the initial
hypothesis, but the project's active history doesn't obviously span that
long, so it may have been something else (a manual reset, a
misconfigured connection string, etc.) — left as an open question rather
than a settled cause. What IS confirmed: `population_strata` was missing
entirely, and `notifiable_disease_records` existed but with a STALE
schema (missing `icd10_code` and other newer columns), because
`Base.metadata.create_all()` only creates tables that don't exist yet —
it never alters an existing table to match a changed model. Recovery:
drop the stale table, let `init_db()` recreate it from the current
`db_models.py`, re-run `create_population_strata` and
`load_synthetic_reports`. All fields confirmed back to 100% afterward. If
it recurs, the same recovery steps apply regardless of root cause — see
the ground rules section below.

**patient_sex is now extracted too** (2026-07-27, rule-based, same
approach as patient_age) — 100% on all 500 reports. The dashboard's
"Cases by sex" chart is confirmed visually showing a real male/female
split now, instead of 100% "unknown" (which was expected before that
day: the field simply wasn't populated by extraction yet — earlier
Metabase-era test data had `patient_sex` hand-typed directly into a seed
script, bypassing extraction entirely, which is why it looked like it
worked before).

**Dashboard is a custom page in our own frontend, not Metabase.**
`frontend/prototype/dashboard.html` (Chart.js, reuses `style.css`), fed by
`GET /reports/notifiable-disease/dashboard-data`. Four controls combining
with AND: disease, year, region, measure (count vs rate per 100,000). Five
charts plus four summary metrics. Metabase was tried and dropped — see the
2026-07-27 decisions-log entry.

**IMMEDIATE NEXT STEP — this is the one thing to do first:**
Dashboard visual polish (colors, animations/transitions) — purely
cosmetic, no functional changes planned. After that, open questions in
rough priority order:
1. Four lower-priority fields still not extracted: occupation,
   travel_related, travel_country, vaccination_status, outcome. The
   loader prints this gap list every run.
2. More report types — Immunization next (the Kuwait MOH 2025 childhood
   immunization schedule PDF is on hand as the real vaccine-name source,
   the same role notifiable_diseases.json plays for disease names),
   reusing entity_selection.py / confidence.py / gazetteer.py. Or
   terminology normalization (ICD-10 / LOINC).

Docx file upload is **descoped entirely**, not deferred — the workflow is
free-text only, no file upload, no live hospital system integration.

## What's already working (locally)

- Full extraction pipeline for **Notifiable Disease** report type: raw
  text → GLiNER-based NER + rule-based fields + gazetteers → confidence
  report → editable review UI → save to Postgres.
- 84 backend tests passing (`pytest tests/ -v` from `backend/`).
- Negation-aware extraction in BOTH directions ("ruled out dengue" and
  "dengue was ruled out"), bounded to the sentence so a negation can't leak
  onto a neighbouring diagnosis — applies to both NER entities and
  gazetteer matches.
- Closed-vocabulary matching for BOTH region and disease name via
  data-driven gazetteers — regions come from population_strata, diseases
  from `backend/data/notifiable_diseases.json` (seeded from the synthetic
  ground truth via `scripts/build_disease_vocabulary.py`, a placeholder
  until a real deployment supplies its own reportable-disease list).
  Neither is hardcoded in extraction.
- Rule-based patient_age, patient_sex, AND onset_date extraction
  (`rule_based.py`) — 100% on all 500 reports, no model or gazetteer
  needed for any of the three.
- 500 synthetic free-text reports + ground_truth.json in
  `backend/data/synthetic_reports/` (regenerate with
  `python scripts/generate_synthetic_reports.py --count 500`).
- Frontend prototype (static HTML/CSS/JS) at `frontend/prototype/`,
  green-themed, distinct from the sibling de-identification tool.
- Custom dashboard at `frontend/prototype/dashboard.html` — four combined
  filters, five Chart.js charts, count/rate toggle, confirmed visually
  showing correct disease/region/time/age/sex breakdowns.

## What's not built yet

- Immunization, Laboratory, Syndromic, Outbreak report types (schemas
  exist in `backend/app/schemas/`, no extraction logic yet — reuse
  `entity_selection.py` and `confidence.py`, don't reimplement them).
- Terminology normalization (ICD-10, LOINC, vaccine codes).
- File upload of any kind — deliberately out of scope; workflow is
  free-text only (see Where we are right now).
- Frontend is not yet pointed at the deployed Render URL — still hardcoded
  to `http://127.0.0.1:8001` in both `app.js` and `dashboard.html`.
- Four lower-priority fields present in report text that extraction
  doesn't attempt yet (occupation, travel_related, travel_country,
  vaccination_status, outcome) — disease_name, region, patient_age,
  patient_sex, onset_date, report_date, diagnosis_status, and
  lab_confirmed are all done and at 100%.
- Dashboard visual polish (colors, animations/transitions) — next planned
  step, purely cosmetic.
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
- `init_db()` (`Base.metadata.create_all()`) only creates MISSING tables —
  it never alters an existing table when the model changes. Any time the
  Render database gets reset (free-tier 30-day expiry — see "Where we are
  right now") and a schema mismatch error appears (a column "does not
  exist"), drop the affected table and let `init_db()` recreate it, rather
  than assuming the model code is wrong. Switch to Alembic migrations once
  real (non-synthetic) data exists and dropping tables is no longer safe.

## How to resume in a new chat

Paste this file, or just say "continue the MedNexus public health project"
and share the GitHub repo: https://github.com/drsamehmomen7/mednexus-public-health
