# Decisions Log

Each entry: date, decision, reasoning, alternatives considered.

---

### 2026-07-22 — New independent project, not an extension of the de-id tool
The public health module is a separate project (`mednexus-public-health/`)
rather than a folder inside the existing de-identification codebase.
Reasoning: different lifecycle, different report types, avoids coupling
two products that may evolve at different speeds. Visual identity is shared
intentionally for brand consistency.

### 2026-07-22 — Start with a static HTML/CSS/JS prototype, no backend
Reasoning: validates the interaction flow (report type selection → input →
extraction → result) before any extraction logic exists. Zero setup cost —
opens directly in a browser, no server or build step required.

### 2026-07-22 — Report type is selected explicitly by the user, not auto-detected (for now)
Reasoning: auto-detection of report type is itself a classification problem
that needs its own validation. Starting with explicit selection removes that
variable while the extraction pipeline for each type is being built.
Revisit once per-type extraction is stable.

### 2026-07-23 — OpenMed adopted as full engine, with clarified layer boundaries
After reviewing `dhis2-export`, `fhir-interop`, and `zero-shot-ner` docs in detail,
the layer split is:
- Extraction: OpenMed zero-shot GLiNER toolkit (custom labels per report type,
  no fine-tuning needed per type) + specialized OpenMed NER models as a second signal.
- Normalization (ICD-10/LOINC/vaccine codes): still ours to build — no mature
  open tool covers this well.
- Free-text de-identification inside extracted fields: OpenMed's
  `hipaa_safe_harbor` pipeline (same engine as the MedNexus de-id tool).
- Export (FHIR/DHIS2): ours to map schema -> FHIR/DHIS2 shape; OpenMed's
  `export_dhis2()` and `to_bundle()`/`to_operation_outcome()` are late-stage
  privacy/assembly helpers, not extraction or auto-mapping tools. `export_dhis2()`
  expects data already in DHIS2 dataValueSet/tracker shape — it is a final
  privacy pass before handoff to an authenticated uploader, not a starting point.

Follow-up: review OpenMed's "Egypt PDPL & Morocco Law 09-08" compliance
checklist and "African Developer Onboarding" docs given our regional context.

### 2026-07-25 — First working end-to-end extraction; load GLiNER directly, not via openmed.infer()
The first real extraction ran successfully (free text -> structured
NotifiableDiseaseCase). Three issues had to be fixed, worth recording so
they are not repeated for the other report types:

1. `openmed.ner.infer()` resolves model_id against the HuggingFace Hub, so
   a local folder name was treated as a repo id and failed with a 401
   RepositoryNotFound. Fix: load GLiNER directly from the local checkpoint
   folder with `local_files_only=True`. No Hub call, fully offline.
2. GLiNER checkpoints are marked by `gliner_config.json`, not the
   `config.json` that regular transformers models use.
3. Port 8000 is already used locally by the MedNexus de-identification
   project. This module now uses 8001. Two local projects must not share a
   port — the browser silently talks to whichever server answers.

Process lesson: an unhandled exception in FastAPI returns a 500 generated
outside the CORS middleware, so the browser reports a misleading "CORS
policy" error instead of the real cause. The global exception handler in
main.py now keeps CORS headers on errors and prints the traceback. Check
the server terminal, not the browser console, for the real error first.

### 2026-07-25 — Project moved under Git version control, pushed to GitHub
Motivation: a VSCode session closed mid-work and cost time re-establishing
environment variables and running processes. Code itself was never lost
only because nothing had been committed yet — that was luck, not process.
Repository: https://github.com/drsamehmomen7/mednexus-public-health (private).
`backend/models/` (downloaded GLiNER weights, 600MB+) and `venv/` are
gitignored — reproducible via `scripts/download_gliner_model.py` and
`requirements.txt`, not meant to live in source control.

### 2026-07-26 — Messy real-note test caught 3 rule-based bugs; confidence badges worked as designed
First test on non-clean clinical shorthand ("pt c/o fever x3d... hx of
contact w/ confirmed case... results pending... 29yo") surfaced real gaps
that the clean-sentence tests never would have:

1. `diagnosis_status` and `lab_confirmed` matched the substring "confirmed"
   anywhere in the text — including a mention of a CONTACT's confirmed
   case, not the patient's own status — while ignoring "results pending"
   for the patient's own test. Fixed: both now check for pending/awaiting
   language first, before the confirmed/positive keyword scan.
2. Date regex only handled 4-digit years (2026-07-01, 01/07/2026) — missed
   the common clinical shorthand "15/6/26" (2-digit year). Added a third
   pattern, assumed to be 2000s.
3. Age regex only handled "34-year-old" / "34 years old" — missed the
   shorthand "29yo". Extended the pattern to cover both.

Validation: the confidence-badge feature (added earlier the same day)
correctly flagged the wrong disease_name ("rash", 51%) as low-confidence
on first run, which is exactly its intended job — catching model
uncertainty before it reaches statistics or export.
Regression tests for all three bugs added to test_extraction.py using the
real note text verbatim, so future changes to the rule-based helpers
cannot silently reintroduce them.

### 2026-07-26 — Second messy-note test caught negation handling + 2 more parsing gaps
Different failure mode this time — negation, not shorthand. Note: "Ruled
out dengue based on negative rapid test. Suspected typhoid fever pending
blood culture... age 45 yrs... presented on 26 Jun 2026."

1. **Most important bug found so far**: disease_name extracted "dengue" —
   the disease the text explicitly RULES OUT — instead of "typhoid", the
   actual suspected diagnosis. The system had no concept of negation; it
   just took the first NER-tagged disease entity. Fixed by adding
   `start`/`end` character offsets to ExtractedEntity (GLiNER's
   predict_entities already returns these) and checking a 40-character
   window before each disease entity for negation cues ("ruled out",
   "excluded", "negative for", "r/o", etc.) before selecting it. If a
   negated mention was skipped, the confidence report now notes it
   explicitly rather than silently disappearing.
2. Date regex still only handled numeric formats — missed "26 Jun 2026"
   (day + month name + year). Added two new patterns (day-month-year and
   month-year-day orderings) using Python's `calendar` module for month
   name/abbreviation lookup, not a hardcoded list.
3. Age regex required "old" or "yo" — missed "age 45 yrs" (no "old"
   suffix). Added a second pattern requiring an explicit "age"/"aged" cue
   word before the number, to avoid false-positives like "3 years ago".

Negation-aware selection is applied to disease_name only for now (highest
clinical stakes). Region/facility do not get this yet — revisit if a real
report surfaces a negated location/facility mention.

### 2026-07-26 — Refactor before replicating the pattern to other report types
Code review of extraction.py / rule_based.py / ner_client.py before adding
Immunization/Laboratory/etc. Found and fixed:
- Negation-aware entity selection (`is_negated`, `first_non_negated_entity`)
  was living inside notifiable_disease's extraction.py — moved to a new
  shared module `entity_selection.py`, since other report types (e.g.
  "no evidence of pneumonia" in a syndromic report) need the same logic
  and must not each get their own copy.
- Per-field confidence dict construction was repeated 3x with the same
  ternary shape — extracted to `confidence.py` (`model_confidence()`,
  `rule_based_confidence()`), so every report type's confidence report has
  an identical, single-source-of-truth structure.
- `RULE_BASED_FIELDS` was defined but unused (dead code) — now actually
  used to build those confidence entries via a dict comprehension.
- Removed unused `datetime` import in rule_based.py.
- Added tests/test_rule_based.py: direct tests for extract_first_date and
  extract_age, independent of the extraction pipeline. Future report types
  reusing these can trust them without re-testing through a full pipeline.
No behavior changed — 36 tests pass (was 21; 15 new, all for rule_based.py
directly). Next report type (Immunization) should import from
entity_selection.py and confidence.py rather than reimplementing them.

### 2026-07-26 — Persistence layer added: PostgreSQL store for reviewed records
First step of the agreed short-term roadmap (data store → Render → Metabase).
- SQLAlchemy models in `db_models.py`, engine/session setup in `db.py`,
  connection read from `DATABASE_URL` env var (defaults to a local
  Postgres URL; Render will supply this automatically once a Postgres
  instance is attached).
- `POST /reports/notifiable-disease/save` persists a record AFTER human
  review — this table is the "reviewed and trusted" store a BI tool reads
  from, not a raw extraction log.
- `needed_review` is computed once at save time (via a shared
  `needs_review()` helper in confidence.py) and stored as a plain boolean
  column, denormalized on purpose — so Metabase can filter/aggregate on it
  without parsing the JSON confidence blob in every query.
- The full confidence report is still stored as JSON alongside, for audit.
- Tested in this sandbox using SQLite as a stand-in (no Postgres server
  available here) — confirmed inserts and the needed_review computation
  work correctly. Real Postgres setup happens locally before this is
  trusted end-to-end.
- Frontend: added a "Save reviewed record" button that overlays whatever
  the reviewer edited in the input boxes onto the last extraction result
  before sending it to /save — manual correction now actually persists,
  not just displays.

### 2026-07-26 — Backend deployed successfully to Render (trial, synthetic data)
Second step of the short-term roadmap complete. `render.yaml` Blueprint
created both the web service and Postgres database together.

One issue hit and fixed: the first deploy failed because Render's default
Python runtime (3.14) has no prebuilt wheel for `pydantic-core==2.23.4`,
so pip fell back to building it from source via Rust/maturin — which
failed due to a read-only filesystem restriction in Render's build
environment. Fixed by pinning `PYTHON_VERSION: 3.12.7` as an env var in
render.yaml, matching a version with prebuilt wheels for every dependency.

Verified end-to-end: `/health` returns 200 from the live URL
(https://mednexus-public-health-api.onrender.com), and
`POST /reports/notifiable-disease/save` successfully wrote a record to
the Render Postgres instance (confirmed via the FastAPI /docs UI).

Not tested on Render yet: `/extract` — the GLiNER model weights are
intentionally not in git, so this endpoint will 503 there until/unless a
model-download step is added to the build. Not needed for this trial;
the goal was validating the deployment + persistence chain, not
re-running extraction remotely.

### 2026-07-23 — Core schemas stay system-agnostic; ministry-specific integrations are optional adapters
Correction from stakeholder: MedNexus's public health module must work across
any country's health system, not be built around one (Egypt, DHIS2, etc.).
Reasoning: current interest is Kuwait's healthcare system, not Egypt's — a
system-specific core would need rework for every new country/ministry.
Decision: core schemas (NotifiableDiseaseCase, etc.) stay based on
international standards only (ICD-10, LOINC, FHIR shapes). DHIS2 export,
Egypt PDPL mapping, or any ministry-specific integration become separate,
optional exporter/adapter modules added later — never a dependency of core
extraction or normalization logic.

### 2026-07-26 — Metabase set up (self-hosted, free) as step 3 of roadmap; first 4 indicators built
Reasoning: Metabase Cloud only offers a 14-day free trial before requiring
payment ($100/month Starter plan) — not a fit for a still-synthetic-data
trial phase. Ran the Open Source edition instead: self-hosted locally via
the standalone JAR file (no Docker needed), which is free indefinitely.
- Required Java 21 (JDK 8, already installed locally, is too old — Metabase
  dropped support for anything below 21). Installed Eclipse Temurin 21
  separately; existing Java 8 left untouched.
- Running from C:\metabase\metabase.jar via:
  `java --add-opens java.base/java.nio=ALL-UNNAMED -jar metabase.jar`
  Kept outside the mednexus-public-health repo entirely — it's a
  standalone analytics tool, not project code, and isn't tracked in git.
- Connected to the Render Postgres instance (external connection string,
  SSL required) — sync found the single existing table,
  notifiable_disease_records, as expected.
- Built and saved 4 SQL questions, combined into one dashboard
  ("Notifiable Disease Overview"): Cases by Disease, Cases by Region,
  % Needing Review, Cases Over Time (weekly). All currently show 1 row —
  only the single test record (id=1) exists in Render's Postgres so far.

Follow-up: seed a handful more synthetic notifiable-disease records
(varying disease, region, needed_review) so the dashboard actually shows
shape before treating it as validated.

### 2026-07-26 — Dashboard validated with seeded synthetic data
Ran `backend/scripts/seed_synthetic_records.py` against the live Render
`/save` endpoint — 6 new records (ids 2-7), varying disease, Kuwait
governorate, and confidence level. Total 7 records. Confirmed all 4
Metabase indicators now show real distribution, not a flat single row:
6 distinct diseases, 6 distinct regions, 28.6% needing review (2/7, from
the two seeded records given a deliberately low model confidence score),
and a 5-week spread on the Cases Over Time trend. Metabase/roadmap step 3
is now considered fully validated, not just "connected."

### 2026-07-26 — Notifiable Disease domain, phase 2: live sync + dashboard breakdowns
Three items requested before moving to the next report type: (1) confirm
the frontend/backend flow writes straight into the same store Metabase
reads, (2) file upload (docx) for reports — deferred, see below, (3)
dashboard redesign inspired by an external notifiable-disease dashboard
(PHF Science / ESR, NZ) — cases + rate per 100k nationally and by region,
broken down by age/sex/ethnicity.

1. **Live sync confirmed, no new code needed.** Metabase already reads
   directly from the same Postgres Render uses — any record saved via the
   "Save reviewed record" button appears on refresh with no separate ETL
   step. The actual gap was that the local backend's default
   `DATABASE_URL` points at a local Postgres instance that doesn't exist
   yet locally, not Render. Fix: set `$env:DATABASE_URL` to the Render
   external connection string before starting uvicorn locally — now part
   of the local dev routine (see README, Terminal 1). Verified
   end-to-end: extracted a synthetic dengue case locally, saved it,
   confirmed it appeared in Metabase (id 8, 7→8 rows) after a refresh.
2. **Dashboard redesign — partial, matched to what the schema supports.**
   Added two new SQL questions: Cases by Sex (`patient_sex` grouping) and
   Cases by Age Group (age bucketed into 0-4/5-14/15-24/25-44/45-64/65+
   via CASE, with a sort_key column to force numeric-not-alphabetic
   ordering — sort_key must stay excluded from the visualization itself,
   only used for row ordering). Converted existing questions to proper
   chart types instead of raw tables: Cases by Disease → bar, Cases by
   Region → bar, Cases by Sex → pie/donut, Cases by Age Group → bar
   (order-preserving), Cases Over Time → line. % Needing Review stays a
   plain number.
   Explicitly NOT replicating the reference dashboard's ethnicity
   breakdown or per-disease dropdown filter yet — ethnicity is a
   sensitive attribute this project deliberately does not collect (see
   system-agnostic/no-ministry-specific-logic ground rule), and "rate per
   100,000" needs a population-by-region reference table we don't have
   yet (a separate, deliberate follow-up if wanted, not built here).
3. **Docx file upload — descoped.** User confirmed the real workflow is
   free-text only (doctor types/pastes a report, extracts, saves) — no
   file upload, no integration with any live hospital system. Dropped
   from the plan entirely, not just deferred.

### 2026-07-26 — Dashboard v2: population reference, chart types, cross-filter
Explicit user pushback led here: before adding more report types
(breadth), the single working report type needed to look decision-ready,
not just technically functional. Concretely:
- Added `backend/scripts/create_population_reference.py` — creates
  `region_population` (6 rows, real public 2025 governorate population
  estimates, not synthetic — this is public demographic reference data,
  not patient data, so real figures are fine and more useful than
  placeholders). New question "Rate per 100k by Region" joins this
  against case counts.
- Converted flat-table questions into real chart types: Cases by Disease
  (bar), Cases by Region (bar), Cases by Sex (pie/donut), Cases by Age
  Group (bar), Cases Over Time (line). % Needing Review stays a number.
- Added a single dashboard-level filter ("Disease", Text/Category, Is
  operator) cross-filtering Cases by Disease, Cases by Region, Cases by
  Sex, Cases by Age Group, Cases Over Time, and % Needing Review all at
  once. Each underlying SQL question needed a `{{disease}}` Field Filter
  variable mapped to `notifiable_disease_records.disease_name` — mapping
  it to the wrong column (e.g. Region on the Cases by Region question)
  silently pollutes the dropdown with mismatched values and needs fixing
  per-question, not just at the dashboard filter level.
- Gotcha worth remembering: a table created directly in Postgres (e.g.
  via a script using the SQLAlchemy engine) does not appear in Metabase
  until a manual "Sync database schema now" is triggered from Admin →
  Databases — Metabase does not auto-detect new tables on its own
  schedule immediately.
- Explicitly not replicated from the reference dashboard: ethnicity
  breakdown (sensitive attribute, deliberately not collected) and a
  region choropleth map (Metabase has no native support for custom
  Kuwait-governorate boundaries; a bar chart substitutes for this).

Not yet decided: whether this is now "decision-ready" enough to move on
to more report types, or whether further dashboard maturation is still
needed first — open question for the next session.

