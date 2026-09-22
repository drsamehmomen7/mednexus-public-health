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

### 2026-07-27 — Metabase replaced by a custom in-app dashboard page
Reversal of the 2026-07-26 Metabase decision, for a reason that should
have been established BEFORE picking a BI tool: the dashboard is meant to
be shown to decision-makers, not just used internally by the team. That
requirement was never asked about up front, and it's the one that decides
the tool. Metabase OSS gives essentially no control over visual identity
(colours, typography, layout, card design) — fine for internal
exploration, wrong for anything presented externally. Also only supports
one filter widget per variable comfortably, and can't match the product's
green brand.

What actually transferred, and what didn't — worth being precise, because
the Metabase work was NOT wasted:
- Transferred as-is: the database schema, the Render connection, every
  indicator definition (the SQL for cases by disease/region/sex/age/time,
  the % needing review computation, the rate-per-100k join), and the
  cross-filtering model. That's the hard part and it was already correct.
- Discarded: only the rendering layer — i.e. Metabase drawing the charts.

New implementation:
- `GET /reports/notifiable-disease/dashboard-data` in main.py returns the
  whole dashboard payload in one response: summary numbers, all five
  breakdowns, and the available filter options (so the frontend never
  hardcodes disease/region/year lists).
- Four controls, all combining with AND: disease, year, region, and
  `measure` (count vs rate per 100,000). Measure applies to EVERY
  breakdown, not just the regional one — each row carries a precomputed
  `value` field so the frontend doesn't need to know which measure is
  active.
- That required population stratified by region x age group x sex:
  `scripts/create_population_strata.py` builds `population_strata`
  (72 rows). Governorate totals are real 2025 estimates; the age/sex
  split within each governorate applies national proportions because
  governorate-level stratification isn't published anywhere public. This
  is a documented approximation — good for comparable rates, NOT quotable
  as official statistics. The older `region_population` table is now
  redundant but left in place.
- `frontend/prototype/dashboard.html` — single self-contained page using
  Chart.js from CDN, reusing the existing `style.css` palette so it looks
  like part of the same product. Linked from the extraction page.

Known limitation, accepted for now: each filter change fires ~12 separate
queries against Render's free-tier Postgres in Oregon, so a refresh takes
3-4 seconds from Kuwait. Not a code problem — it's round-trip latency.
Options if it becomes annoying: collapse the queries into fewer round
trips, or run Postgres locally for development and keep Render for demos.

Process lesson (the important one): ask what the artifact is FOR — internal
use vs external presentation — before choosing the tool that produces it.
Two days of tool work were spent before that question surfaced, and it
surfaced from the user, not from me.


### 2026-07-27 — Schema extended to match standard reporting forms
Reviewed how notifiable disease reporting is actually done — CDC/NNDSS,
WHO IDSR, and UKHSA's current paper form (v3, Dec 2025). They converge on
a common structure, and our schema was missing several near-universal
fields. Added: onset_date (epidemic curves are drawn by symptom onset, not
by when paperwork arrived — this matters more than report_date),
vaccination_status, travel_related + travel_country (separates imported
from locally-acquired cases), occupation (drives contact-tracing priority
for food handlers, healthcare and childcare workers), and outcome (needed
for case fatality rate). Also wired up icd10_code and lab_test_type, which
existed in the schema but were never persisted.

Two things NOT adopted from the reference forms: patient name/DOB/address
(the schema is deliberately de-identified) and ethnicity (a sensitive
attribute this project does not collect — same reasoning as the dashboard
decision).

`init_db()` uses create_all, which creates missing TABLES but never alters
existing ones, so scripts/add_extended_case_columns.py adds the columns to
the deployed table. Stopgap — switch to Alembic before real data exists.

### 2026-07-27 — 500 synthetic reports generated, and what running them found
Docx upload was descoped, but the underlying need — realistic volume — was
real. 8 records proved the pipeline worked and demonstrated nothing.

scripts/generate_synthetic_reports.py writes reports as FREE TEXT in four
clinician "voices" (structured template, prose note, clinic shorthand, and
one that includes a ruled-out differential), because generating structured
records would test nothing — extracting structure from messy prose is the
whole product. It also builds actual epidemiology rather than noise: a
measles outbreak in one governorate over six weeks with a proper epidemic
curve, background sporadic cases, disease-specific age profiles,
seasonality, and regional counts proportional to population. It emits
ground_truth.json alongside, so extraction accuracy is measurable as a
number per field instead of eyeballed.

scripts/load_synthetic_reports.py runs the REAL pipeline over them and
reports per-field accuracy. Deliberately not a shortcut: loading
ground_truth.json straight into the database would have been far faster
and would have tested only the dashboard.

Running it surfaced four bugs that hand-written single-note tests had not,
all of which produced plausible-looking wrong answers:

1. **Pending result overrode an explicit classification.** "probable case,
   results pending" returned suspected, because the pending check ran
   before the keyword scan. Fixed so pending only blocks CONFIRMED — the
   direction where over-claiming is dangerous — and leaves an explicitly
   stated probable/suspected alone.
2. **lab_confirmed matched only the literal word "confirmed".** Real notes
   write "confirming X", "culture +ve", "serology positive". Broadened,
   with negated phrases ("non-reactive", "not confirmed", "negative")
   stripped FIRST since several contain a positive marker as a substring.
3. **Negation cues after the entity were missed entirely.** The negation
   work in the 26 July entry only checked text BEFORE a disease mention
   ("ruled out dengue"). Reports equally often write "Hepatitis A was
   ruled out" — so the excluded disease was extracted as the diagnosis,
   the same clinically dangerous error in mirror image. Trailing cues are
   now checked too, bounded to the entity's own sentence: without that
   bound, "Measles confirmed. Rubella negative." would negate Measles.
4. **Region was extracted by zero-shot NER despite being a closed
   vocabulary.** Reports write "Ardiya Clinic, Farwaniya" and the model
   frequently attributed the whole phrase to the facility, returning no
   region ~15% of the time. See the next entry.

Accuracy went from disease_name 80% / region 85% / diagnosis_status 80%
to 100% across all seven extracted fields on a 20-report sample.

One "failure" turned out to be the generator's fault, not the pipeline's:
the shorthand voice wrote "?X. Labs pending." for probable AND suspected
cases alike, so the text carried no signal distinguishing them — the
extraction was reading it correctly and being scored wrong. Fixed in the
generator, and there is now a check that every report's text contains a
cue for its true status. Worth remembering: when a measurement disagrees
with the system, the measurement can be the thing that's broken.

Test count went 41 -> 69, all new ones regressions for the above.

### 2026-07-27 — Closed-vocabulary matching, without breaking system-agnosticism
Region is a CLOSED vocabulary — a deployment has a fixed list of regions.
Zero-shot NER is the right tool for open vocabularies (disease names,
facility names, where new values appear constantly) and the wrong one here:
asking a model to guess when the six valid answers are already known throws
away information.

The tension: the ground rule says no country-specific logic in extraction,
and a hardcoded governorate list would violate it. Resolved by separating
three concerns so no layer holds knowledge that belongs to another:
- services/gazetteer.py knows HOW to match a vocabulary. Contains no
  country, ministry, or deployment values whatsoever.
- services/vocabularies.py knows WHERE a deployment's vocabulary lives —
  it reads regions from population_strata, which already has to list every
  region for rate-per-100k. One place to declare regions, no chance of two
  lists drifting apart.
- services/extraction.py knows neither. The gazetteer arrives as an
  optional parameter; when absent, behaviour is unchanged and it falls back
  to NER, so a fresh install with no reference data still works.

Matching is conservative on purpose: exact whole-token matches plus
optional aliases, never fuzzy. Assigning a case to the wrong region is
worse than leaving it Unknown for a human to fill in. Gazetteer hits are
reported in the confidence report as source "gazetteer", not as a model
score they didn't come from.

Same pattern should be reused for any future closed vocabulary (facility
lists, vaccine names) rather than reaching for the model.

### 2026-07-27 — Disease gazetteer added, closing the gap the 500-report run exposed
Loading all 500 reports through the real pipeline (not the 20-report
sample the previous entry measured) told a different story: disease_name
was actually 84.8% (424/500), not 100% — the smaller sample simply hadn't
surfaced the failures yet. Worth remembering alongside the generator-bug
lesson above: a 20-report sample can look perfect and still be wrong.

Sample mismatches showed two distinct failure modes, both plausible-
looking: GLiNER sometimes labelled a symptom or clinical sign ("myalgia",
"posterior cervical lymphadenopathy") as `disease`, and sometimes returned
no disease entity at all ("Unknown") even when one was clearly stated.

Disease name is exactly as closed a vocabulary as region — a deployment
reports on a known, fixed list of notifiable diseases — so the same
architecture applies: `services/vocabularies.py::load_disease_gazetteer()`
now builds a `Gazetteer` from `data/notifiable_diseases.json` (10
diseases), seeded via `scripts/build_disease_vocabulary.py` from the
distinct disease names in the synthetic ground truth. This is a
placeholder, the same way population_strata is the real thing for
region: nothing stops a real deployment swapping in its own reportable-
disease list later, and extraction logic doesn't change either way.

Unlike region, disease selection has to stay negation-aware — a
gazetteer match inside "ruled out X" is not evidence of X. `Gazetteer.find()`
normalizes text internally (lowers, collapses whitespace) to make matching
forgiving, which means its match offsets are into the NORMALIZED string,
not the original — useless for the negation-window check, which needs
real character offsets. Rather than change `Gazetteer` (region still
depends on its current behaviour), `entity_selection.py` gained
`first_non_negated_gazetteer_term()`: it matches vocabulary terms directly
against the ORIGINAL text (case-insensitive, whole-word, longest-first),
wraps each hit in a small `_GazetteerHit` stand-in exposing the same
`.start`/`.end`/`.label` shape as `ExtractedEntity`, and reuses `is_negated()`
unchanged rather than duplicating its window logic.

Testing that against real report text (not hand-written examples) surfaced
a second, independent bug — one that predates the disease gazetteer and
also affects the NER path: `is_negated()`'s PRECEDING-cue check had no
sentence boundary, only the TRAILING check did. "Dengue fever was ruled
out on negative testing. Influenza confirmed by PCR." read the previous
sentence's "ruled out" as negating the confirmed Influenza in the next
one, because "ruled out" fell inside Influenza's 40-character preceding
window with nothing to stop it at the sentence break. Fixed symmetrically
to the existing trailing-window bound (`_text_before_entity_in_same_sentence`,
mirroring `_text_after_entity_in_same_sentence`). Not separately measured
on the NER-only path, but the same phrasing pattern ("X ruled out. Y
confirmed.") is common in the generated reports, so it likely accounted
for some of the original 84.8%, not just gazetteer misses.

Wired into both call sites that already had `region_gazetteer` —
`app/main.py`'s `/extract` endpoint and `scripts/load_synthetic_reports.py`
— as an equally optional `disease_gazetteer` parameter, so behaviour is
unchanged when it isn't supplied.

Result on the full 500-report re-run: disease_name 84.8% → 100%, all
seven fields now at 100%. Flagged-for-review dropped from 33 (6.6%) to 0
(0.0%) — expected, not a red flag: every disease in this synthetic set is
in the 10-item gazetteer, so nothing falls through to the lower-confidence
NER path that review-flagging depends on. A disease outside that list
still falls back to NER and can flag for review same as before.

Not yet done: no pytest regression tests cover the new gazetteer path or
the preceding-window fix specifically (the existing 69 all still pass
unchanged, since the new parameter defaults to None). Add tests mirroring
`test_entity_selection.py`'s structure before reusing this pattern for
Immunization or another report type.

### 2026-07-27 — patient_sex added; regression tests written for today's fixes
Two follow-ups from the disease gazetteer entry above, done the same day.

**Regression tests.** The gazetteer/negation fixes above had no dedicated
tests — `test_entity_selection.py` gained four: a gazetteer term selected
when not negated, one skipped when ruled out, and the sentence-boundary
fix verified on both the gazetteer path and the original NER-entity path
(same bug, same fix, both paths now covered independently). 69 → 73 tests.

**patient_sex.** Noticed because the dashboard's "Cases by sex" chart
showed 100% "unknown" — expected, since patient_sex is one of the seven
fields extraction never attempted (see the gap list `load_synthetic_reports.py`
prints every run). It had looked populated before, during the Metabase
phase, only because `scripts/seed_synthetic_records.py` hand-typed
`"patient_sex": "female"` etc. directly into ~6 test records posted
straight to `/save` — bypassing extraction entirely. Nothing to do with
the real pipeline.

Sex is exactly as rule-based as age: checked all 500 report texts first,
and every single one is covered by one of two phrasings — clinical
shorthand ("33yo M") or prose ("54-year-old female") — zero exceptions.
`rule_based.py` gained `extract_sex()`, mirroring `extract_age()`: two
regexes, returns a plain "male"/"female"/None string (kept free of the
PatientSex enum, same reasoning as extract_age returning a plain int) —
`extraction.py` wraps it in `PatientSex(...)` at the call site, falling
back to `PatientSex.UNKNOWN` when nothing is found. Added to
`RULE_BASED_FIELDS` for confidence reporting, and moved from
`NOT_YET_EXTRACTED` to `EXTRACTED_FIELDS` in the accuracy script.

Result: 100% on all 500 reports, confirmed both via the raw function
directly and through the full extraction call. 73 → 78 tests. Dashboard
reloaded and confirmed visually: "Cases by sex" now shows a real
male/female split instead of a single "unknown" slice.

Next planned session: `onset_date` extraction (same rule-based approach),
plus purely cosmetic dashboard polish (colors, animation) — no functional
changes intended alongside that.

### 2026-07-28 — Render free-tier database reset; stale-table schema mismatch
Dashboard suddenly failed with "Failed to fetch" on port 8001, and the
backend logged `relation "population_strata" does not exist` on the very
first query after restarting uvicorn. `population_strata` isn't created by
`init_db()` — it's a separate one-off script (`create_population_strata.py`),
so its absence meant the connected database had never had project setup
run against it. `notifiable_disease_records` had exactly 2 rows (not 500,
not 0), confirming this wasn't the same database the 500-report runs had
been using all along.

Root cause: not fully confirmed. Render's free PostgreSQL tier hard-deletes
a database 30 days after creation (44 days including the grace period to
upgrade), with no backups — the initial hypothesis here — but flagged
after the fact that the project's active history doesn't obviously span
that long, so this is left open rather than settled. The mitigation is the
same regardless of cause: either upgrade the Render instance to paid, or
treat a reset as routine and re-run setup (documented in
CURRENT_STATUS.md's ground rules now).

Recovery attempt 1: `python -m scripts.create_population_strata` (worked,
72 rows) then `python -m scripts.load_synthetic_reports` — this got 20
reports in before crashing: `column "icd10_code" of relation
"notifiable_disease_records" does not exist`. Checked `db_models.py`
directly — it already correctly defines `icd10_code` and every other
extended field (onset_date, patient_sex, travel_*, vaccination_status,
outcome, lab_test_type). The model was never wrong. The issue is that
`Base.metadata.create_all()` (what `init_db()` calls on every startup)
only creates tables that don't exist — it never alters an existing one to
add columns a changed model now expects. The `notifiable_disease_records`
table that existed on the reset database predated `icd10_code` being
added to the model at some point, and `create_all()` had been silently
leaving it un-migrated ever since, invisible until an INSERT finally tried
to write to that specific column.

Fix: dropped the stale table outright (`DROP TABLE IF EXISTS
notifiable_disease_records`) and called `init_db()` directly to recreate
it from the current model — safe here only because all data is synthetic.
Re-ran `load_synthetic_reports` clean: all 500 processed, all eight fields
(including patient_sex) at 100%, 0 flagged for review.

This is a known, accepted limitation of `create_all()`-based schema
management (already flagged in `db.py`'s own docstring: "switch to Alembic
migrations once real data exists"). Noted here as the concrete failure
mode it eventually produces, for the next time a schema field is added:
a fresh database will get it right automatically; an existing one won't,
and needs either a manual `ALTER TABLE` or a table drop-and-recreate (only
acceptable pre-production, with synthetic data).

### 2026-07-28 — onset_date added, closing out the core field set
Last of the fields planned alongside patient_sex. Checked all 500 reports
first (same discipline as disease/sex): two phrasings, not one.

Prose reports state onset directly, anchored by one of three keywords —
"Onset", "Symptoms began on", "Date of symptom onset" — followed by a
date in one of the formats `extract_first_date` already parses. Clinical
shorthand reports don't state a date at all: "c/o cough x12d" means
symptoms have been present for 12 days as of the report date, so
onset_date has to be computed as `report_date - 12 days` rather than
parsed from text directly.

Confirmed by testing before writing anything: naively reusing
`extract_first_date` for onset_date (no keyword anchor) matched 0/500 —
report_date and onset_date are both present in the same report, in
different formats or positions, and an unanchored scan can't tell them
apart. `rule_based.py` gained `extract_onset_date(text, report_date)`:
tries the keyword-anchored date first (reusing `extract_first_date` on
the text just after the keyword, not duplicating its format parsing),
falls back to the duration-from-report_date calculation. Requires
`report_date` to already be computed, since the shorthand path depends on
it — `extraction.py` now computes `report_date` before calling it.

Result: 100% on all 500 reports, confirmed via the raw function and the
full extraction pipeline. 78 → 84 tests. All nine extracted fields
(disease_name, diagnosis_status, onset_date, report_date, patient_age,
patient_sex, region, facility_name, lab_confirmed) now at 100% on the
full 500-report run; 0% flagged for review.

Remaining gap fields (occupation, travel_related, travel_country,
vaccination_status, outcome) are lower priority — none are needed for the
charts currently on the dashboard. Next planned work: dashboard visual
polish (cosmetic only), then likely the Immunization report type — the
real Kuwait MOH 2025 childhood immunization schedule is on hand as the
vaccine-name source, the same role notifiable_diseases.json plays here.

### 2026-07-28 — Immunization report type built, tested, and completed
Followed the same reasoning discipline as every fix above: check real
phrasing across the full generated set before writing any regex, then
verify against all 500, not a sample.

**Schema decisions before writing any code.** Two gaps found in the
existing `ImmunizationRecord` schema by cross-checking it against the
real Kuwait MOH 2025 schedule PDF, both fixed before generating data
around them: `InjectionRoute` had no `INTRADERMAL` value (BCG genuinely
uses I.D. per the official schedule) — added, purely additive. Second,
most of the schedule (birth through 18 months) is naturally stated in
months, and `patient_age` alone (years) would show "0" for nearly all of
it — asked the user directly rather than guessing; the answer was to add
`patient_age_months` (0-24, optional) alongside `patient_age`, populated
for infant doses and left unset once years is the natural way to state
an age (2y, 3.5y, 10-12y, 16-18y boosters).

**Vaccine gazetteer is a REAL source, not synthetic.** `data/vaccines.json`
(12 vaccines: BCG, DTaP, Hepatitis B, Hexa, MMR, MMRV, Meningococcal
ACWY, OPV, Pneumococcal, Rota, Tdap, Varicella) transcribed directly from
the official schedule table — canonical names match the table's own
wording ("Rota" not "Rotavirus", since that's what the source document
itself uses). `vaccine_name` does NOT need negation-aware matching the
way `disease_name` does — an administered-dose report isn't where a
vaccine gets "ruled out" — so it uses `Gazetteer.find()` directly, same
as `region`.

**Generator (`generate_immunization_reports.py`) modelled on the real
schedule**, not invented ages/doses. Explicit scope decisions: pregnant-
mother Tdap excluded (different patient, adult age profile, out of scope
for a first version); one report = one vaccine administration event,
matching how real immunization registries actually record multi-vaccine
visits (three separate entries, not one entry listing three vaccines) —
some reports mention co-administered vaccines as flavour text only, not
part of ground truth. Adverse event descriptions split by age
(infant vs older) after an early check showed "mild fussiness" attached
to a 16-year-old's Tdap booster — same principle as occupation-by-age in
the disease generator.

**Two self-inflicted ambiguities found by testing, not by inspection**,
both fixed at the source rather than patched around:
1. One "severe" adverse-event description string was itself "hospitalization
   following the dose" — colliding with the narrative voice's own template
   wrapper ("developed X following the dose (severity)"), which duplicated
   the phrase for that one case. Fixed in the generator (shortened to
   "hospitalization"), not in the extractor.
2. The extractor's own trailing-phrase strip was written, tested in
   isolation, then accidentally dropped when the function was pasted into
   `rule_based.py` — caught by re-running the SAME test against the real
   file rather than assuming the isolated test result still applied.

**Rule-based extraction, all verified against all 500 before shipping:**
`extract_age_months`, `extract_dose_number`, `extract_route`,
`extract_adverse_event` — added to `rule_based.py`. New orchestrator
`immunization_extraction.py` mirrors `extraction.py`'s structure exactly.
New `SavedImmunizationRecord` ORM model in `db_models.py` — named
differently from the Pydantic `ImmunizationRecord` schema on purpose, to
avoid a name collision (same reason `NotifiableDiseaseCase` and
`NotifiableDiseaseRecord` are distinct names). New endpoints
`POST /reports/immunization/extract` and `/save`, and
`scripts/load_immunization_reports.py`, both mirroring the Notifiable
Disease equivalents.

**Real GLiNER run result:** 100% on 10/11 fields immediately; facility_name
measured 99.0% (495/500) — GLiNER's zero-shot "facility" label was
swallowing a trailing ", <region>" when both appear on one comma-separated
line ("Facility: Central District Hospital, Al Asimah"). Same root cause
already known from Notifiable Disease's region-vs-facility confusion (see
the region gazetteer entry above), just manifesting the other direction
here. Fixed with `_strip_trailing_region()` — strips a trailing ", <known
region>" from facility_name using the region gazetteer, which is safe
specifically because region is a closed vocabulary: it only ever fires on
an actual region name, never a real facility name that happens to contain
a comma for some other reason. Re-run after the fix: 100% on all 11
fields, 500/500, 0% flagged for review. 107 tests total (99 → 107, 8 new
covering the orchestrator and this exact fix).

Not done: vaccine_code and lot_number (terminology normalization,
deferred same as ICD-10 for Notifiable Disease). No dashboard or review
UI for Immunization yet — API only.

Next planned work: dashboard visual polish (Notifiable Disease) and
making the project's landing page more visually engaging with more
explanation of what it does — both purely cosmetic/presentation, no new
extraction logic.

### 2026-07-29 — Frontend redesign, document upload, batches, export
A long session covering several linked pieces of work, in the order they
were actually built.

**Frontend redesign.** app.js was fixed to route Extract/Save to the
correct backend endpoint based on the selected report-type card — it had
always called the notifiable-disease endpoints regardless, so Immunization
never actually worked in the UI despite the card being selectable. A
separate Immunization dashboard was built
(`immunization-dashboard.html` + `GET /reports/immunization/dashboard-data`)
with charts specific to the data's shape rather than reused verbatim from
Notifiable Disease — notably an age-BAND breakdown (birth-2mo, 3-6mo,
7-18mo, then 2-3y/3-9y/10-15y/16-18y) instead of the disease dashboard's
0-4/5-14/... buckets, since nearly the whole immunization schedule
happens before age 2 and those buckets would put almost everything in
one bin. Both dashboards then got a shared visual pass: an extended
accent palette (slate/amber/rust/rose) so each chart has its own
identity, soft card shadows instead of flat borders, a real one-line
description per chart, and a thin animated "pulse line" as the one
deliberate signature flourish — restraint everywhere else, per the
"spend your boldness in one place" principle. The landing page
(`index.html`) was rebuilt with a hero illustration (original inline SVG,
not stock photography — avoids both a copyright question and a broken
hotlink), a "How it works" section, and a "Report types" section marking
Notifiable Disease/Immunization as Live and the rest as Coming next.
Brand identity: wordmark "Med" (light) + "Nexus" (bold green) in a
Fraunces display face, slogan "Every report, counted.", and — after two
earlier attempts (a converging-lines abstraction, then a medical cross)
were rejected as unclear or wrong — a logo mark showing loose incoming
report cards resolving into one structured record, no container tile.
Attribution was moved out of the header into the footer only, worded
carefully after a revision: "Built by Dr. Sameh Momen" alone, then a
disclosure that MedNexus is built over open-source biomedical models
"developed with an AI engineering collaborator" (no vendor name) and
that extraction logic, schemas, and clinical decisions are
human-designed and human-reviewed — accurate rather than either
overstating or omitting the AI's role.

**Document upload + report-type detection.** The "Upload a document"
dropzone had been a non-functional placeholder since the prototype's
first version. `services/document_parsing.py` extracts text from
DOCX (python-docx) and TXT; `services/report_type_detection.py` guesses
which report type the text is by reusing the SAME disease/vaccine
gazetteers extraction already depends on, plus a handful of structural
keywords per type ("notifiable"/"diagnosis" vs "vaccine"/"dose") — no
separate model, and tested 100% correct against all 1000 real synthetic
reports (500 of each type) before shipping. Always surfaced as a
suggestion the reviewer confirms or overrides, never applied silently —
a real uploaded document can legitimately mention a disease name inside
an immunization report or vice versa, so this heuristic is not a
certainty. Testing the parser against generated documents surfaced a
real bug: `extract_text_from_docx` grouped all paragraphs before all
tables instead of true document order, which put a footer paragraph
(written after a field table) ahead of the table's content in the
extracted text. It happened not to break extraction on the specific
documents tested, but was a real latent risk on any document that
interleaves paragraphs and tables — which describes most real reporting
forms. Fixed by walking `document.element.body` directly instead of
python-docx's separate `.paragraphs` and `.tables` collections.

**Batch/cohort system.** Triggered by a concrete ask: being able to
save a set of reports (e.g. one region/period) into its own named group,
view it on its own dashboard, and start a fresh one without disturbing
the baseline data. Implemented as a nullable `batch_label` column on
both `notifiable_disease_records` and `immunization_records` — NULL
means "original bulk data," never explicitly batched, which is what the
existing 500+500 rows are and stay. New `GET .../batches` endpoints list
existing batches with counts; both dashboards gained a Batch filter;
the save flow gained a "Save to" selector (existing batch, or type a new
name). Non-destructive by design — no data is ever deleted or moved
between batches automatically. Same `create_all()` limitation as the
icd10_code incident applied again: adding a column to an EXISTING table
needs a manual `ALTER TABLE ... ADD COLUMN`, not a drop-and-recreate,
since the existing rows are worth keeping this time (real data was
starting to accumulate, not just synthetic).

**Export.** Batches have no separate backup — they live in the same
tables as the synthetic bulk data. The synthetic 500+500 are always
regenerable from the same seed if the Render database resets again the
way it did on 2026-07-28; anything saved by hand (a real upload, a
manually corrected record) is not, unless exported first. Both
dashboards gained Export JSON (full-fidelity, every column) and Export
CSV (drops the nested `confidence` blob, keeps `needed_review`) buttons,
respecting whichever batch filter is active. Upgrading the Render
instance to a paid tier would remove the recurring-reset risk entirely;
noted as an option, not yet decided.

**3 realistic DOCX demo files** were built with docx-js (Kuwait MOH
letterhead, a 2-column field table, a signature-line footer) from three
real, already-tested synthetic reports (one Meningococcal disease case,
one Tdap dose with a mild AEFI, one newborn Hepatitis B dose) —
specifically chosen from the "structured voice" reports whose phrasing
the extraction pipeline was already tuned around. Verified 100% correct
extraction on every field for all three, using the real
`document_parsing.py` + extraction pipeline, before delivering them —
these exist so the full upload -> detect -> extract -> save-to-batch
flow can be demonstrated to decision-makers against documents that look
like real official forms, not plain pasted text.

120 tests passing by the end of the session (up from 107).

### 2026-07-29 — Immunization extract route silently broken by an editing mistake
Found by the user testing the two Immunization DOCX demos through the
real UI: both failed with "Not Found" — FastAPI's literal 404 body, not
an application error. `POST /reports/immunization/extract` had stopped
being a registered route entirely.

Root cause: when `/reports/notifiable-disease/export` was added earlier
the same day, the edit's old/new text boundary ended right at the
`@app.post("/reports/immunization/extract")` decorator line — the
replacement reproduced everything up to that line but not the line
itself, silently deleting the decorator while leaving the function body
below it untouched. The function still existed as plain Python; FastAPI
just never registered it as a route. Every test run that session
imported main.py successfully (no syntax error) and other new routes
were spot-checked, but nothing re-verified that a PRE-EXISTING route was
still present after a later edit — the gap wasn't caught until real use
surfaced it.

Fixed by restoring the decorator, then auditing every `/reports/*` and
`/health` route by name against the full expected list (14 routes) —
not just confirming the routes touched in that turn. Worth remembering
as a general practice for future edits near existing decorators: check
the full route list, not just the new ones.

Confirmed end-to-end afterward: both Immunization DOCX demos (Tdap AEFI,
Hepatitis B newborn) now extract correctly through the real running
backend, not just the sandboxed test used during development.

### 2026-07-30 — Notifiable disease list replaced with a real source (CDC 2025)
Prompted by a direct question about the system's own logic: why was the
notifiable-disease gazetteer only 10 items when `vaccines.json` had 12
from a real official document? The honest answer was an inconsistency —
`notifiable_diseases.json` had always been synthetic, originally derived
FROM the ground truth of a generator the developer built, not from any
authoritative list. Worth fixing before Immunization and Laboratory get
the same scrutiny.

Searched for a Kuwait MOH-published notifiable disease list first, to
match the vaccine schedule's precedent exactly — none found via search
(unlike the immunization schedule, which the user already had as a PDF).
WHO's International Health Regulations (2005) Annex 2 was checked next
and rejected as the wrong reference: it's a narrow 4-disease "public
health emergency of international concern" framework, not a routine
national surveillance list — the wrong TYPE of document for what this
project models (case-by-case reporting of ~50 common notifiable
diseases, not global emergency escalation).

Settled on CDC's "Protocol for Public Health Agencies to Notify CDC
about the Occurrence of Nationally Notifiable Conditions, 2025"
(approved by CSTE June 2024, implemented January 1, 2025) — fetched
directly from CDC's own site, ~90 conditions with full official naming.
Not used verbatim: about a third of the CDC list is either non-
infectious (cancer, lead-in-blood, silicosis, acute pesticide illness —
none of which fit this schema's onset/lab-confirmation shape) or a
narrow US-specific lab-classification subtype (VISA/VRSA screening,
individual US arboviruses like Jamestown Canyon or Powassan virus) with
little relevance outside that context. Curated down to 54 genuinely
infectious, broadly-relevant conditions, keeping every one of the
original 10 (Influenza was ADDED back in deliberately — it isn't a
standalone CDC routine-notification category, since ordinary seasonal
flu is too common to case-report individually in the US, but it's
foundational to what's already built here and regionally relevant, so
kept as a stated exception rather than silently dropped).

Verified before considering this done: re-ran the disease gazetteer
against all 500 existing synthetic reports — still 100% (expected,
since 54 is a strict superset of the original 10) — but caught a false
alarm along the way. A quick check calling `Gazetteer.find()` directly
(bypassing the real negation-aware code path) showed 428/500, which
looked like a real regression; re-testing through the actual
`extract_notifiable_disease_with_confidence()` orchestrator (the code
path every real request actually uses) confirmed 500/500. Worth
remembering: `.find()` alone was never how disease_name gets extracted
in production — testing it directly is not representative and produced
a misleading result here.

Explicitly scoped what this does NOT do yet: the 500-report SYNTHETIC
test corpus still only mentions the original 10 diseases by name — the
gazetteer now recognizes 54, but that hasn't been exercised by generated
test data, only verified not to regress the existing 10. Expanding the
generator to realistically cover the other 44 (each needs its own
onset/symptom/lab phrasing, not just a name) is separate, larger work,
not done here. `lab_tests.json` remains an unsourced synthetic
placeholder — the next item, ideally against a real terminology standard
(LOINC) rather than another developer-picked list. `vaccines.json`
stays real (Kuwait MOH) but pediatric-only — whether to add adult/travel
vaccines is open.

Added a "Data Sources" section to the landing page footer disclosing
exactly this: which vocabularies are real vs. synthetic-placeholder,
and where the real ones come from — matches the project's existing
transparency practice (the AI-collaboration disclosure) rather than
letting a demo audience assume every list is equally authoritative.

### 2026-07-30 — Real-world text stress test (not synthetic) — findings for later
Ran two genuinely real, published texts through the Notifiable Disease
pipeline — not to replace the synthetic generator (still the right tool
for measuring accuracy against a known answer), but to check whether the
gazetteer/rule-based logic generalizes past the phrasing this project's
own generator happens to use. No individual-level de-identified case
report datasets are freely available without a formal data use agreement
(confirmed via search — e.g. MIMIC-IV requires PhysioNet credentialing);
CDC's own public notifiable-disease data is aggregate statistical tables,
not narrative text. Settled on real published outbreak narratives
instead: a Wikipedia article on the 2026 Kent (England) meningococcal
disease outbreak, sourced from UKHSA/press reporting, and a WHO Disease
Outbreak News report on the 2025-26 Marburg virus disease outbreak in
Ethiopia (published 26 January 2026) — both real, both public, neither
requiring credentialed access.

**What generalized well:** disease_name (gazetteer) correctly matched
"meningococcal disease" and "Marburg virus disease" in both real texts
with no changes needed. patient_age correctly parsed "19-year-old" from
real prose. lab_confirmed correctly picked up "laboratory confirmed" /
"laboratory confirmation" phrasing in both. region correctly returned
Unknown for non-Kuwait locations (Kent, Jinka) — expected behaviour, not
a failure, since the gazetteer is deliberately Kuwait-scoped.

**What didn't, and should get a follow-up pass:**
1. `onset_date` — its keyword anchors ("onset", "symptoms began on",
   "date of symptom onset") come from this project's OWN generator's
   phrasing. Neither real text used any of them: the UK article said "a
   case... presented in East Kent"; the WHO report said "developed
   symptoms on 23 October." Both real, both never matched. Worth adding
   "developed symptoms" and "presented with/in" as additional anchor
   phrases once there's time to verify they don't introduce false
   matches elsewhere.
2. `diagnosis_status` — the WHO Marburg text describes 14 confirmed and
   5 probable cases together; keyword-priority order picked up
   "probable" (checked first, per the existing rule that a cautious
   classification shouldn't be overridden by an unrelated "confirmed"
   elsewhere) even though the specific FIRST case being described was
   confirmed. This isn't really a bug in the priority logic — it's the
   schema's single-patient assumption meeting a text that narrates
   multiple patients with different statuses at once. Worth remembering
   if real free-text intake ever includes multi-case outbreak summaries
   rather than one-patient reports, which is the shape this schema
   currently assumes throughout.

Both source files kept as-is (with citation) for whoever wants to re-run
this check after future rule_based.py changes.

### 2026-07-30 — Second Render reset; migration script made permanent
Same symptom as 2026-07-28: uploads started failing with "Not Found" /
`Could not reach the backend`, traced to `column "batch_label" does not
exist` once uvicorn came up — confirming the Render web service AND
database had both been recreated under new names
(`mednexus-public-health-api`, `mednexus-public-health-db`), not just
reset in place. Same root cause as before: `init_db()`'s
`create_all()` only creates missing tables, never alters an existing
one, so a freshly-created table reflects whatever `db_models.py` looked
like the moment the very first request hit it — if that's before
`batch_label` existed, the column is simply absent until patched
manually.

One new wrinkle this time: the first fix attempt used a `python -c
"..."` one-liner with a nested double-quoted SQL string
(`\"SELECT ...\"`) inside an already-double-quoted PowerShell argument.
PowerShell doesn't treat backslash as a quote-escape character the way
bash does, so the string broke and Python saw an unclosed paren. Lesson:
don't hand-write multi-statement inline `-c` commands with mixed
quoting for PowerShell — write a short `.py` file instead, every time,
even for something that looks like a one-liner.

Fixed properly this time: `scripts/add_batch_label_column.py` is now a
permanent, reusable, idempotent script (`ADD COLUMN IF NOT EXISTS` on
all three tables, then confirms by name) rather than a throwaway
command — next time this happens, it's `python -m
scripts.add_batch_label_column`, not reconstructing the fix from
scratch. Recovery after that was the by-now-standard sequence: generate
+ load all three report types fresh. Confirmed back to 100% on all
fields (Laboratory explicitly re-verified; Disease and Immunization
completed without errors in the same run).

### 2026-07-30 — Local dev workflow stabilized (.env + startup script)
Prompted by the user wanting reliability rather than re-running the same
handful of commands every session, and asking whether upgrading Render
to a paid plan would prevent future resets.

**Render pricing/policy, confirmed via search (current as of this
date):** free Postgres databases expire 30 days after creation with a
14-day grace period before permanent deletion — matches what's already
been observed twice. Paid instances don't expire and get real backups.
Compute (web service) and Postgres are billed and upgraded separately —
upgrading only one doesn't fix the other's failure mode. Cheapest paid
tier for each is roughly $6-7/month, ~$13-14/month total for both. This
is the user's call to make (cost vs. reliability trade-off), not
something to decide unilaterally — presented the facts and left the
decision open.

**Local workflow fix (implemented):** `app/db.py` now loads
`python-dotenv` at import time, so `DATABASE_URL` can live in
`backend/.env` (gitignored; `.env.example` is the committed template)
instead of being retyped into `$env:DATABASE_URL` every new terminal
session — a real environment variable, if one happens to be set, still
takes priority over the `.env` file. `start_backend.ps1` bundles venv
activation and starting uvicorn into one script, so starting the
backend is `cd backend` then `.\start_backend.ps1` — no separate
activation step.

**Getting there took several real, worth-remembering PowerShell/Windows
gotchas**, all now in the ground rules above so they don't get
rediscovered from scratch next time: a browser download strips the
leading dot from `.env.example`, landing as `env.example`; PowerShell
blocks running any local `.ps1` by default
(`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`,
one-time per machine); Windows separately flags any downloaded file,
`.ps1` included, as untrusted even after that policy change
(`Unblock-File`, one-time per file); and pasting multiple PowerShell
statements as one block can silently merge them onto one line in a way
that breaks argument parsing — the fix throughout this whole session
was the same one, run every command separately and wait for its result
before the next.

### 2026-08-06 — Indicators layer built end-to-end
Fourth planned pillar, agreed in advance: metrics that cross-reference or
sit above individual report types, distinct from each report type's own
dashboard. Kept in a new `backend/app/services/indicators.py` rather
than folded into `main.py`'s existing dashboard-data functions, since
the logic shape is different — sometimes a join across report-type
tables, sometimes a breakdown a single report type's own dashboard
doesn't already surface, but always cross-cutting rather than
per-report.

Two indicators built, one at a time, each verified against real data via
a throwaway check script before moving on:
- `vaccination_coverage_by_region` — doses from `immunization_records`
  joined against `population_strata`, the same denominator table
  Notifiable Disease/Immunization already use for rate-per-100k.
  Deliberately grouped by region only, not also by age_group — the
  population table's age bands (0-4/5-14/...) are the adult-oriented
  buckets from the Notifiable Disease dashboard, not Immunization's
  under-2-focused month bands, so splitting by age_group here would
  compare doses against a denominator shaped for a different purpose.
- `test_positivity_by_region` — positive/(positive+negative) from
  `laboratory_records`, same definition the Laboratory dashboard's
  headline `pct_positive` already uses, just broken out by region (that
  dashboard's own region breakdown was a raw count, not a rate).

Combined `GET /indicators/dashboard-data` in `main.py` just calls both
functions and returns them side by side — deliberately thin, no shared
"filter" parameter across the two, since they filter different things
on different tables and a shared filter would be misleading.

**Frontend layout decided by direct comparison, not guessed.** Three
rough concepts were sketched (bar charts / one comparison table / a card
per region) and shown with the real numbers before building anything;
the user picked a combination of the bar-chart and per-region-card
concepts. `frontend/prototype/indicators-dashboard.html` was then built
as the real file (not a mockup) reusing `style.css` and the exact same
CSS classes/colors as the other three dashboards — no new design system
introduced. Linked into the nav on all three other dashboard pages
(one line each) so navigation between all four is symmetric.

**Real data caught a real gap in the demo numbers.** With only 500
synthetic immunization doses spread across Kuwait's actual governorate
populations (600k-1.2M each), `coverage_pct` came out to ~0.01% in every
region — technically correct, but visually useless for a bar chart since
every bar looks the same height. The dashboard charts
`doses_administered` instead for now (which does vary meaningfully
region to region) and keeps `coverage_pct` in the underlying data for
when a more realistic data volume exists. Not treated as a bug to fix
now — the indicator's math is right, the input volume just isn't
representative yet.

### 2026-08-06 — Render Postgres reset a third time; both services upgraded to paid
Third occurrence (2026-07-28, 2026-07-30, now this one) of the same
failure shape: `immunization_records` and `laboratory_records` found
empty while `notifiable_disease_records` was untouched. Root cause still
not conclusively identified across any of the three resets. Recovered
via the existing `load_immunization_reports.py` /
`load_laboratory_reports.py` loaders — full 500-report reload each,
re-confirmed 100% accuracy on every field, same as every prior run.

**New gotcha found during recovery, not previously documented:** both
loaders only `INSERT`, they never clear existing rows first. Running
`--limit 10` as a quick trial and then the full run right after (without
clearing in between) left 10 duplicated rows in each table — caught by
noticing the region totals from a check script summed to 510, not 500.
Fixed with a new one-off `scripts/clear_immunization_and_lab_records.py`
that empties both tables before a clean reload. Documented as a standing
rule in `CURRENT_STATUS.md`, not just a one-time fix, since the same
--limit-then-full pattern will keep coming up.

**Decision made, not just discussed this time:** both Render services
(web service and Postgres) upgraded to paid instance types, specifically
to stop the recurring free-tier expiry going forward. Confirmed this
does NOT retroactively restore data already lost in a reset — it only
prevents the *next* one. Both services were also grouped under one
Render Project ("mednexus-public-health") via Render's Projects feature,
for easier billing/management in the dashboard — purely organizational,
no code or connection-string changes involved.

### 2026-08-06 — Terminology normalization started: ICD-10 for Notifiable Disease
First of three planned terminology domains (ICD-10 for diseases, LOINC
for lab tests, vaccine codes — likely CVX — for immunization), taken one
at a time. `icd10_code` had existed as an unpopulated column since the
schema was first written; this is the first time it's actually filled.

**Standard chosen: WHO ICD-10, not US ICD-10-CM.** Consistent with the
project's existing system-agnostic/international-standards ground rule
(2026-07-23 entry above) — ICD-10-CM is a US clinical-billing extension
of WHO ICD-10 with extra digits for billing granularity that don't apply
here. Used three-character WHO category codes throughout.

**All 54 diseases mapped in a new `backend/data/icd10_codes.json`, kept
deliberately separate from `notifiable_diseases.json`.** The gazetteer
file continues to drive name matching during extraction, completely
unaffected by this addition; the new lookup is only consulted at SAVE
time (`main.py`) via a new `load_icd10_lookup()` in `vocabularies.py`,
following the same caching/fail-safe pattern as the existing gazetteer
loaders (missing or malformed file just means `icd10_code` stays empty,
never a crash). Sourced from WHO ICD-10 category codes; the two
diseases the model was least confident on from memory (Melioidosis,
Hantavirus pulmonary syndrome, Chikungunya) were verified via search
before including them, rather than guessed.

**9 of the 54 flagged for Dr. Sameh's clinical review, not silently
defaulted.** A single 3-character code can't always represent a real
clinical distinction the case-report schema doesn't currently capture:
Hepatitis A/B/C (acute vs chronic — different codes entirely), HIV
infection (which resulting condition), Haemophilus influenzae invasive
disease (no single WHO code fits — depends on site: meningitis, sepsis,
pneumonia), Influenza (not even in the same ICD-10 chapter — J09-J11,
respiratory, not A00-B99), Malaria (species not captured), Syphilis
(stage not captured), and Tuberculosis (site + confirmation method not
captured — flagged as the highest-scrutiny one given TB's public-health
weight). Each flag entry in the JSON file documents exactly what
clinical nuance the default is collapsing, so the reviewer isn't
starting from scratch. Provisional approval given to proceed with the
defaults while full review of the 9 stays open — matches the project's
established pattern of shipping a defensible, documented default rather
than blocking on perfect data (same approach as the CDC-sourced disease
list itself).

**Not yet verified against a real save** — the code path exists and the
lookup logic was checked directly against the real data files, but an
actual extract → save → confirm-icd10_code-in-Export-JSON pass hasn't
been run yet. That's the next immediate step before starting LOINC.

### 2026-08-16 — LOINC for Laboratory: lab_tests.json expanded 15→71, then mapped
Verified the ICD-10 auto-population end-to-end (Influenza → J11
confirmed in Export JSON) before starting this — the prior entry's
open item is closed.

**First attempt at LOINC mapping was scoped wrong, caught and
corrected.** Initial pass mapped LOINC codes onto the *existing* 15
test names without re-examining whether those 15 were the right tests
for the (by then) 54-disease list — a repeat of exactly the shortcut
already avoided once for the disease list itself. Corrected after
direct feedback: real-source review of the test LIST had to happen
first, same as `notifiable_diseases.json` got against CDC's disease
list. Rebuilt `lab_tests.json` from CDC NNDSS "Laboratory Criteria for
Diagnosis" per disease (53 of 54 — Tetanus has no confirmatory lab
test at all; diagnosis is clinical, discovered via direct source
verification, not assumed), then corrected against direct clinical
review: added confirmatory/molecular tests alongside initial screening
picks for TB (GeneXpert MTB/RIF alongside sputum culture), HIV (RNA
PCR alongside the antigen/antibody screen), Hepatitis B/C (RNA/DNA PCR
alongside serology), Malaria (RDT alongside blood smear), Meningococcal
(blood culture + PCR alongside CSF culture/Gram stain), Diphtheria
(PCR alongside culture), Brucellosis (serology alongside culture), and
Leptospirosis (PCR alongside serology). Net: 15 → 71 test names, still
covering the original 10 diseases' exact original test names
unchanged (existing 500-report Laboratory data stays 100% valid, no
reload needed).

**LOINC mapping needed a genuinely different structure than ICD-10's.**
A LOINC code identifies analyte + specimen + method together, not just
the analyte — one test name can correspond to 5-8 real LOINC codes
depending on specimen/method. `icd10_codes.json`'s flat
name-to-code-string format couldn't honestly represent this, so
`loinc_codes.json` uses a richer per-entry object (`{loinc, status,
notes}`) with a 7-value mapping-status taxonomy — `EXACT`,
`ACCEPTABLE_GENERIC_SPECIMEN`, `ACCEPTABLE_GENUS_LEVEL`, `PROXY`,
`COMPOSITE`, `NO_DIRECT_LOINC`, `REJECTED_MISMATCH` — replacing a
simpler flag-string approach after review. Three tests deliberately
left uncoded (`loinc: null`) rather than forced to a technically-present
but wrong/misleading code: **Poliovirus Stool PCR** (the only LOINC
code found is a CULTURE method — a genuine method mismatch, not a
granularity compromise, rejected outright rather than accepted as
"close enough"), **Hantavirus IgM Serology** (the only code found is
Sin-Nombre-subtype-specific; defaulting to it would silently narrow
every case to one viral subtype with no evidence that's correct), and
**Leprosy Skin Biopsy** (histopathology, not a discrete lab analyte —
no LOINC code should exist for this by design, not by gap).

Wired into `main.py`'s laboratory save endpoint via a new
`get_loinc_code()` helper in `vocabularies.py`, same separated-lookup/
save-time-only pattern as `load_icd10_lookup()` — extraction-time
gazetteer matching is untouched regardless of any mapping decision
here.

### 2026-08-16 — MedNexus Seven: architecture crosswalk, frozen contracts, approved roadmap
This project's owner is developing a second, parallel platform
("MedNexus" — an enterprise medical-document-intelligence system,
currently strongest at document UNDERSTANDING and a Clinical Privacy
Policy Engine for de-identification, via a different Claude
conversation). A cross-project architecture session this session
produced four documents, now the authoritative cross-project reference,
placed in `docs/mednexus-integration/`:

- **Architecture Crosswalk v1.1** — stage-by-stage comparison. Key
  finding from direct inspection of both codebases (not just each
  project's own documentation): MedNexus Main has NO persistence layer
  at all, so ANALYZE/VISUALIZE/INDICATORS aren't things to "merge" —
  this project is simply ahead there, unopposed. The real integration
  surface is UNDERSTAND/PROTECT (MedNexus Main's strength) meeting
  EXTRACT/STANDARDIZE (this project's strength). Also surfaced a real
  naming collision: MedNexus's existing `PUBLIC_HEALTH` domain
  recognition signals ("case notification," "epidemiological
  investigation") describe this project's Notifiable Disease report
  type well but NOT Immunization or Laboratory — resolved by keeping
  `PUBLIC_HEALTH` narrow (surveillance/notification only), routing
  Laboratory through MedNexus's existing separate `LABORATORY` domain,
  and giving Immunization its own new `IMMUNIZATION` domain.
- **Clinical Semantic Context Contract v0.1** and **Clinical Extraction
  Contract v0.1** — the frozen (not-yet-implemented) shape of what
  MedNexus's UNDERSTAND/PROTECT stages will eventually hand to this
  project's EXTRACT stage, and what EXTRACT must/must-not do with it.
  Notable ratified rule: **EXTRACT must remain terminology-independent
  — a terminology mapping error must never affect extraction
  recognition or confidence.** This project's existing separated ICD-10/
  LOINC-lookup-at-save-time pattern is cited in the contract itself as
  the working proof this separation holds in production (specifically:
  Poliovirus Stool PCR's rejected LOINC mapping never touched
  extraction accuracy for that field).
- **Domain Intelligence Track Roadmap** — this project continues as
  "Track B," finishing its current checkpoint before starting a
  Laboratory-domain vertical (which generalizes, not rebuilds, this
  project's existing Laboratory work), then Pathology, then Radiology.

**Governance decisions from this session, now standing:** the
checkpoint is named **Public Health Stable Scope Checkpoint v0.1.0** —
explicitly a *scope* checkpoint, never to be described as "complete,"
"production ready," or "real-world validated." A **Cross-Track
Synchronization Policy** now applies — a formal sync brief is required
when a shared contract assumption changes, at each stable checkpoint,
or before any real convergence work; routine internal changes don't
need one. Two checkpoint *levels* were distinguished: a **Domain
Development Checkpoint** (reachable independently, synthetic data, this
project's own lightweight report-type detection as a temporary
bootstrap) versus a **MedNexus Integrated Domain Checkpoint** (requires
real contract-conformance with an implemented `MedNexusDocumentContext`
from MedNexus Main) — this project is not blocked on the latter to keep
working. Real PHI remains prohibited on this project's infrastructure
regardless of any of this, until a real PROTECT implementation AND a
separate Ministry-level infrastructure decision are both in place —
unchanged from the existing standing rule, just reaffirmed in the new
cross-project context.

No code changed as a result of this session — architecture and
governance only, per explicit instruction.

### 2026-08-16 — CVX vaccine codes started
Same pattern as ICD-10/LOINC: sourced from CDC's official `cvx_list.pdf`
(not memory) for all 12 vaccines in `vaccines.json`. 8 resolved with a
single unambiguous active CVX code (BCG, DTaP, Hexa, MMR, MMRV, OPV,
Tdap, Varicella) — notably OPV required catching that the trivalent
formulation code (CVX 02) is INACTIVE (retired after the 2016 global
OPV switch); the correct current code is the bivalent formulation (CVX
178). 4 flagged `ACCEPTABLE_GENERIC_FORMULATION` because CDC currently
has multiple genuinely different active codes for the same vaccine
concept and `vaccines.json`'s naming doesn't specify which: Hepatitis B
(pediatric vs. adult dose — defaulted pediatric, matching this being a
childhood-schedule context), Meningococcal ACWY (conjugate vs.
polysaccharide vs. tetanus-protein-conjugate — defaulted conjugate),
Pneumococcal (PCV13 vs. newer PCV15/20/21 vs. non-US PCV10 — defaulted
PCV13), Rotavirus (monovalent vs. pentavalent — defaulted monovalent).
Saved to `backend/data/cvx_codes.json`; not yet wired into the
Immunization save endpoint (blocked on the 4 flagged decisions, not a
technical blocker — the wiring itself is a direct copy of the ICD-10/
LOINC pattern once the defaults are confirmed or corrected).

### 2026-08-16 — Python environment recovery: backend/venv_recovery replaces broken backend/venv
`backend/venv`'s linked Python 3.10 install
(`AppData\Local\Programs\Python\Python310`) lost its `python.exe` — an
external machine issue, unrelated to this project. Rather than repair
the machine-wide install or borrow anything from the sibling MedNexus
Main project (kept strictly isolated throughout — never read from,
written to, or bootstrapped through), a fully independent, project-local
environment was built: `.runtime/Python310` (python.org's official
embeddable 3.10.11 package, MD5-verified against python.org's published
hash for that file) bootstrapped with pip via the official PyPA
`get-pip.py`, then `virtualenv` (the embeddable distribution ships
without the stdlib `venv`/`ensurepip` modules, so stdlib `venv` can't
create environments from it directly) to create `backend/venv_recovery`.
Both `.runtime/` and `backend/venv_recovery/` are gitignored.
`start_backend.ps1` now invokes `venv_recovery`'s interpreter by its
explicit full path instead of activating it first — a deliberate change
from the old "activate then run `python`" pattern, since explicit-path
invocation can't silently pick up whatever `python` happens to resolve
to on a given machine. Full 126-test baseline reconfirmed on the new
environment before any further work proceeded; `backend/venv` (broken)
kept in place, untouched, as a rollback artifact — not deleted.

### 2026-08-16 — Requirements split: backend/requirements.txt stays lightweight, extraction stack moves to a separate file
Running the real extraction path (GLiNER via `openmed[gliner]`) on the
newly-recovered environment surfaced that `backend/requirements.txt`
(9 packages: fastapi, uvicorn, pydantic, pytest, sqlalchemy,
psycopg2-binary, python-docx, python-multipart, python-dotenv) has never
included the extraction stack — `pip install "openmed[gliner]"` has
always been a separate, undocumented-in-any-requirements-file step
(README already described it this way; this was true before the
environment recovery too, just newly visible once a clean environment
needed rebuilding from scratch). Decision: keep them split rather than
merge. `requirements.txt` stays the lightweight API/DB/dashboard/test
surface — it's also exactly what Render's `buildCommand` installs, and
pytest's fake `ner_fn` means the test suite never needs GLiNER either,
matching `render.yaml`'s existing note that `/extract` deliberately
503s on Render without the model. A new
`backend/requirements-extraction.txt` will hold the local-only
extraction stack starting with `openmed[gliner]` (installed versions
confirmed: openmed 2.1.0, gliner 0.2.28, torch 2.13.0, transformers
5.13.1, tokenizers 0.22.2, ~89 packages total including the ML/NLP
tree). No full transitive lock file yet — deferred to a future
environment-governance milestone; the file will pin just the direct
`openmed[gliner]` line, the same level of pinning the rest of the
project's dependency declarations use today.

### 2026-08-16 — LOINC end-to-end verification CONFIRMED
Test cases prepared earlier (see the LOINC dataset entry above) were
finally run through the real UI once the environment was working again:
Measles IgM Serology extracted and saved → `test_code: "21503-8"`;
Poliovirus Stool PCR extracted and saved → `test_code: null` (the
deliberate `REJECTED_MISMATCH` entry from `loinc_codes.json`, working as
designed, not a bug). Both confirmed by matching full record content
(not just test name) against `GET /reports/laboratory/export?format=json`,
since that endpoint also returns 500+ pre-existing synthetic records
with overlapping facility/test-name combinations. Re-confirmed again
unchanged after the `openmed[gliner]` install (126/126 tests, `/health`,
both records still correct). LOINC is now IMPLEMENTED and verified,
matching ICD-10's status.

### 2026-08-16 — Local dev port convention: MedNexus Main = 8001, Public Health = 8002
With both projects now under active local development side by side,
port 8001 (this project's port since 2026-07-xx — see that entry above)
was reassigned to MedNexus Main, and Public Health moved to **8002** to
avoid the two servers colliding. `backend/start_backend.ps1` now binds
`--port 8002` (a comment there records the convention); the frontend's
`API_BASE` in `app.js` and all four dashboard HTML files moved from
`http://127.0.0.1:8001` to `http://127.0.0.1:8002`, including the
on-screen "backend unreachable" error text in each dashboard. Verified
live: backend health check, all four dashboards' data-load requests,
and a real extraction POST all confirmed reaching `8002` successfully
through the actual running servers. A repo-wide sweep afterward found
and corrected the remaining stale `8001` references describing this
project's own setup — `README.md` and `docs/mednexus-integration/
README.md`'s "Terminal 1" instructions, three port mentions in
`CURRENT_STATUS.md` (two "not yet pointed at Render" notes, the Local
dev routine section), and two in `Claud+OpenAi/MedNexus_Public_Health_
Authoritative_Handoff.md`. Left untouched deliberately: historical
entries in this file describing the port as it was at the time
(2026-07-xx's original 8001 choice, the 2026-07-28 incident report),
and `3 terminals.txt` (a literal terminal-session transcript, not
living instructions — editing it would falsify a historical record).

### 2026-08-17 — CVX end-to-end verification CONFIRMED
Same verification shape as ICD-10 and LOINC: a BCG Immunization report
(Central District Hospital, Al Asimah) and a Rota Immunization report
(Ardiya Clinic, Farwaniya) were run through the real extraction UI on
the current `venv_recovery` environment, backend confirmed running on
`127.0.0.1:8002` (current port convention), and saved. Both confirmed
via `GET /reports/immunization/export?format=json`, matched by full
record content (id, facility, date, age — not just vaccine name):
BCG → `vaccine_code: "19"`; Rota → `vaccine_code: "116"`. Both exactly
match `get_cvx_code()`'s direct-lookup result from the earlier wiring
sanity check, now confirmed through the real save path rather than a
bare function call. First attempt at this verification hit unrelated
process hygiene debt — multiple stale backend/frontend server processes
from earlier turns were still running and had never been fully
terminated, one of them silently holding port 8002 already, which
caused a fresh backend launch to fail to bind while an old process kept
answering `/health`. All `venv_recovery` processes were killed and a
single clean backend + frontend pair started before repeating the test
cleanly. Two unrelated field-level gaps noticed in passing, not fixed
here since they're outside CVX's scope: the BCG record's `route` came
back `"unknown"` instead of `"Intradermal"` (a rule-based extraction
miss on that phrasing), and neither record's `dose_number` populated
despite being stated in the source text. CVX is now IMPLEMENTED and
verified, matching ICD-10 and LOINC's status — terminology
normalization (ICD-10/LOINC/CVX) is complete for this checkpoint.

### 2026-09-17 — Batch Upload: planned first, built in 5 verified milestones, hard constraint held throughout
Requested as "a written technical plan first, for review, before any
code changes" — backend design, frontend design, confirmation that
existing systems (batch_label, confidence/needs_review) would be reused
rather than forked, a milestone breakdown, and named risks, all reviewed
and approved before a single line of implementation code existed. The
plan's central recommendation held for the whole build: no new backend
endpoints — the frontend loops the existing single-file
`parse-document`/`detect-type`/`{type}/extract`/`{type}/save` endpoints
once per file. Batch Upload ships with zero new backend code.

The one non-negotiable requirement, stated at the start and restated
before Milestone 4 specifically: per-report human review before save,
exactly as the single-report flow already enforces, with no path —
not even a convenience one — that bulk-approves review. This is why
every card's "Reviewed — ready to save" checkbox starts unchecked,
always, and is never programmatically checked by anything (a successful
detection doesn't check it, an edit doesn't check it, there is no
select-all/mark-all-reviewed control anywhere in the code), and why a
needs-type card (ambiguous detection) blocks only itself rather than
silently defaulting. Verified live, not just by design: editing a field
on one ready card was confirmed not to check its own or any other
card's box (same DOM node before and after, proving the card hadn't
even been re-rendered), and three ready cards' checkboxes were
confirmed independent — `[true, false, false]` after checking exactly
one of them.

Milestone 1 was a throwaway script (never shipped) driving 8-10 real
mixed-type files through the real endpoint chain before any frontend
code existed, specifically to get real timing instead of guessing: a
cold GLiNER load (the first extraction call after a fresh backend
start) measured 29-58s across two separate runs; every warm call after
it measured well under a second (0.16-0.92s). This is what ruled out
concurrency as worth building — a warm-dominated batch of ~10 files
costs one ~30-60s wait plus a handful of sub-second calls, sequentially,
and concurrent requests to the same process wouldn't obviously help
anyway given GLiNER's inference is CPU-bound work of uncertain
GIL-release behavior. The same script caught a real bug in itself on
its first run: building extract URLs from detect-type's raw label
("notifiable") instead of translating to the actual path segment
("notifiable-disease"). That exact mistake was carried forward as an
explicit warning into every later milestone — route through the same
`ENDPOINTS` map the single-report flow already uses, never build a URL
from the raw label.

Built in the order the plan proposed, specifically so each piece could
be verified against the real backend before the next was built on top
of it: Milestone 2 (sequential orchestration + per-file error isolation,
proven via a temporary diagnostic scaffold before any real UI existed —
a deliberately-empty file was used to force a real parse failure and
confirm the file after it still processed normally); Milestone 3 (the
real dropzone/multi-select and a live, cold/warm-aware progress grid,
replacing the scaffold — the cold card's amber "loading the model, up
to a minute" state was caught on screen mid-flight, not just inferred
from the end result); Milestone 4 (the editable review card grid,
factoring `renderFieldsTable()` and `collectEditedRecord()` out of the
single-report flow's own inline code so both use one implementation,
not two); Milestone 5 (the batch-wide save step, unioning all three
types' existing `/batches` endpoints client-side into one merged picker
rather than adding a combined backend endpoint, keeping the
zero-new-backend-code story intact through the very last piece).

Two real bugs were found this way — via live testing, not code review —
and both fixed immediately and re-verified rather than left as known
issues. (1) Milestone 3: `.batch-selection-summary { display: flex; }`
had the same CSS specificity as the `hidden` attribute's own
`display:none`, and an author stylesheet rule beats the UA stylesheet
at equal specificity, so the "Process Files" button was visible before
any file was ever selected — fixed with `:not([hidden])`. (2) Milestone
5: the save-error handling assumed FastAPI's `detail` field is always a
string, but a 422 validation error's `detail` is a structured array of
`{type, loc, msg}` objects — interpolated directly into a template
literal, it rendered as `"[object Object]"`. Fixed with a shared
`formatSaveError()` helper, which also quietly fixed the identical
latent bug already sitting in the pre-existing single-report
`saveRecord()` — that code used the exact same unsafe pattern since
before Batch Upload existed, it had just never been exercised by a real
validation failure until Milestone 5's forced-failure test (an
intentionally invalid `route` edit, chosen as a plausible real
reviewer-typo scenario rather than a network-failure mock) went
looking for one.

The finished save step was verified against the real database, not
just the UI: a 3-file mixed batch (one of each report type) saved into
a brand-new batch label, confirmed via each type's own
`/batches`/export endpoints; the same forced validation failure
confirmed the other two cards saved successfully while the failed one
stayed checked and retryable; retrying re-sent exactly one save request
(confirmed via the backend's own access log), leaving the two
already-saved records' ids unchanged, since a saved card's inputs are
disabled and `reviewedUnsavedItems()` skips anything already
`saveStatus: "saved"`; and selecting that same batch label again (not
"+ New batch...") on a second run correctly summed record counts across
tables — `"Milestone5-Test-Batch (2)"` shown before the run, correct
totals of 2 (notifiable) / 1 (immunization — the two failed attempts
correctly persisted nothing) / 2 (laboratory) after — rather than
creating a duplicate batch entry.

Batch Upload is now IMPLEMENTED: no new backend endpoints, no parallel
implementation of extraction/confidence/save logic, hard constraint on
mandatory individual review held and verified at every layer rather
than just asserted.

### 2026-09-20 — Upload page: Single/Batch mode switch, read-only type cards, dashboard links, filtered Save-to picker
Four small frontend changes to the extraction page, built between
2026-09-18 and 09-20 as separate, individually specified requests
(`index.html`, `app.js`, `style.css`, and a small `?batch=` read in each
per-type dashboard). No backend change, and nothing about how reports
are extracted, reviewed or saved changed.

- **Mode switch.** Single and Batch are alternative paths, not steps of
  one 1-2-3-4 sequence: Batch never reads Step 1 (type) or Step 2
  (input) because it detects each file's type itself. The page now has a
  two-button switch ("Single report" / "Batch upload"), and each shows
  only its own pane. Switching only hides and shows the panes, so
  nothing typed or reviewed in either is reset. `#batch` in the URL
  opens Batch directly; Single is the default.
- **Read-only type cards in Batch.** A non-selectable twin of the Step 1
  cards (Notifiable Disease, Immunization and Laboratory as Live;
  Syndromic and Outbreak/Cluster dimmed as Coming next) with the line
  "Each file's type is recognised automatically. Nothing to select
  here", so Batch doesn't suggest a choice it doesn't offer.
- **"View <Type> Dashboard" after a save.** Single shows one link for
  the saved type; Batch shows one per report type that had a saved
  record. If a batch label was used the link carries `?batch=<label>`
  (in Batch, only when all saved records of that type went to the same
  label, otherwise the plain dashboard). The Notifiable Disease,
  Immunization and Laboratory dashboards read `?batch=` on first load and
  select that batch if it exists. Links open in a new tab so unsaved
  review work on the page isn't lost.
- **Batch "Save to" picker narrowed by report type.** One batch label
  can span all three tables, so the picker unions the three existing
  `/batches` endpoints client-side and keeps which report types each
  label holds. While cards are ticked as reviewed it lists only labels
  that already hold at least one record of a ticked type (nothing
  ticked: all labels) and says so in a note; "Original data" and
  "+ New batch..." are always offered. It is a convenience filter only:
  saving still uses whatever is selected, each card still saves through
  its own type's existing `/save` endpoint, and a picked label that
  stops matching stays selected and is marked "— no matching records"
  instead of being switched silently. Single mode needed no change: its
  batch list was already limited to the selected type.

The hard rule from the Batch Upload entry is unchanged, and was
re-checked in the code: there is no select-all or mark-all-reviewed
control anywhere, and nothing ever sets a card's "Reviewed" checkbox to
checked — only the reviewer's own click does. Also on record: the Batch
dropzone is a native `<label for>` because a scripted `.click()` version
did not open the file picker in one real Chrome profile (cause not
established); the Single dropzone still uses a scripted click. Checked by
DOM inspection and headless-Edge screenshots against the real backend in
the development environment; own-browser confirmation of these four
changes is not recorded here.

### 2026-09-21 — PDF upload: ingestion only, pypdf over pypdfium2, planned first, built in 4 verified milestones
Requested as a written plan first, with no implementation code until it
was reviewed, and approved in full on 2026-09-20 as nine numbered
decisions (D1-D9 below). The scope was deliberately narrow: PDF support
for BOTH Single and Batch upload with zero changes to the pipeline
behind it. PDF is an ingestion change — bytes in, text out — so
everything after `POST /reports/parse-document` (detect-type → extract →
confidence → review → save) is untouched, the response is still
`{"text": ...}`, and neither upload flow needed new logic; on the
frontend only two `accept` attributes and the dropzone hint changed.
Built as four milestones, each reported and approved before the next:
M1 backend ingestion, M2 frontend wiring, M3 the permanent pytest suite,
M4 this documentation. Out of scope by design: OCR, and any field-level
accuracy measurement on PDFs (last section).

**The nine decisions, all approved before code.**
- D1 — Library: `pypdf` 6.19.0 primary, `pypdfium2` as the named
  fallback pending M1's side-by-side check (next section).
- D2 — Dependencies in `backend/requirements.txt`: `pypdf==6.19.0`, and
  `httpx==0.28.1` only because `fastapi.testclient` needs it for the
  endpoint tests.
- D3 — Limits, applied to EVERY format rather than only PDF (same code
  path, so the protection is free): 10 MB per file and 30 pages. PDFs
  are counted from real page objects; DOCX/TXT have no pages, so their
  length is judged by an estimate of 3,000 characters per page (90,000
  characters).
- D4 — No crypto package. pypdf reads AES-encrypted PDFs only with an
  optional package (`cryptography` or PyCryptodome), so every
  AES-encrypted PDF is refused as password-protected — including an
  "owner-only" file (restrictions but no open password) that WOULD open
  if a package were installed. RC4-encrypted owner-only files are read:
  pypdf handles RC4 itself and an empty user password opens them.
- D5 — A deliberately small text clean-up, nothing more: ligatures
  (ff, fi, fl, ffi, ffl, st) expanded; exotic spaces (no-break, thin,
  ideographic) become plain spaces; soft hyphens, zero-width characters
  and the BOM removed; line/paragraph separators become newlines; the
  Symbol-font bullet becomes a real bullet; whitespace tidied. NOT done,
  on purpose: unwrapping hard-wrapped lines, de-hyphenating, stripping
  repeated headers/footers. Each is a guess about layout, and the
  accuracy pass should show which are worth building before any is.
- D6 — Every failure mode has its own honest message, worded and
  approved before implementation: not a real PDF (empty, damaged, or
  another file type renamed .pdf), damaged/unsupported PDF,
  password-protected, no selectable text (a scan — OCR isn't
  supported), over the page limit, over the size limit. The same pass
  fixed an existing bug: a corrupt `.docx` escaped as an unhandled 500
  whose body was the raw exception text, and now returns the same clean
  422 as the rest.
- D7 — Dropzone hint that sets the scanned-PDF expectation up front:
  "DOCX, TXT and PDF supported (PDFs need selectable text; scans aren't
  read yet). CSV planned for a later phase."
- D8 — Test strategy: a stdlib-only PDF builder (`tests/pdf_fixtures.py`)
  for everything constructible, PLUS one realistic static fixture from a
  different producer, so the suite isn't only tested on PDFs the project
  wrote itself. `.gitignore` now ignores `*.pdf` everywhere except
  directly inside `backend/tests/fixtures/`, and ignores
  `backend/data/Test Reports/` and `backend/data/pdf_test_reports/`.
- D9 — The 60 test PDFs Dr. Sameh supplied (20 per report type) and their
  `ground_truth.csv` live in `backend/data/pdf_test_reports/`: local
  only, gitignored, never committed, never quoted at length. M1 could
  read them for ingestion profiling only (statistics, short excerpts).
  Comparing extracted FIELDS to `ground_truth.csv` was kept as a
  separate later step and has not been started.

**pypdf vs pypdfium2: what the comparison showed, and why pypdf.** M1
profiled the 60-file set (20 per report type): every file is
single-page ReportLab output with standard non-embedded Helvetica/Times
fonts, 2.5-3.6 KB; none encrypted, none with form fields, none scanned,
no ligatures or odd characters; ingestion took 8.5 ms per file on
average and 14 ms at worst when re-measured on 2026-09-21 (M1's first
measurement said 21 ms and 44 ms — timings vary with machine load). On
the 10 files compared side by side, pypdf and pypdfium2 produced
IDENTICAL text (word-level and content-only agreement 1.000 on all 10,
re-confirmed on 2026-09-21). pdfminer.six, tried as well, reorders
blocks and form-style tables (word-level agreement with pypdf 0.69-0.90
on the 2026-09-21 re-run; M1 reported 0.20-0.90) and was dropped. Since
all 60 files come from one producer, a second "flavor" was built on
purpose: a 3-page synthetic report printed by headless Edge
(Chromium/Skia, embedded subset fonts) with a letterhead and footer on
every page, a form-style table, a wrapped `9-year-old` and a
soft-hyphenated paragraph. On it pypdf and PDFium agree on every letter
and digit and differ only on hyphens. pypdf (and pdfminer) split
soft-hyphenated words ("influ enza", "vacci nation", "coordin ator")
where PDFium keeps them whole. But where a real hyphen falls at a line
end, PDFium drops it and joins the lines around a stray noncharacter
(`9-year<U+FFFE>old`), while pypdf keeps `9-year-` and `old` on two
lines; the age rule reads neither form. Switching engines would trade
one hyphen artifact for another.

Decision, confirmed by Dr. Sameh after M1: stay with pypdf. It is pure
Python, so there is nothing native to install or ship in the
project-local embeddable Python 3.10 environment or on Render; it
matched PDFium on every file of the 60-file set; and the one observed
difference appears only in browser-printed documents with hyphenation,
which none of the 60 are. Swapping in a native PDFium binary now would
trade a dependency for a problem not yet seen on a real document.
Revisit only if a real PDF surfaces the soft-hyphen split — a
strict-xfail test (below) keeps that decision visible.

**What was built.** `services/document_parsing.py` gained
`extract_text_from_pdf` (text layer only), `normalize_pdf_text` and the
shared limits; `extract_text` checks size first, then dispatches by
extension. `POST /reports/parse-document` returns 200 `{"text": ...}` as
before, 415 for an unsupported extension, 413 over 10 MB, and 422 for
every unreadable or over-length case plus the existing empty-text
check. The specific message travels in `detail`, which both upload flows
show verbatim (Single's red status line, Batch's per-file error card),
so the wording is the user-facing contract. The endpoint reads at most
10 MB + 1 byte into memory, and parsing runs in a worker thread
(`run_in_threadpool`): PDF parsing is CPU-bound Python and would
otherwise stall every other request, `/health` included. Whatever the
third-party parser throws on untrusted input becomes the "damaged"
message and is logged by exception TYPE only, never its text — parser
messages can quote file content, and none belongs in logs.
`scripts/pdf_ingestion_profile.py` is the M1 diagnostic, kept for reuse:
a census of a folder of PDFs (encryption, form fields, scans,
ligatures, repeated headers, timing) and a `--compare` mode against
pypdfium2/pdfminer.six when those are on PYTHONPATH; it prints
statistics and short excerpts only.

**Two real problems found by testing, not by inspection.** (1) The
first AES fixtures came back as "damaged" instead of "password-
protected" in 3 of 4 cases. Only AES-128 with an open password was
caught (pypdf's `decrypt("")` reports NOT_DECRYPTED). With no crypto
package installed, pypdf raises its `DependencyError` from two other
places depending on the variant — the constructor for AES-256, and only
later, inside `extract_text()`, for AES-128 with just an owner
password — and the first version caught neither. Fixed by catching it
around the whole read, and by calling it "password-protected" only when
the message names AES: the same exception class is also raised for
other missing optional pieces (e.g. JBIG2 images), and those must stay
"damaged/unsupported".
(2) The first "does parsing block the server?" test passed for the wrong
reason: its clock started only after the blocked event loop had
resumed, so a blocked server looked fast. Replaced with a deterministic
test — a stubbed parser that can finish early only if the loop keeps
serving another request meanwhile — which the mutation pass below
confirms fails when the threadpool is removed.

**Tests: 126 → 138 → 220.** The last commit's suite has 126 tests. When
PDF work began the working tree stood at 138 — those 126 plus 12 tests
added since for the rule-based `found` flag on date fallbacks and one
report-type-detection fix, uncommitted and not yet written up in these
docs. It now stands at **220 passed plus 2 expected xfails** (about 4
seconds; no database, server or network needed; runs from `backend/`,
the repo root or `backend/tests`): 84 new tests — 53 added to
`test_document_parsing.py` (now 60), 12 in the new
`test_pdf_static_fixtures.py`, 19 in the new
`test_parse_document_endpoint.py`. They cover what comes out of a PDF
(page order and joining, repeated letterheads kept, no unwrapping); 17
text clean-up cases; every failure mode with its exact message; every
limit at its boundary for every format; corrupt DOCX; the endpoint's
status codes and messages, CORS headers on error responses (so the
browser can read the message), the bounded read and the non-blocking
parse; PDF text detected as the same report type as the same text
pasted (all three types, with a term straddling a line break); and the
realistic Edge-printed report (section order, form-table rows one per
line, dates and units, no leftover ligature or invisible characters).
The approved limits (D3) and message wording (D6) are pinned in tests,
so changing either is a deliberate act.

Whether the tests actually bite was checked, not assumed: 24 deliberate
breaks — a limit boundary flipped, the threadpool removed, the
unbounded read restored, 413/422/415 remapped to 400, individual
clean-up rules removed, the header and encryption checks removed, the
CORS origin changed, a message reworded, and others — were applied one
at a time to a scratch copy of `app/` (never the repo). Every one was
caught by at least one test, and the unmodified copy was clean. The
harness was not kept in the repo. This pass is also why the limits and
wording are pinned: it showed both could change silently.

Two tests are strict xfails, marking limits accepted under D5:
soft-hyphenated words come out split, and a hyphenated compound wrapped
at a line end stays split. They go red the day something fixes either —
the reminder to remove the marker, update this note and, for the first,
revisit D1. Three tiny AES fixtures are committed as static files
because pypdf cannot WRITE AES without the crypto package this project
deliberately doesn't ship; regeneration steps are in
`backend/tests/fixtures/README.md`. The owner-only AES test skips itself
if a crypto package is ever installed, since such files then become
readable.

**A finding that corrected an earlier note: the "stalling" large
uploads.** During M1, intermittent stalls on 9-11 MB test uploads —
including against a plain read-everything control endpoint — were put
down to the local environment. That was wrong. The cause, found when
M3's first 10 MB endpoint test took 21 seconds: `python-multipart`
0.0.9 parses the upload before our endpoint runs, and its boundary
search drops to a byte-by-byte Python loop (about 2 s per MB) whenever
the payload's bytes also occur in the random hex boundary the client
chose (0-9, a-f, dash, CR, LF). The test payloads were runs of `0`/`a`,
and a random boundary contains such a character in roughly 87% of
requests, so most were slow and a few fast, which looked intermittent.
Confirmed by holding size and code fixed and changing only the
payload/boundary pairing: 0.01-0.02 seconds against 2.1-2.4 seconds.
Realistic content is not affected: random/compressed bytes and a
text-heavy PDF structure repeated to 4 MB parsed at 0.01-0.05 s per MB.
The behavior pre-dates PDF support (same parser for DOCX/TXT), was not
changed and needs no action; the 413 test uses a `z`-filled payload, a
byte that never occurs in a boundary, so it runs in 0.1 s. Worth
knowing: the 10 MB limit (D3) is applied by our code AFTER the framework
has received and parsed the whole upload — it bounds what is read and
processed, not what is accepted. A front-door limit (proxy or
Content-Length check) or a newer python-multipart would be separate
decisions; none was made here.

**Recorded for the later accuracy-testing step.** Not addressed now,
and none of it measured on the 60 test PDFs, which contain none of these
situations.
1. Browser-printed PDFs and the M/D/YY vs D/M/YY date risk. The default
   print-to-PDF of Chromium-based browsers (verified with Edge) stamps a
   header and footer on every page — on this machine, in the en-US
   locale, `9/21/26, 9:19 AM <page title>` and `file:///... 1/3` — and
   they land in the extracted text at every page boundary (shown on a
   default-print of the synthetic fixture; the committed fixture is
   printed WITHOUT them, so it does not exercise this). The date rules
   read slash dates DAY-first (D/M/YYYY, D/M/YY) and `extract_first_date`
   tries patterns in a fixed order — ISO, then slash forms, then
   month-name forms — returning the first PATTERN that matches anywhere,
   not the earliest date by position. So a stamp printed on the 1st-12th
   of a month, such as `9/3/26`, is read as 9 March 2026 and outranks a
   correct body date written "September 3, 2026" (shown directly on the
   function: 2026-09-03 without the stamp, 2026-03-09 with it). A stamp
   whose second number is above 12, as on the 21st, cannot parse
   day-first, so it yields no wrong date — but as the first slash-shaped
   match it hides a later valid slash date such as `15/6/26` (the rule
   returns nothing and the date falls back to today's, which the
   `found: false` flag does mark); a month-name body date still parses.
   The exposed fields are the two that read the whole text — Notifiable
   Disease's `report_date` and Immunization's `administration_date`;
   onset, specimen and result dates use keyword-anchored windows, though
   an onset stated as a duration ("x12d") is computed from `report_date`
   and inherits the error. Because a stamp that DOES parse counts as a
   genuinely found date, the `found: false` fallback flag does not fire
   for it: the reviewer sees a filled date with no warning. The same
   fixed pattern order returns 2026-09-04 (an ISO date
   later in the body) on the CLEAN fixture although "September 3, 2026"
   comes first — harmless on the 500 synthetic reports, which use one
   format each, but relevant to real narrative reports with mixed
   formats. Options to weigh then, none decided: strip print-stamp lines,
   prefer position over pattern order, or tell users to print without
   headers and footers.
2. Partly scanned PDFs pass silently. Only a PDF with NO text layer at
   all is refused. A PDF that mixes typed and scanned pages is read from
   its typed pages and returned with no warning that the scanned pages
   contributed nothing, so the reviewer sees a plausible but incomplete
   text, and fields that lived on those pages come back empty or
   low-confidence. A test records this as current behavior
   (`test_partly_scanned_pdf_returns_only_the_text_it_has`). Options to
   weigh then: detect a text-less page and warn, or add OCR.
3. Text-level limits accepted under D5 (the two strict-xfail tests):
   soft-hyphenated words split ("influ enza"), and a hyphenated compound
   wrapped at a line end stays split. The second has a concrete
   consequence: `9-year-` / `old` on two lines is NOT read by the age
   rule (no age, against 9 for the same sentence on one line; a wrap
   after "year" with no hyphen reads fine). Repeated letterheads and
   footers are also kept, by design.
4. Not tested at all: Arabic and other right-to-left or non-Latin-script
   PDFs; producers other than ReportLab and Edge (Word "Save as PDF",
   LibreOffice, scanners with an OCR text layer); multi-column layouts.

**What is verified, and what is not.** Verified: the 220-test suite and
the mutation pass (both in this machine's `venv_recovery` only); real
HTTP requests against the running local backend during M1; for M2, the
real `index.html`/`app.js`/`style.css` driven in headless Edge against
the real backend with the save endpoint blocked — both flows accepted a
valid PDF and displayed the backend's messages for files that failed;
and, CONFIRMED by Dr. Sameh directly in his own Chrome on 2026-09-21,
PDF upload working correctly in both Single report and Batch upload,
real file-picker filtering included. NOT verified: PDF upload on Render
(`render.yaml` builds from `requirements.txt`, so `pypdf` should arrive
with the next deploy, but no deploy or test was run); field-level
accuracy on any PDF (extraction and detect-type were deliberately not
run on the 60 test PDFs); anything listed under item 4 above; Python
versions other than the project's 3.10.11 environment.

PDF upload is now IMPLEMENTED as ingestion only: text-layer PDFs go
through the same detect → extract → review → save path as DOCX/TXT and
nothing downstream changed. Own-browser confirmation: CONFIRMED
(2026-09-21). OCR, CSV upload and PDF accuracy testing are not built or
run.
