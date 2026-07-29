# Current Status — read this first in any new chat

Last updated: 2026-07-28

## Where we are right now

Notifiable Disease AND Immunization are both end-to-end complete, each
with a measured 100% field-accuracy figure on their own full 500-report
run. Same pipeline shape for both: raw text -> GLiNER NER + gazetteer(s)
+ rule-based fields -> confidence report -> save to Postgres. Notifiable
Disease also has a custom dashboard; Immunization doesn't yet (see
immediate next step).

**Immunization report type completed 2026-07-28.** vaccine_name and
region via gazetteers (vaccine_name doesn't need negation-awareness,
unlike disease_name — a vaccine given isn't the kind of thing that gets
"ruled out"); dose_number, route, adverse_event_reported/severity/
description, and patient_age_months all rule-based. The vaccine
vocabulary (`backend/data/vaccines.json`, 12 vaccines) is a REAL source —
transcribed from the Kuwait MOH 2025 Childhood Immunization Schedule PDF
— not a synthetic placeholder the way the disease gazetteer is. Two
schema decisions made along the way: `InjectionRoute` gained
`INTRADERMAL` (BCG genuinely uses it, the enum didn't have it), and
`ImmunizationRecord` gained `patient_age_months` (0-24, optional)
alongside `patient_age`, because most of the schedule (birth through 18
months) is naturally stated in months, not years. New endpoints:
`POST /reports/immunization/extract` and `/save`, plus
`scripts/load_immunization_reports.py`. **Result on the real GLiNER
pipeline: 100% on all 11 attempted fields, 500/500, 0% flagged for
review** — first run measured facility_name at 99.0% (GLiNER's
"facility" label was swallowing a trailing ", <region>" on
comma-separated lines), fixed with a post-extraction cleanup
(`_strip_trailing_region` in `immunization_extraction.py`) and confirmed
back to 100% on re-run. vaccine_code and lot_number aren't attempted yet.
107 tests passing.

**Extraction accuracy is confirmed 100% on all NINE Notifiable Disease
fields across the FULL 500-report run** (real GLiNER pipeline, exact
match against ground truth), including onset_date and patient_sex — not
just a 20-report sample. disease_name had actually dropped to 84.8% at
500-report scale before the 2026-07-27 fix (the 100% figure from the
20-report sample didn't hold up); see that day's decisions-log entries
for the two bugs that caused it and how they were fixed (a disease
gazetteer, plus a sentence-boundary bug in negation-checking).

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

**Dashboard is a custom page in our own frontend, not Metabase.**
`frontend/prototype/dashboard.html` (Chart.js, reuses `style.css`), fed by
`GET /reports/notifiable-disease/dashboard-data`. Four controls combining
with AND: disease, year, region, measure (count vs rate per 100,000). Five
charts plus four summary metrics. Metabase was tried and dropped — see the
2026-07-27 decisions-log entry. **Immunization has no dashboard yet** —
the save endpoint and table exist, but nothing reads from them visually.

**IMMEDIATE NEXT STEP — this is the one thing to do first:**
Two things planned together, purely cosmetic/presentation — no new
extraction logic:
1. **Dashboard visual polish** — colors, animations/transitions on the
   existing Notifiable Disease dashboard.
2. **Landing page** (the project's overall entry page) needs more
   creativity/visual impact and more explanation of what the project
   does — flagged as needing "ابهار" (more impressive/polished) and more
   detail, not just a functional page.

After that, open questions in rough priority order:
1. Lower-priority fields still not extracted: Notifiable Disease's
   occupation/travel_related/travel_country/vaccination_status/outcome,
   and Immunization's vaccine_code/lot_number.
2. An Immunization dashboard (mirroring the Notifiable Disease one) —
   not started.
3. More report types (Laboratory, Syndromic, Outbreak — schemas exist,
   no extraction logic), or terminology normalization (ICD-10 / LOINC).

Docx file upload is **descoped entirely**, not deferred — the workflow is
free-text only, no file upload, no live hospital system integration.

## What's already working (locally)

- Full extraction pipeline for **Notifiable Disease** report type: raw
  text → GLiNER-based NER + rule-based fields + gazetteers → confidence
  report → editable review UI → save to Postgres.
- Full extraction pipeline for **Immunization** report type: raw text →
  GLiNER NER + vaccine/region gazetteers + rule-based fields (dose
  number, route, adverse event, patient_age_months) → confidence report
  → save to Postgres. No review UI or dashboard yet, just the API.
- 107 backend tests passing (`pytest tests/ -v` from `backend/`).
- Negation-aware extraction in BOTH directions ("ruled out dengue" and
  "dengue was ruled out"), bounded to the sentence so a negation can't leak
  onto a neighbouring diagnosis — applies to both NER entities and
  gazetteer matches. Immunization's vaccine_name doesn't need this (see
  "Where we are right now").
- Closed-vocabulary matching via data-driven gazetteers for region,
  disease name, AND vaccine name — regions come from population_strata,
  diseases from `backend/data/notifiable_diseases.json` (synthetic
  placeholder), vaccines from `backend/data/vaccines.json` (real, from
  the Kuwait MOH schedule). None hardcoded in extraction.
- Rule-based patient_age, patient_sex, onset_date (Notifiable Disease),
  and patient_age_months, dose_number, route, adverse_event_* fields
  (Immunization) — all in `rule_based.py`, all 100% on their full
  500-report runs, no model needed for any of them.
- 500 synthetic free-text reports + ground_truth.json for EACH report
  type: `backend/data/synthetic_reports/` (Notifiable Disease, regenerate
  with `python -m scripts.generate_synthetic_reports --count 500`) and
  `backend/data/immunization_reports/` (Immunization, regenerate with
  `python -m scripts.generate_immunization_reports --count 500`).
- Frontend prototype (static HTML/CSS/JS) at `frontend/prototype/`,
  green-themed, distinct from the sibling de-identification tool.
- Custom dashboard at `frontend/prototype/dashboard.html` — four combined
  filters, five Chart.js charts, count/rate toggle, confirmed visually
  showing correct disease/region/time/age/sex breakdowns. **Notifiable
  Disease only** — Immunization has no dashboard yet.

## What's not built yet

- Laboratory, Syndromic, Outbreak report types (schemas exist in
  `backend/app/schemas/`, no extraction logic yet — reuse
  `entity_selection.py` and `confidence.py`, don't reimplement them).
  Immunization is DONE as of 2026-07-28 (see above).
- Terminology normalization (ICD-10, LOINC, vaccine codes) — includes
  Immunization's vaccine_code and lot_number fields, not attempted.
- File upload of any kind — deliberately out of scope; workflow is
  free-text only (see Where we are right now).
- Frontend is not yet pointed at the deployed Render URL — still hardcoded
  to `http://127.0.0.1:8001` in both `app.js` and `dashboard.html`.
- Lower-priority fields present in report text that extraction doesn't
  attempt yet: Notifiable Disease's occupation/travel_related/
  travel_country/vaccination_status/outcome, Immunization's
  vaccine_code/lot_number.
- An Immunization dashboard and review UI — the extract/save API exists,
  nothing visual reads from it yet.
- Dashboard visual polish (colors, animations/transitions) AND the
  project's landing page needing more creativity/explanation — both next
  planned, purely cosmetic/presentation.
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
