# MEDNEXUS CLINICAL SEMANTIC CONTEXT CONTRACT
## Version 0.1
## Scope: what UNDERSTAND emits, consumed by PROTECT and (indirectly) EXTRACT
## Status: DRAFT — ratified architectural decisions, no implementation yet

This contract governs the output of the UNDERSTAND stage (MedNexus
Seven). It extends the existing `MedNexusDocumentContext` shape
(`understanding/context_models.py`) rather than replacing it. Every
field below is either (a) already implemented as-is, (b) an additive
extension of an existing structure, or (c) explicitly marked as a
future/not-yet-built capability. Reference implementations: Radiology
(rich UNDERSTAND, first implementation) and MedNexus Public Health's
three report types (first EXTRACT-side consumer).

---

## 1. Top-Level Shape (unchanged)

```python
@dataclass(frozen=True, slots=True)
class MedNexusDocumentContext:
    document: DocumentDescriptor
    identity: DocumentIdentityContext
    structure: tuple[SemanticSection, ...]
    clinical_context: ClinicalContext        # SEE SECTION 3 — CHANGES HERE
    privacy_context: PrivacyContext
    processing_context: ProcessingContext     # SEE SECTION 4 — CHANGES HERE
    provenance: ContextProvenance
```

## 2. Domain Taxonomy (Decision 1)

```python
class DocumentDomain(str, Enum):
    RADIOLOGY = "RADIOLOGY"
    PATHOLOGY = "PATHOLOGY"
    LABORATORY = "LABORATORY"
    EMERGENCY = "EMERGENCY"
    ADMISSION_DISCHARGE = "ADMISSION_DISCHARGE"
    PUBLIC_HEALTH = "PUBLIC_HEALTH"           # narrowed: surveillance/notification/outbreak only
    IMMUNIZATION = "IMMUNIZATION"             # NEW — independent domain, not a PUBLIC_HEALTH subtype
    UNKNOWN = "UNKNOWN"
```

`PUBLIC_HEALTH` semantics narrowed to: case notification, outbreak
investigation, epidemiological surveillance documents. Syndromic and
Outbreak report types (Public Health project, not yet built) are
expected to become `DocumentSubtype` values under `PUBLIC_HEALTH`, not
new domains.

`IMMUNIZATION` is new. Recognition signals (to be written, not part of
this contract) should key on vaccine/dose/administration-route/AEFI
vocabulary, independent of any surveillance-notification language.

`LABORATORY` is unchanged — Public Health's Laboratory report type maps
here directly, on the principle that downstream analytic purpose
(population surveillance) does not change a document's native clinical
identity (it is still, natively, a laboratory test result report).

## 3. `ClinicalContext` — Typed Domain Extensions (Decision 2)

**Generic core** (present for every document, every domain):
```python
@dataclass(frozen=True, slots=True)
class ClinicalContext:
    clinical_purpose: str | None = None
    domain_concepts: tuple[str, ...] = ()
    temporal_context: TemporalContext | None = None      # NEW, see below
    comparison_context: str | None = None                 # e.g. "compared to prior study" — generic across domains
    domain_extension: DomainClinicalContext | None = None  # SEE BELOW — the typed union
    attributes: dict[str, Any] = field(default_factory=dict)  # ESCAPE HATCH ONLY — see rule below
```

**Rule on `attributes`**: this field exists for genuinely novel,
not-yet-modeled signals during active development of a new domain. Any
key used more than once, or used by more than one domain, must be
promoted into a typed field on the relevant domain extension (or the
generic core, if it turns out to be domain-agnostic) before that
domain's UNDERSTAND implementation is considered stable. `attributes`
is not a permanent parking lot.

**`TemporalContext`** (new, generic — needed by Public Health/
Immunization/Laboratory as much as Radiology's "comparison to prior
study"):
```python
@dataclass(frozen=True, slots=True)
class TemporalContext:
    has_comparison: bool = False
    is_follow_up: bool = False
    reporting_period_hint: str | None = None   # e.g. "weekly surveillance", document-level signal only
```

**`DomainClinicalContext`** — a closed discriminated union, one variant
per `DocumentDomain`:

```python
DomainClinicalContext = (
    RadiologyClinicalContext
    | LaboratoryClinicalContext
    | PublicHealthClinicalContext
    | ImmunizationClinicalContext
    | PathologyClinicalContext        # future
    | EmergencyClinicalContext        # future
    | AdmissionDischargeClinicalContext  # future
)
```

**`RadiologyClinicalContext`** — exactly today's fields, unchanged, to
guarantee zero regression against the 780-test baseline:
```python
@dataclass(frozen=True, slots=True)
class RadiologyClinicalContext:
    modality: str | None = None
    examination: str | None = None
    body_region: str | None = None
    body_regions: tuple[str, ...] = ()
    contrast: str | None = None
    techniques: tuple[str, ...] = ()
```

**`LaboratoryClinicalContext`** (new, document-level signals only —
NOT extracted field values):
```python
@dataclass(frozen=True, slots=True)
class LaboratoryClinicalContext:
    has_reference_range: bool = False
    result_status_hint: str | None = None   # "finalized" | "preliminary" | "amended" — document-level cue, not the extracted `result` field
    panel_hint: bool = False                # signals this looks like a multi-test panel, not a single test
```

**`PublicHealthClinicalContext`** (new, narrowed to surveillance/
notification per Decision 1):
```python
@dataclass(frozen=True, slots=True)
class PublicHealthClinicalContext:
    notification_type: str | None = None    # "case_notification" | "outbreak_investigation" | "surveillance_summary"
    disease_concept_hint: str | None = None  # e.g. "measles-like" — a ROUTING signal, never the reviewed disease_name
    region_mentioned: bool = False           # presence signal only — the actual region string is EXTRACT's job
```

**`ImmunizationClinicalContext`** (new):
```python
@dataclass(frozen=True, slots=True)
class ImmunizationClinicalContext:
    is_administration_record: bool = False
    is_adverse_event_report: bool = False
    vaccine_concept_hint: str | None = None  # e.g. "MMR-like" — routing signal only, never the reviewed vaccine_name
```

**Hard rule, applies to every domain extension above**: a `_hint` /
`_concept` / boolean presence field is a document-level ROUTING signal
only. It may inform which extractor to invoke or how confident
UNDERSTAND is that this document belongs to a domain. It must NEVER be
treated as, or substituted for, a reviewed, save-ready extracted field
(`disease_name`, `vaccine_name`, `region`, `result`, etc.). Those values
belong entirely to EXTRACT's output — see the companion Extraction
Contract, Section 2.

## 4. Two-Layer Review Model (Decision 0)

```python
@dataclass(frozen=True, slots=True)
class ProcessingContext:
    privacy_profile: str
    extraction_profile: str
    terminology_profile: str
    recommended_capabilities: tuple[str, ...]
    document_review_required: bool     # canonical MedNexus Seven contract name — see migration note below
    # extraction_review_required lives on the EXTRACT output, not here — see Extraction Contract Section 3
```

**Naming migration note**: `document_review_required` and
`extraction_review_required` are the canonical contract names going
forward, approved. Existing Radiology (`manual_review_required`) and
Public Health (`needed_review`) code must NOT be broken by an immediate
rename — the rollout is additive/backward-compatible (e.g. the
canonical name introduced as the primary field with the existing name
retained as a deprecated alias, or an adapter at the contract boundary)
until each side's own implementation migrates on its own schedule. This
contract fixes the target name, not the migration mechanics.

A future unified UI MAY compute a single displayed flag as
`review_required = document_review_required OR extraction_review_required`,
but the two source signals stay independently stored and inspectable —
they answer different questions ("should a human look at this document
before it's routed at all?" vs. "should a human look at this specific
extracted field/record before it's saved?") and collapsing them loses
real information about WHY review was triggered.

## 5. Semantically Typed Dates (Decision 3)

Dates are not extracted by UNDERSTAND (that remains EXTRACT's job —
see companion contract), but UNDERSTAND's `PrivacyContext` must be able
to flag date-shaped spans by ROLE, not just location, so PROTECT can
apply a role-aware policy instead of one blanket date rule:

```python
class DateRole(str, Enum):
    EVENT_DATE = "EVENT_DATE"                       # encounter / onset
    REPORT_DATE = "REPORT_DATE"
    SPECIMEN_COLLECTION_DATE = "SPECIMEN_COLLECTION_DATE"
    RESULT_DATE = "RESULT_DATE"
    ADMINISTRATION_DATE = "ADMINISTRATION_DATE"
    BIRTH_DATE = "BIRTH_DATE"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True, slots=True)
class DatePrivacyRegion(PrivacyRegion):     # extends the existing PrivacyRegion
    date_role: DateRole = DateRole.UNKNOWN
```

This is a UNDERSTAND-side typing contribution; the corresponding
per-role policy ACTION (`KEEP` / `REMOVE` / `GENERALIZE` / future
`SHIFT`) is a PROTECT-side concern, out of scope for this document.
**Status**: architectural shape ratified; no policy profile may be
considered production-ready for date handling until it is rewritten
against `DateRole`, not a single flat `encounter_date` rule.

## 6. What This Contract Explicitly Does NOT Cover

- Field-level entity values of any kind (a specific date, a specific
  disease name, a specific patient age) — these are EXTRACT's output,
  governed by the companion Extraction Contract.
- The actual PROTECT policy actions per `DateRole`/entity type — PROTECT
  profile design, not UNDERSTAND output shape.
- Persistence, dashboards, or indicators — ANALYZE/VISUALIZE/INDICATORS
  stage concerns, unaffected by this contract.

## 7. Compatibility / Migration Note

This is additive to the existing `MedNexusDocumentContext`. Existing
Radiology code paths that only ever populated the old flat
`ClinicalContext` fields (`modality`, `body_region`, etc.) continue to
work unchanged if those fields are preserved on
`RadiologyClinicalContext` and the top-level flat fields are kept as a
deprecated-but-functional alias during migration (implementation
detail, not decided here — flagged for the eventual implementation
plan, not this contract).
