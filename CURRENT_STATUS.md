# Current Status — read this first in any new chat

Last updated: 2026-07-27

## Where we are right now

Notifiable Disease is end-to-end complete, with a custom dashboard and a
measured accuracy figure. Pipeline: raw text -> GLiNER NER + gazetteer +
rule-based fields -> confidence report -> editable review UI -> Render
Postgres -> dashboard.

**Extraction accuracy is confirmed 100% on all seven core extracted fields
across the FULL 500-report run** (real GLiNER pipeline, exact match
against ground truth) — not just a 20-report sample. disease_name had
actually dropped to 84.8% at 500-report scale before today's fix (the
100% figure from the 20-report sample didn't hold up); see the
2026-07-27 decisions-log entries for the two bugs that caused it and how
they were fixed (a disease gazetteer, plus a sentence-boundary bug in
negation-checking), and for the patient_sex field added the same day.

**patient_sex is now extracted too** (rule-based, same approach as
patient_age) — 100% on all 500 reports. The dashboard's "Cases by sex"
chart is confirmed visually showing a real male/female split now,
instead of 100% "unknown" (which was expected before today: the field
simply wasn't populated by extraction yet — earlier Metabase-era test
data had `patient_sex` hand-typed directly into a seed script, bypassing
extraction entirely, which is why it looked like it worked before).

**Dashboard is a custom page in our own frontend, not Metabase.**
`frontend/prototype/dashboard.html` (Chart.js, reuses `style.css`), fed by
`GET /reports/notifiable-disease/dashboard-data`. Four controls combining
with AND: disease, year, region, measure (count vs rate per 100,000). Five
charts plus four summary metrics. Metabase was tried and dropped — see the
2026-07-27 decisions-log entry.

**IMMEDIATE NEXT STEP — this is the one thing to do first:**
Two things planned for next session, together:
1. **onset_date extraction** (rule-based, like patient_age/patient_sex) —
   epidemic curves should use symptom onset, not report date.
2. **Dashboard visual polish** — colors and animation/transitions, purely
   cosmetic, no functional changes planned.

Other open questions, lower priority:
1. Extraction still doesn't attempt six fields the reports DO contain:
   onset_date, occupation, travel_related, travel_country,
   vaccination_status, outcome. The loader prints this gap list every run.
2. ~~"Flagged as needing human review" came back 0% on clean samples~~ —
   RESOLVED: it's 0% (0/500) on the full run too, and that's expected —
   every disease in the 500 reports is in the known 10-item gazetteer
   vocabulary (backend/data/notifiable_diseases.json). A report naming a
   disease outside that list would still fall back to NER and could
   trigger review, so this reflects a closed test set, not a broken
   review mechanism.
3. ~~No dedicated pytest regression tests for the disease gazetteer /
   negation fix~~ — RESOLVED: added the same day (4 tests), plus 5 more
   for patient_sex. 78 tests total, all passing.
4. Only then: more report types (Immunization next, reusing
   entity_selection.py / confidence.py / gazetteer.py), or terminology
   normalization (ICD-10 / LOINC).

Docx file upload is **descoped entirely**, not deferred — the workflow is
free-text only, no file upload, no live hospital system integration.

## What's already working (locally)

- Full extraction pipeline for **Notifiable Disease** report type: raw
  text → GLiNER-based NER + rule-based fields + gazetteers → confidence
  report → editable review UI → save to Postgres.
- 78 backend tests passing (`pytest tests/ -v` from `backend/`).
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
- Rule-based patient_age AND patient_sex extraction (`rule_based.py`) —
  100% on all 500 reports, no model or gazetteer needed for either.
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
- Six fields present in report text that extraction doesn't attempt yet
  (onset_date, occupation, travel_*, vaccination_status, outcome) —
  patient_sex was the seventh, added 2026-07-27.
- Dashboard visual polish (colors, animations/transitions) — planned for
  next session alongside onset_date, purely cosmetic.
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
