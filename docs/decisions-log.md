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

