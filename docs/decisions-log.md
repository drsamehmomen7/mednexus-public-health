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

