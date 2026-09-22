# MEDNEXUS ARCHITECTURE CROSSWALK — v1.1
## MedNexus Main ↔ MedNexus Public Health ↔ Unified Target Architecture
## Status: 16 August 2026 — Decisions ratified, pre-code

**Supersession notice**: this revision adopts **MedNexus Seven** as the
authoritative journey. INGEST is no longer an independent stage; it is
absorbed into UNDERSTAND. All prior 8-stage wording (including in the
v1.0 crosswalk and the original MedNexus handoff) is historical.

```
MEDNEXUS SEVEN
01 UNDERSTAND   (includes ingestion / document input handling)
02 PROTECT
03 EXTRACT
04 STANDARDIZE
05 ANALYZE
06 VISUALIZE
07 INDICATORS
```

---

## RATIFIED DECISIONS (this session)

These five points were decided by Dr. Sameh in response to crosswalk
v1.0 and are now the architectural baseline. Nothing below is open for
re-litigation except where explicitly marked.

### Decision 0 (correction to v1.0): review flags stay two-layer, not one boolean

`ProcessingContext.manual_review_required` (MedNexus, document/process-
level: "does this document as a whole need review?") and Public
Health's `needed_review` (field/record-level: "does this specific
extracted record need review?") are DIFFERENT questions at different
layers, not the same boolean independently invented twice. They must
keep separate provenance. A future unified UI MAY compute
`review_required = document_review OR extraction_review`, but the
underlying signals stay distinct and separately inspectable.

### Decision 1: Domain taxonomy — RATIFIED

- Notifiable Disease / Surveillance Notification → `PUBLIC_HEALTH`
  (kept narrow: surveillance/notification/outbreak/epidemiological
  documents only — Syndromic and Outbreak will likely become subtypes
  under this domain later, not siblings).
- Patient Laboratory Report → `LABORATORY` (existing domain, unchanged).
- Immunization Record/Report → **new independent domain `IMMUNIZATION`**,
  not a `PUBLIC_HEALTH` subtype. Rationale (Dr. Sameh): vaccination is
  an independent clinical activity — its own procedures, products,
  doses, schedules, administration routes, AEFI (adverse events
  following immunization), and standards — not merely a surveillance
  document, and may in the future originate from clinical systems
  entirely separate from public-health notification.

**Correction to v1.0's framing, also ratified**: "MedNexus Public
Health" (the product/project) is NOT the same thing as
`DocumentDomain.PUBLIC_HEALTH` (the enum value). The Public Health
project is an **application domain** that receives documents from
multiple native clinical domains (`PUBLIC_HEALTH`, `LABORATORY`,
`IMMUNIZATION`). Downstream purpose (this document will be used for
public-health analytics) does not change a document's native identity
(what kind of document it actually is). This distinction matters
throughout Section 6/7 below.

### Decision 2: `ClinicalContext` — Option B, disciplined — RATIFIED

`attributes: dict[str, Any]` is an escape hatch only, never the primary
contract mechanism — an untyped dict as the main carrier would
regress into an undocumented key-soup after a few more domains.
Adopted shape (Section 2 below has the full spec): a small generic core
plus a closed set of typed domain-extension objects, one per
`DocumentDomain`. Migration constraint: existing Radiology behavior
(780 passing tests) must not regress in one breaking change — the
extension objects are additive, `RadiologyClinicalContext` preserves
today's fields exactly.

### Decision 3: Dates — semantically typed privacy entities, not blanket KEEP/REMOVE — RATIFIED

Rejected: a single `encounter_date` policy action applied uniformly.
Ratified: dates become their own semantically-typed privacy entity
class, distinct from each other by **role**, not just by field name:
`event_date` (encounter/onset), `report_date`, `specimen_collection_date`,
`result_date`, `administration_date`, `birth_date`. Each gets its own
policy action per profile: `KEEP`, `REMOVE`, `GENERALIZE` (to week/
month/year), or (future, not implemented now) `SHIFT`/pseudonymize.
**`MEDNEXUS_ANALYTICS_PUBLIC_HEALTH`'s current blanket
`encounter_date=REMOVE` rule is explicitly NOT production-approved**
until this typed-date model exists and the profile is rewritten against
it. The existing profile's concept (population-analytics purpose,
`organization=KEEP`, `location=KEEP`, `patient=REPLACE`) remains
approved; only the date rule is blocked pending this work.

### Decision 4: PROTECT is a policy gate, not a destructive redaction step — RATIFIED

Rejected: "EXTRACT receives `protected_text`" as the whole contract —
this would make PROTECT a destructive upstream processor and risks
breaking extraction of dates, ages, and other clinically necessary
values. Ratified architecture:

```
UNDERSTAND
    ↓
PROTECT  (policy decision, not necessarily redaction)
    ↓
ProtectionContext / Access Decision
    ↓
EXTRACT   — runs inside a governed execution boundary
```

Working name for the concept: **MedNexus Protected Execution
Envelope** — an architectural contract, not a new feature to build now.
EXTRACT receives `document_context`, `protection_context`,
`protected_text`, AND a `raw_text_access` decision
(`ALLOWED | DENIED | RESTRICTED`) made by PROTECT. A trusted, locally-
running extractor (like Public Health's today) may be granted raw-text
access by policy specifically to extract clinically necessary fields
(age, dates, facility, clinical values) that a naive redaction pass
would have destroyed — but whatever EXTRACT subsequently outputs or
persists is still governed by policy constraints on the way out. This
is "protect the decision about processing," not "destroy the data
before processing."

### Observation 5 (not a decision — recorded for context)

Public Health is the first evidence that the MedNexus Seven journey is
not aspirational: MedNexus Main already has a strong/rich UNDERSTAND
foundation plus an accepted, frozen PROTECT foundation (Phase 1
Clinical Privacy Policy Engine), while Public Health is strong at
EXTRACT → STANDARDIZE → ANALYZE → VISUALIZE → INDICATORS. These are
complementary halves of one product
shape, not two unrelated projects awaiting a conventional merge. Public
Health should be treated as the **first vertical reference
implementation** of the MedNexus Seven downstream journey — Radiology
is the first rich UNDERSTAND implementation; together they are the two
reference points the formal contracts (below) are being written
against.

---

## 1. STAGE-BY-STAGE CROSSWALK (updated to MedNexus Seven)

| Stage | MedNexus Main | MedNexus Public Health | Gap / Overlap |
|---|---|---|---|
| UNDERSTAND (incl. ingestion) | Full: `ExtractorFactory`/`ExtractorRegistry` (DOCX/TXT/PDF), `MedNexusDocumentContext` — domain/type/subtype classification, section detection, language detection, clinical context, provenance, routing | Partial: DOCX/TXT parsing only, inline report-type detection with no richer semantic context, no section detection, no provenance object | Main strictly ahead. Primary integration surface — see Sections 6/7 (contracts) below. |
| PROTECT | Full: Clinical Privacy Policy Engine, 4 purpose-based profiles (one already public-health-shaped), frozen/accepted Phase 1 checkpoint | Does not exist. Only synthetic data ever processed. | Main strictly ahead. Confirmed integration point — Decision 3/4 above govern how. |
| EXTRACT | `DetectedEntity` schema exists; no working domain-specific field-level extractor yet beyond Radiology's document-level understanding | Full, 3 report types, hybrid GLiNER+gazetteer+rule-based, per-field confidence, mandatory human review, measured 100% accuracy on synthetic data | **Public Health strictly ahead.** Reusable pattern flows Public-Health-toward-Main here. |
| STANDARDIZE | Reference-model layer for Radiology (LOINC 2.82, RadLex 4.3, DICOM); SNOMED CT not active | ICD-10 (54/54) and LOINC (71/71, reviewed, 7-status taxonomy) done; vaccine codes not started; SNOMED CT also not active | Both independently reached the same SNOMED CT gap and the same "external terminology is reference knowledge, not authority" philosophy. Public Health's separated-lookup pattern and status taxonomy are concrete prior art. |
| ANALYZE | Does not exist — no persistence layer at all in MedNexus Main | Basic: plain SQL dashboard queries, no pre-aggregation | Public Health ahead on a thin foundation; nothing to reconcile from Main's side. |
| VISUALIZE | Demo/marketing frontend only (`/understanding`, `/privacy`) — no persisted-data dashboards | 4 dashboards, shared brand system, Chart.js | Public Health strictly ahead. |
| INDICATORS | Does not exist | 2 cross-report-type indicators implemented | Public Health strictly ahead. |

(Section 2 of crosswalk v1.0 — "MedNexus Main has no persistence layer
at all" — stands unchanged and is the reason ANALYZE/VISUALIZE/
INDICATORS have nothing on the Main side to cross-reference.)

## 2. WHERE THIS LEADS

The two formal contracts requested — **MedNexus Clinical Semantic
Context Contract v0.1** and **MedNexus Clinical Extraction Contract
v0.1** — are delivered as separate documents alongside this crosswalk.
They encode Decisions 1-4 above as the actual typed shapes UNDERSTAND,
PROTECT, and EXTRACT are expected to honor, with Public Health's three
report types and Radiology as the two reference implementations each
contract is checked against.

No implementation work follows immediately from this crosswalk. Per
Dr. Sameh's direction, the next concrete build step (separately
scoped, not started here) is enriching MedNexus's UNDERSTAND stage with
the typed domain-extension architecture and designing the PROTECT
bridge — NOT migrating Public Health's codebase into MedNexus. Public
Health and Radiology continue on their current paths without
interruption.
