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
