# Current Status — read this first in any new chat

Last updated: 2026-07-29

## Where we are right now

Notifiable Disease AND Immunization are both end-to-end complete, each
with a measured 100% field-accuracy figure on their own full 500-report
run, PLUS a working document-upload pipeline with automatic report-type
detection, a batch/cohort system, data export, and a fully redesigned
frontend (landing page, both dashboards, brand identity). Same
extraction pipeline shape for both report types: raw text -> GLiNER NER
+ gazetteer(s) + rule-based fields -> confidence report -> save to
Postgres.

**Document upload + auto-detection (2026-07-29).** The "Upload a
document" button is no longer a placeholder — `POST
/reports/parse-document` extracts text from DOCX/TXT (python-docx;
PDF/CSV still not built), and `POST /reports/detect-type` guesses which
report type it is by reusing the SAME gazetteers extraction already
relies on (disease vs vaccine vocabulary + a few structural keywords) —
no separate model. Tested 100% correct on all 1000 real synthetic
reports (500 disease + 500 immunization). The frontend shows the
detected type, auto-selects the matching report-type card, and displays
the extracted text for review before Extract runs — a suggestion the
reviewer confirms, never a silent decision. `services/document_parsing.py`
walks the DOCX body in TRUE reading order (paragraphs and tables
interleaved as they actually appear) — an earlier version grouped all
paragraphs before all tables, which misplaced a footer behind the field
table it followed.

**Batch/cohort system (2026-07-29).** At save time, a reviewer picks
"Original data" or a new/existing named batch (e.g. "Farwaniya Q1 2026
outbreak"). Both dashboards gained a Batch filter. Non-destructive: a
new `batch_label` column (nullable) was added to both tables via a
manual `ALTER TABLE` (NOT a full reset — `create_all()` doesn't add
columns to existing tables, same lesson as the icd10_code incident) —
existing 500+500 rows keep `batch_label = NULL`, meaning "original bulk
data," the default dashboard view.

**Export (2026-07-29).** Both dashboards have Export JSON / Export CSV
buttons, respecting the active batch filter. This exists because batches
have no separate backup — they live in the same tables as everything
else. If Render resets the database again, the synthetic 500+500 are
regenerable from the same seed, but anything saved by hand (real
uploads, manual corrections) is not, unless it was exported first.
Upgrading the Render instance to a paid tier would remove the
recurring-reset risk entirely; not yet decided.

**Frontend fully redesigned (2026-07-29).** Brand identity: wordmark
"Med" (light) + "Nexus" (bold green) in the Fraunces display face,
slogan "Every report, counted.", and a custom logo mark (loose incoming
report cards resolving into one structured record, no container tile).
Attribution lives in the footer only: "Built by Dr. Sameh Momen", then a
disclosure that MedNexus is built over open-source biomedical models
"developed with an AI engineering collaborator" (no vendor name), and
that extraction logic, schemas, and clinical decisions are
human-designed and human-reviewed. Landing page (`index.html`) gained a
hero illustration (original SVG, not stock photography — copyright-safe
and on-brand), a "How it works" section, and a "Report types" section
showing Notifiable Disease/Immunization as Live and Laboratory/
Syndromic/Outbreak as Coming next. Both dashboards got a shared visual
refresh: extended accent palette (slate/amber/rust/rose) so each chart
has its own identity instead of defaulting to green everywhere, soft
card shadows instead of flat borders, a real one-line description per
chart (not just a repeated unit label), and a thin animated "pulse line"
as the one deliberate signature flourish.

**Immunization got its own dashboard (2026-07-29).**
`frontend/prototype/immunization-dashboard.html` +
`GET /reports/immunization/dashboard-data` — doses by vaccine/region/
time, an age-BAND breakdown specific to immunization (birth-2mo, 3-6mo,
7-18mo, then 2-3y/3-9y/10-15y/16-18y, since nearly the whole schedule
happens before age 2 and the disease dashboard's 0-4/5-14/... buckets
would be nearly useless here), and adverse-events-by-severity.

**3 realistic Kuwait MOH-letterhead DOCX demo files exist**
(`Notifiable_Disease_Report_Meningococcal`, `Immunization_Record_Tdap_AEFI`,
`Immunization_Record_HepB_Newborn`) — built with docx-js, verified 100%
correct extraction on every field before delivery, for demoing the full
upload -> detect -> extract -> save-to-batch flow to decision-makers
with documents that look like real official forms, not plain text.

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
months) is naturally stated in months, not years. **Result on the real
GLiNER pipeline: 100% on all 11 attempted fields, 500/500, 0% flagged
for review** — first run measured facility_name at 99.0% (GLiNER's
"facility" label was swallowing a trailing ", <region>" on
comma-separated lines), fixed with a post-extraction cleanup
(`_strip_trailing_region`) and confirmed back to 100% on re-run.
vaccine_code and lot_number aren't attempted yet.

**Extraction accuracy is confirmed 100% on all NINE Notifiable Disease
fields across the FULL 500-report run** (real GLiNER pipeline, exact
match against ground truth), including onset_date and patient_sex. See
2026-07-27's decisions-log entries for the disease gazetteer and the
sentence-boundary negation-checking bug.

**The Render Postgres database reset once already (2026-07-28)** —
cause not fully confirmed (the project's active history didn't obviously
span the 30-day free-tier window that was the initial hypothesis).
Recovery steps documented in the ground rules below; the same steps
apply regardless of root cause if it recurs — and now there's an Export
button to reduce what a repeat would cost.

120 backend tests passing.

**IMMEDIATE NEXT STEP:** None fixed — the four originally-planned steps
(app.js routing, Immunization dashboard, visual redesign, landing page)
plus the upload/detection/batch/export/DOCX work triggered by testing
are ALL done as of today. Open questions, rough priority order:
1. Lower-priority fields still not extracted: Notifiable Disease's
   occupation/travel_related/travel_country/vaccination_status/outcome,
   and Immunization's vaccine_code/lot_number.
2. More report types (Laboratory, Syndromic, Outbreak — schemas exist,
   no extraction logic), or terminology normalization (ICD-10 / LOINC).
3. PDF/CSV document upload (currently DOCX/TXT only).
4. Point the frontend at the deployed Render URL instead of
   `http://127.0.0.1:8001` (still hardcoded in `app.js` and both
   dashboards).

## What's already working (locally)

- Full extraction pipeline for **Notifiable Disease** report type: raw
  text → GLiNER-based NER + rule-based fields + gazetteers → confidence
  report → editable review UI → save to Postgres.
- Full extraction pipeline for **Immunization** report type: raw text →
  GLiNER NER + vaccine/region gazetteers + rule-based fields (dose
  number, route, adverse event, patient_age_months) → confidence report
  → save to Postgres, plus its own dashboard.
- **Document upload**: DOCX/TXT parsing (`services/document_parsing.py`)
  + automatic report-type detection (`services/report_type_detection.py`,
  100% correct on all 1000 real synthetic reports) — the frontend
  dropzone is fully wired, not a placeholder.
- **Batch/cohort system**: save-time batch selection, per-dashboard batch
  filter, non-destructive (existing data untouched, `batch_label` is
  nullable).
- **Export**: JSON/CSV download per batch (or everything) on both
  dashboards — the safety net for manually-saved records with no other
  backup.
- 120 backend tests passing (`pytest tests/ -v` from `backend/`).
- Negation-aware extraction in BOTH directions ("ruled out dengue" and
  "dengue was ruled out"), bounded to the sentence so a negation can't leak
  onto a neighbouring diagnosis — applies to both NER entities and
  gazetteer matches. Immunization's vaccine_name doesn't need this.
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
- Fully redesigned frontend at `frontend/prototype/` — brand identity
  (MedNexus wordmark, logo mark, slogan), landing page with a hero
  illustration/how-it-works/report-types sections, both dashboards
  visually refreshed with a shared design language. Distinct from the
  sibling de-identification tool (shares only the base green palette).
- Custom dashboards at `frontend/prototype/dashboard.html` (Notifiable
  Disease) and `immunization-dashboard.html` — combined filters
  including Batch, Chart.js charts, count/rate toggle, Export buttons.

## What's not built yet

- Laboratory, Syndromic, Outbreak report types (schemas exist in
  `backend/app/schemas/`, no extraction logic yet — reuse
  `entity_selection.py` and `confidence.py`, don't reimplement them).
- Terminology normalization (ICD-10, LOINC, vaccine codes) — includes
  Immunization's vaccine_code and lot_number fields, not attempted.
- PDF and CSV document upload — only DOCX and TXT are parsed today.
- Frontend is not yet pointed at the deployed Render URL — still hardcoded
  to `http://127.0.0.1:8001` in `app.js` and both dashboard pages.
- Lower-priority extraction fields: Notifiable Disease's
  occupation/travel_related/travel_country/vaccination_status/outcome,
  Immunization's vaccine_code/lot_number.
- A separate backup store for batches — right now Export (JSON/CSV) is
  the only safety net; nothing automatic yet.
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
