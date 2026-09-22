# MEDNEXUS — DOMAIN INTELLIGENCE TRACK (TRACK B) ROADMAP
## Response to: Parallel Domain Development Plan
## Status: 16 August 2026 — Roadmap for review, no implementation yet

This is a planning document only, per instruction. It answers A-H in
order.

---

## A. Remaining Work to Finish the Public Health Vertical

Grouped by whether it blocks the "stable domain checkpoint" (Section B)
or is legitimately beyond it.

**In progress / near-term (blocks checkpoint):**
1. Verify the LOINC lookup end-to-end against a real save (test cases
   already prepared — a known-code case and a deliberately-null case —
   not yet confirmed run).
2. Vaccine terminology codes (CVX) for the 12 vaccines — third and
   final terminology domain, same separated-lookup pattern as ICD-10/
   LOINC.
3. pytest coverage for the code that postdates the 126-test baseline:
   `indicators.py`, `load_icd10_lookup()`, `load_loinc_lookup()`,
   `/indicators/dashboard-data`.
4. First tagged GitHub release (`v0.1.0`), reflecting the state once
   1-3 above land.

**Explicitly OUT of the checkpoint — real, tracked, but not blocking:**
- PDF/CSV document ingestion.
- Syndromic and Outbreak report types.
- Deployed frontend (currently local-only).
- Lower-priority extraction fields (Notifiable Disease's
  occupation/travel_related/travel_country/vaccination_status/outcome;
  Immunization's lot_number).
- The three documented schema gaps needing multi-observation support
  per lab test (GeneXpert MTB/RIF, Lyme Two-Tier Serology, Typhoid
  Widal Test).
- Q fever Phase I serology components.
- Real-world (non-synthetic) validation of the extraction pipeline.

Reasoning for the split: items 1-4 complete work already fully in
motion and close every open loop from the current terminology-
normalization effort. The "OUT" items are each legitimate future work
but are not required to call the current three-report-type + Indicators
vertical stable — bundling them in would make "stable checkpoint" an
ever-receding target, which defeats the purpose of having one.

## B. Definition of "Stable Domain Checkpoint"

A Public Health domain checkpoint is reached when:
1. All three report types (Notifiable Disease, Immunization,
   Laboratory) are extraction-complete and measured (already true).
2. The Indicators layer is complete and verified (already true).
3. All terminology domains applicable to Public Health's current scope
   are complete: ICD-10 (done), LOINC (done), CVX (pending — Section A
   item 2).
4. Every terminology/indicator addition since the 126-test baseline has
   its own test coverage (Section A item 3) — the project's own
   "measured, not assumed" standard applied to itself.
5. `CURRENT_STATUS.md` and `docs/decisions-log.md` are current as of
   the checkpoint, and a GitHub release tag exists marking it.

This is deliberately a **scope checkpoint**, not a **maturity
checkpoint** — it does not require real-world validation, deployment,
or additional report types. Those remain open, tracked, non-blocking
work (Section A, "OUT" list), consistent with treating "finish Public
Health" as a scope boundary rather than an unreachable moving target.

## C. Proposed Order for Next Domain Verticals

Agree with the proposed order (Laboratory → Pathology → Radiology),
with reasoning specific to each:

**1. Laboratory — first, and substantially reused, not started fresh.**
This needs an important framing correction, carried over from the
Crosswalk: Public Health's existing "Laboratory" report type is not a
Public-Health-specific artifact that needs a parallel, separate
LABORATORY-domain implementation — per the frozen boundary (Crosswalk
v1.1, Decision 1 / frozen responsibility #7), a laboratory document is
natively a `LABORATORY` document whether or not its downstream use is
public-health analytics. Concretely: Public Health's existing
`laboratory_extraction.py`, the 71-test gazetteer, and the full LOINC
mapping (with its 7-status taxonomy) are not a prototype to be
rebuilt for a "real" Laboratory vertical — they are already most of
one. The Laboratory vertical's real remaining work is generalizing this
existing implementation to the `ClinicalExtractionResult`/STANDARDIZE
contract shape (Crosswalk Sections 6-7) rather than building new domain
intelligence from nothing. This is the lowest-effort, highest-confidence
next vertical, and a natural first proof that the frozen contracts work
in practice with a real (not hypothetical) implementation.

**2. Pathology — second, genuinely new domain intelligence.**
No Public Health precedent exists for Pathology extraction. Worth
noting: MedNexus Main's UNDERSTAND layer already has Pathology
recognition signals defined (`understanding/profiles.py`: "pathology
report", "histopathology", "gross description", "microscopic
description", "final diagnosis", "immunohistochemistry", "specimen",
"margins" — confirmed in code, not assumed), so UNDERSTAND-side document
classification for Pathology is further along than EXTRACT-side field
recognition. This vertical will need its own gazetteer/rule-based/model
hybrid built from scratch, following Public Health's established
pattern (Section E), but with entirely new domain vocabulary.

**3. Radiology — third, downstream side only, deliberately sequenced
after Track A's UNDERSTAND deepening.**
Track A is actively enriching Radiology's UNDERSTAND stage in parallel.
Sequencing Radiology's EXTRACT/STANDARDIZE/ANALYZE/VISUALIZE/INDICATORS
third (not first, despite Radiology being MedNexus Main's most mature
domain) means Track B's Radiology work begins once Track A's richer
`RadiologyClinicalContext` (Semantic Context Contract v0.1, Section 3)
is more likely to already exist, reducing the chance of building
Radiology EXTRACT against a UNDERSTAND shape that changes underneath
it. This is a sequencing choice to reduce rework risk, not a statement
that Radiology is lower priority.

## D. Per-Domain Breakdown (EXTRACT / STANDARDIZE / ANALYZE / VISUALIZE / INDICATORS)

**Laboratory** (mostly already exists, per Section C):
- EXTRACT: reuse `laboratory_extraction.py`'s hybrid pattern as-is;
  generalize its report-type-detection dependency once
  `document_context.identity.document_type` is available (Extraction
  Contract v0.1, Section 4) — not blocking, see Section G below.
- STANDARDIZE: reuse `loinc_codes.json` and the mapping-status taxonomy
  directly; extend to non-Public-Health lab tests as they arise.
- ANALYZE/VISUALIZE: reuse the existing Laboratory dashboard's query
  patterns; likely needs generalizing beyond the current
  notifiable-disease-linked 71-test list to a broader/general lab test
  catalog if this vertical is meant to serve laboratories outside
  public-health surveillance.
- INDICATORS: `test_positivity_by_region` generalizes directly; new
  indicators (e.g. turnaround time, panel completion rate) are a
  reasonable general-Laboratory addition beyond Public Health's current
  scope.

**Pathology** (new):
- EXTRACT: new hybrid extractor — gazetteer candidates likely include
  specimen types, diagnosis terminology, margin-status vocabulary;
  rule-based fields likely include dates, specimen counts; model
  (GLiNER/OpenMed) handles free-text diagnosis narrative, following
  Public Health's exact three-mechanism split (Section E).
- STANDARDIZE: SNOMED CT is the natural terminology fit for pathology
  diagnoses (not currently active in either project — first real test
  of whether/how SNOMED CT gets activated).
- ANALYZE/VISUALIZE/INDICATORS: new; no direct Public Health precedent,
  though the dashboard/indicator UI patterns (filter row, summary
  cards, Chart.js breakdowns) transfer directly as a visual/structural
  template.

**Radiology** (downstream side only — UNDERSTAND is Track A's):
- EXTRACT: first real field-level Radiology extractor (today's
  UNDERSTAND stops at document-level classification, not findings/
  measurements/lesions per the MedNexus handoff's own Section 18
  example). This is new work for Track B, consuming whatever
  `RadiologyClinicalContext` Track A has built by the time this starts.
- STANDARDIZE: RadLex (already an active reference in MedNexus Main)
  plus LOINC (already active for Radiology in MedNexus Main) — this
  vertical inherits more STANDARDIZE groundwork from Track A than
  Laboratory or Pathology do.
- ANALYZE/VISUALIZE/INDICATORS: new; same transferable UI/dashboard
  pattern as above.

## E. Reusable Patterns vs. Public-Health-Specific

**Reusable across all future domains** (already identified in the
Authoritative Handoff, Section X, restated here as directly applicable
to Track B's next three verticals):
- The three-mechanism extraction split (model / gazetteer / rule-based)
  per field, chosen per field based on which mechanism fits best.
- Per-field `{source, score, needs_review}` confidence, rolling up to a
  record-level `extraction_review_required`.
- Mandatory human review before persistence, no exceptions, no bypass
  path.
- The separated-lookup STANDARDIZE pattern (terminology mapping as a
  file/service consulted strictly after extraction, never interleaved)
  — now formally required by the Extraction Contract's terminology-
  independence rule, not just a Public Health convention.
- The mapping-status taxonomy (EXACT / ACCEPTABLE_GENERIC_SPECIMEN /
  ACCEPTABLE_GENUS_LEVEL / PROXY / COMPOSITE / NO_DIRECT_LOINC /
  REJECTED_MISMATCH) as a general STANDARDIZE status model, not LOINC-
  specific.
- Dashboard/indicator visual structure (filter row → summary cards →
  charts → export) as a UI template, independent of domain content.
- The documentation discipline itself: living CURRENT_STATUS-equivalent
  doc + decisions log per domain, honest measured-vs-assumed accuracy
  reporting.

**Must remain domain-specific, not generalized:**
- Gazetteer/terminology CONTENT (disease names, lab tests, vaccines,
  and their code mappings) — each domain's vocabulary is a fresh
  clinical-review exercise, not a template to copy values from.
- Specific rule-based regex patterns — tuned per domain's typical
  report phrasing.
- Specific indicator formulas and denominators — domain-dependent by
  definition.
- `population_strata`-style reference/denominator data — Public
  Health's regional population figures do not generalize to Laboratory
  turnaround-time or Pathology case-volume indicators, which will need
  their own denominators if any.

## F. Milestone Boundaries — Proceeding Without Waiting on Track A

Track B does not need any Track A deliverable to continue through the
Laboratory and Pathology verticals' EXTRACT/STANDARDIZE work:
- Extraction today runs directly against raw/pasted/uploaded text, with
  Track B's own lightweight report-type detection, exactly as Public
  Health already operates. This continues to work unmodified whether or
  not Track A's UNDERSTAND stage exists yet — it is not a dependency,
  only a future optional upgrade (Section G).
- STANDARDIZE work (terminology mapping) has no dependency on Track A
  at all — it consumes EXTRACT's output, which Track B fully owns.
- ANALYZE/VISUALIZE/INDICATORS have no dependency on Track A — Track A
  has no persistence layer to depend on (Crosswalk Section 2).

The one place Track A's pace genuinely matters is the Radiology
vertical specifically (Section C, item 3) — sequenced third partly
*because* it benefits from Track A's progress, not because it is
blocked by it in a hard sense. If Track A's Radiology UNDERSTAND work
is slower than expected, Track B could still begin Radiology EXTRACT
against today's existing (thinner) Radiology understanding output
rather than wait — this would just mean redoing some of Track B's own
Radiology context-gathering that a richer UNDERSTAND would otherwise
have supplied. Not a hard blocker, a quality/rework tradeoff.

## G. First Point Requiring an Implemented Contract from Track A

Two distinct trigger points, of different urgency:

1. **Non-blocking, optional, whenever convenient**: retiring Track B's
   own report-type detection (`report_type_detection.py` today,
   equivalent logic in future Laboratory/Pathology verticals) in favor
   of trusting `document_context.identity.document_type` from a real
   UNDERSTAND implementation. This is a simplification opportunity
   (Extraction Contract v0.1, Section 4), not a requirement — Track B's
   own detection continues to work indefinitely if Track A isn't ready.

2. **Blocking, hard requirement**: the first time REAL (non-synthetic)
   patient data is introduced to any Track B domain. At that point, an
   actual implemented `ProtectionContext` / Protected Execution
   Envelope from Track A is required before that data may be processed
   — this is not a technical nicety, it is the standing governance
   decision already on record (no real PHI on the current
   infrastructure without a resolved PROTECT stage and a separate
   Ministry-level infrastructure decision). This is the genuine hard
   dependency point, and it is data-triggered, not calendar-triggered —
   it could arrive whenever the first real-data conversation happens,
   independent of which vertical Track B is working on at the time.

Until trigger 2 occurs, Track B has no hard dependency on Track A's
delivery pace.

## H. Frontend / Deployment Strategy

Confirmed alignment with the directive to keep frontends separate now.
Concrete execution for Track B:

- Each domain vertical (Laboratory, Pathology, Radiology, and Public
  Health's existing four pages) gets its own dashboard page(s) within
  Public Health's existing static-site pattern (shared `style.css`
  brand system, no framework, no build step) — consistent look, no
  premature unification.
- Continue using the existing Render Postgres deployment for synthetic/
  development data across new verticals, per the directive — not
  reinterpreted as the permanent real-data home for any future domain.
- Deploying the frontend as a Render Static Site (previously discussed,
  not yet done) remains a reasonable near-term improvement independent
  of domain expansion — makes demos shareable without a two-terminal
  local setup — but is not required before starting Laboratory/
  Pathology work.
- Compatibility with a future unified MedNexus portal: keep each
  domain's dashboard pages independently linkable (stable URLs, no
  assumptions that break if embedded via iframe or linked from an
  external shell) and keep each domain's API namespaced by report/
  domain type (already true of Public Health's `/reports/{type}/...`
  pattern) — this costs nothing now and avoids a forced rewrite if/when
  a MedNexus portal shell is built later.
