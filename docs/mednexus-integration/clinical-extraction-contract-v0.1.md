# MEDNEXUS CLINICAL EXTRACTION CONTRACT
## Version 0.1
## Scope: PROTECT/UNDERSTAND → Domain Extractor → Human Review → STANDARDIZE
## Status: DRAFT — ratified architectural decisions, no implementation yet

This contract governs what a domain extractor (Public Health's three
extraction services today; MedNexus Main's future Pathology/Emergency/
etc. extractors) receives as input, what it is responsible for
producing, and what it must NOT do. Reference implementations: MedNexus
Public Health's Notifiable Disease / Immunization / Laboratory
extractors (the only working EXTRACT implementations that exist today
in either project).

---

## 1. The Protected Execution Envelope (Decision 4)

PROTECT is a **policy gate**, not a destructive redaction step applied
unconditionally before EXTRACT ever runs. The contract:

```
UNDERSTAND
    ↓  MedNexusDocumentContext  (Semantic Context Contract v0.1)
PROTECT
    ↓  policy decision, not necessarily text mutation
ProtectionContext / Access Decision
    ↓
EXTRACT   ← runs INSIDE this governed execution boundary
```

**Input to EXTRACT:**
```python
@dataclass(frozen=True, slots=True)
class ExtractionInput:
    document_context: MedNexusDocumentContext   # from UNDERSTAND
    protection_context: ProtectionContext        # from PROTECT — see below
    protected_text: str                          # PROTECT's output text (may equal raw_text — see raw_text_access)
    raw_text_access: RawTextAccess                # ALLOWED | DENIED | RESTRICTED
    raw_text: str | None                          # present only if raw_text_access is ALLOWED or RESTRICTED
```

```python
class RawTextAccess(str, Enum):
    ALLOWED = "ALLOWED"        # extractor may read raw_text in full — e.g. a trusted, locally-running extractor under a population-analytics policy
    DENIED = "DENIED"          # extractor must work only from protected_text
    RESTRICTED = "RESTRICTED"  # extractor may read raw_text for specific field types only — see ProtectionContext.field_access_rules

@dataclass(frozen=True, slots=True)
class ProtectionContext:
    policy_profile: str                                    # e.g. "mednexus_analytics_public_health"
    raw_text_access: RawTextAccess
    field_access_rules: dict[str, RawTextAccess] = field(default_factory=dict)  # per-field override under RESTRICTED
    date_role_policy: dict[DateRole, str] = field(default_factory=dict)          # KEEP/REMOVE/GENERALIZE per DateRole, see Semantic Context Contract Section 5
```

**Why this shape, not "EXTRACT gets protected_text, full stop"**: a
trusted extractor running inside MedNexus's own controlled environment
(true today of Public Health's local GLiNER/OpenMed pipeline — no
report text is ever sent to an external API) can be explicitly granted
`raw_text_access = ALLOWED` under a population-analytics policy
specifically because clinically necessary fields (exact patient age,
exact dates, facility name) would otherwise be destroyed by a naive
redaction pass, breaking extraction accuracy for no privacy benefit
(these fields are legitimately needed downstream and are governed on
the way OUT, not blocked on the way in). A stricter policy profile
(e.g. `mednexus_strict_privacy`) would instead set `raw_text_access =
DENIED`, forcing the extractor to work only from `protected_text`. The
policy decides; the extractor obeys whatever it's handed — it never
makes its own privacy judgment.

**Output governance**: regardless of `raw_text_access`, whatever
EXTRACT produces (Section 2 below) and whatever gets persisted is still
subject to the same `policy_profile`'s rules on the way out — e.g. a
`patient=REPLACE` rule still applies to any patient-identifying value
in the extraction OUTPUT even if the extractor had `raw_text_access =
ALLOWED` on the way in. Access-in and governance-out are separate
enforcement points.

## 2. Extraction Output Shape (generalized from Public Health today)

```python
@dataclass(frozen=True, slots=True)
class ExtractedFieldConfidence:
    source: Literal["model", "gazetteer", "rule_based"]
    score: float | None
    found: bool | None = None   # gazetteer fields only

@dataclass(frozen=True, slots=True)
class ClinicalExtractionResult:
    domain: DocumentDomain                              # carried through from UNDERSTAND, not re-decided by EXTRACT
    fields: dict[str, Any]                               # domain-specific — see Section 4 for the 3 Public Health shapes
    field_confidence: dict[str, ExtractedFieldConfidence]
    source_excerpt: str
    extraction_review_required: bool                     # canonical MedNexus Seven contract name — see Semantic Context Contract Section 4 for the naming migration note and how this combines with document_review_required
    provenance: ExtractionProvenance                     # extractor identity/version, for audit
```

This is a direct generalization of Public Health's existing
`{fields..., source_excerpt, confidence, needed_review}` shape — no
Public Health behavior changes; the field names above are the
contract-level (MedNexus-wide) names, and Public Health's existing
JSON keys can map onto them without altering its own database schema.

## 3. What EXTRACT Owns (unchanged — this contract does not ask Public Health to give this up)

- All field-level entity recognition: model-based (GLiNER/similar),
  gazetteer/closed-vocabulary matching, and rule-based/regex extraction.
  This is EXTRACT's job in every domain, never UNDERSTAND's — see
  Semantic Context Contract Section 3's hard rule on `_hint`/`_concept`
  fields.
- Per-field confidence scoring and the `extraction_review_required`
  decision.
- The human review gate before persistence — remains mandatory, no
  extractor implementation may bypass it, in any domain.

**Hard rule: EXTRACT MUST remain terminology-independent.** Terminology
code mapping (ICD-10, LOINC, SNOMED CT, RadLex, CVX, UCUM, or any other
coding system) is explicitly OUT OF SCOPE for EXTRACT and belongs
entirely to STANDARDIZE (Section 5 below) — this is the authoritative
MedNexus Seven boundary: EXTRACT produces clinical facts/entities/
observations with provenance and field confidence; STANDARDIZE maps
those facts to terminology systems. A terminology mapping error or gap
must never alter extraction recognition or extraction confidence —
these are different stages with different failure modes, and conflating
them would make a coding-system limitation look like an extraction
defect, or vice versa.

## 4. What EXTRACT Should Retire, Once UNDERSTAND Exists Upstream

Public Health's `report_type_detection.py` becomes redundant once
`document_context.identity.document_type` (from UNDERSTAND) is
available and trustworthy. Concretely: `ClinicalExtractionResult.domain`
above is populated FROM `document_context.identity`, not re-derived by
EXTRACT. This is a genuine simplification, not just a theoretical
convergence point — once the UNDERSTAND → EXTRACT handoff exists for
real, `report_type_detection.py` can be deleted and EXTRACT's dispatcher
becomes a simple lookup on `document_context.identity.document_type`
rather than its own classifier.

## 5. Handoff to STANDARDIZE

`ClinicalExtractionResult.fields` is what STANDARDIZE consumes, and
STANDARDIZE — not EXTRACT — owns everything from this point onward in
this section.

Public Health's current save-time ICD-10/LOINC lookup (a terminology
lookup file, e.g. `icd10_codes.json`, `loinc_codes.json`, keyed by the
already-extracted field value, consulted only at save time, kept
structurally separate from extraction-time gazetteer matching) is best
understood as the **existing practical precursor / reference
implementation of the STANDARDIZE boundary** — built before this
contract formalized EXTRACT/STANDARDIZE as distinct MedNexus Seven
stages, but already shaped correctly: it runs strictly after extraction
recognition is complete, and a mapping gap in it (e.g. Poliovirus Stool
PCR's rejected LOINC match) has never once altered what was recognized
or how confident the recognition was. This is exactly the isolation the
hard rule in Section 3 requires, demonstrated in production rather than
just specified. The LOINC mapping-status taxonomy (`EXACT`,
`ACCEPTABLE_GENERIC_SPECIMEN`, `ACCEPTABLE_GENUS_LEVEL`, `PROXY`,
`COMPOSITE`, `NO_DIRECT_LOINC`, `REJECTED_MISMATCH`) is offered as a
candidate general-purpose STATUS model for any future MedNexus
STANDARDIZE mapping, not just LOINC.

## 6. Reference Field Shapes (Public Health's three domains, unchanged from production today)

Shown here only to demonstrate `fields: dict[str, Any]` is domain-typed
in practice, not actually a loose dict at the Public-Health-schema
level (Public Health's own Pydantic schemas remain the source of truth;
this is illustrative):

**`PUBLIC_HEALTH` domain, Notifiable Disease subtype**: `disease_name`,
`diagnosis_status`, `report_date`, `onset_date`, `patient_age`,
`patient_sex`, `region`, `facility_name`, `lab_confirmed`.

**`IMMUNIZATION` domain**: `vaccine_name`, `dose_number`,
`administration_date`, `route`, `patient_age`, `patient_age_months`,
`region`, `facility_name`, `adverse_event_reported`,
`adverse_event_severity`, `adverse_event_description`.

**`LABORATORY` domain**: `test_name`, `specimen_type`, `result`,
`pathogen_identified`, `specimen_collection_date`, `result_date`,
`patient_age`, `region`, `facility_name`.

## 7. What This Contract Explicitly Does NOT Cover

- The PROTECT policy engine's internal rule evaluation — this contract
  only specifies what EXTRACT receives as the RESULT of that
  evaluation (`ProtectionContext`), not how PROTECT computes it.
- ANALYZE/VISUALIZE/INDICATORS — unaffected; they consume persisted
  records exactly as Public Health already produces them.
- Any UI/review-workflow design — `extraction_review_required` is a
  signal this contract defines the meaning of, not a screen design.
