# Current Status — read this first in any new chat

Last updated: 2026-09-22

## MedNexus Seven — cross-project architecture status (added 2026-08-16)

This project is Track B (Domain Intelligence) of the broader MedNexus
Seven architecture (`UNDERSTAND → PROTECT → EXTRACT → STANDARDIZE →
ANALYZE → VISUALIZE → INDICATORS` — INGEST is part of UNDERSTAND, not a
separate stage). See `CLAUDE.md` for the short orientation version and
`docs/mednexus-integration/` for the full authoritative documents:
architecture crosswalk v1.1, Clinical Semantic Context Contract v0.1,
Clinical Extraction Contract v0.1, and the Domain Intelligence Track
Roadmap. **These are APPROVED ARCHITECTURE / CURRENT ROADMAP, not yet
IMPLEMENTED** — this project still runs its own lightweight report-type
detection and has no PROTECT stage; the contracts describe the target
integration shape for later, not current behavior.

**Current checkpoint target: Public Health Stable Scope Checkpoint
v0.1.0** — approved name, a *scope* checkpoint specifically (not
"Complete," "Production Ready," or "Real-World Validated"). Required to
reach it:
- Three report types (Notifiable Disease, Immunization, Laboratory) — IMPLEMENTED.
- Indicators layer — IMPLEMENTED.
- ICD-10 terminology — IMPLEMENTED.
- LOINC terminology — IMPLEMENTED, end-to-end save verification CONFIRMED (2026-08-16: Measles IgM Serology → 21503-8, Poliovirus Stool PCR → null, both as designed).
- CVX (vaccine) terminology — IMPLEMENTED, end-to-end save verification CONFIRMED (2026-08-17: BCG → 19, Rota → 116, both as designed).
- pytest coverage for everything built after the 126-test baseline (`indicators.py`, `load_icd10_lookup`, `load_loinc_lookup`, `load_cvx_lookup`, `/indicators/dashboard-data`) — NOT YET STARTED.
- Synchronized `CURRENT_STATUS.md`/`docs/decisions-log.md` — this update.
- GitHub `v0.1.0` release tag — NOT YET CREATED.

Explicitly OUT of this checkpoint's scope (tracked, not blocking):
CSV ingestion and OCR (text-layer PDF upload has since been built, but
this checkpoint never required it), Syndromic/Outbreak report types,
deployed frontend, lower-priority extraction fields, the three
documented multi-observation schema gaps (GeneXpert MTB/RIF, Lyme
Two-Tier, Widal H-antigen), and any real-world (non-synthetic)
validation.

**Next domain after this checkpoint: Laboratory** — per the roadmap,
this generalizes the existing Laboratory implementation (already
built) rather than starting fresh; explicitly not a rebuild.

**Cross-Track Synchronization Policy** (standing, from the roadmap
approval): a formal Cross-Track Sync Brief is required when a shared
contract/schema assumption changes, when this checkpoint is reached,
when a change here affects MedNexus Main, when a MedNexus Main
dependency becomes necessary, and before the future "MedNexus
Integrated Domain Checkpoint" (contract-conformance with a real,
implemented `MedNexusDocumentContext`/`ProtectionContext` from MedNexus
Main — distinct from, and later than, the "Domain Development
Checkpoint" this project can reach independently on synthetic data with
its own local detection). Routine internal changes that don't affect
shared contracts do not require one.

## Where we are right now

Notifiable Disease, Immunization, AND Laboratory are all end-to-end
complete, each with a measured 100% field-accuracy figure on their own
full 500-report run, PLUS a working document-upload pipeline (DOCX, TXT
and text-layer PDF) with automatic (3-way) report-type detection, a
batch/cohort system, data export, an Indicators layer sitting above all
three report types, and a fully redesigned frontend (landing page, four
dashboards, brand
identity). Same extraction pipeline shape for all three report types:
raw text -> GLiNER NER + gazetteer(s) + rule-based fields -> confidence
report -> save to Postgres.

**Batch Upload regression fixed: file selection now accumulates again
(2026-09-22).** Found by Dr. Sameh's own testing: selecting files a
second time (Browse again, or another drag-and-drop) was REPLACING the
first selection instead of adding to it. `git blame`/`git log --all`
confirmed every line of the relevant code was introduced in one commit
this session (`afdcfc1`) and never existed before — the feature had
been built and left uncommitted since an earlier session, so git
history could not date the regression, only confirm there's no earlier
version to compare against. Fixed in two parts: `showBatchSelection()`
now accumulates onto `pendingBatchFiles` instead of replacing it (the
10-file-cap check/message now reflect the true accumulated total); and
`pendingBatchFiles` is now cleared when a batch actually starts
processing, otherwise a later, separate run would have silently
re-included already-submitted files — a second problem found and fixed
while fixing the first, not part of the original report. Live-verified:
3 files then 3 more → 6 total; 6 then +5 (over the cap) → correctly
wiped, message reflects the true total of 11, not 5; drop and Browse
mixed correctly; a fresh selection after a completed run did not
re-include that run's files. Full detail: decisions-log.md, 2026-09-22.

**Terminology-code preview, live in the review table (2026-09-21/22).**
New `GET /terminology/preview?report_type=...&value=...` shows what
icd10_code / vaccine_code / test_code WOULD resolve to right now, while
a report is still being reviewed — Single and Batch both — not just
after save. Planned first (written plan approved before code, same
process as PDF/Batch Upload) and built in 4 verified milestones: M1
backend, M2 single-report wiring, M3 Batch Upload wiring, M4 this
polish-and-docs pass. Zero changes to extraction, confidence,
needs_review or save: the three save-time lookups
(`load_icd10_lookup().get()`, `get_loinc_code()`, `get_cvx_code()`) are
untouched; three new, additive functions —
`get_icd10_entry()`/`get_loinc_entry()`/`get_cvx_entry()` in
`vocabularies.py` — reshape those SAME lookups' results for the preview
endpoint, which holds no lookup logic of its own. The preview renders as
a block below the field table, not another row in it — deliberately, so
it never reads as an editable extracted field — appears immediately for
the as-extracted value, and recomputes on every edit of the field it
watches (`disease_name` / `vaccine_name` / `test_name`) via one
delegated `change` listener per flow, reusing the exact per-card
isolation (`closest(".batch-progress-card")`) Batch Upload's own
Reviewed-checkbox listener already used. Proven independent across
multiple simultaneous batch cards, including two cards of the SAME
report type edited one after the other.

The response carries a 4th field beyond `{code, status, note}`:
**`in_vocabulary`**. It exists specifically to tell apart two different
"no code" situations that would otherwise look identical: a value that
simply doesn't match the vocabulary yet (`in_vocabulary: false` — a
typo, or a value still mid-edit) versus a value that IS recognized but
genuinely has no usable code by deliberate clinical decision
(`in_vocabulary: true, code: null` — true today for exactly 3 of 71 lab
tests: Poliovirus Stool PCR, Hantavirus IgM Serology, Leprosy Skin
Biopsy, each shown with Dr. Sameh's own reviewer note). Conflating those
two would be misleading, not just imprecise, so the UI gives them
different headline text ("Not available yet for this wording." vs.
"Reviewed — none applies." plus the real note) rather than relying on
note text alone to carry the distinction. ICD-10 gets a `note` (the
existing 9 diseases' `*_flag` reviewer text, exposed for the first time)
but no `status` — there is still no per-entry ICD-10 mapping-status
taxonomy the way LOINC/CVX have (EXACT / NO_DIRECT_LOINC / ...);
inventing one is a separate, later task needing the same kind of
clinical review LOINC/CVX already got, not retrofitted here.

Tests: 220 → **263 passed + 2 expected xfails** (43 new: 25 in
`test_vocabularies.py` against the real data files directly, 18 in
`test_terminology_preview_endpoint.py` over HTTP). Found and handled in
passing: `get_cvx_entry()`/`get_loinc_entry()` guard against a
non-dict raw entry, because `cvx_codes.json`'s own top-level `_comment`
key is a plain string (unlike `icd10_codes.json`'s, already filtered
out by `load_icd10_lookup()`) — the SAME gap already exists in the
shipped `get_cvx_code()` the save endpoint uses, just never hit because
no real vaccine is named `_comment`; not fixed there (save logic stays
untouched), but the new preview-only functions don't carry the same
risk forward. M4 polish, both checked against their real worst case
rather than assumed correct: the stale-response race guard was proven
by artificially delaying one response 3 seconds behind a second, faster
edit and confirming the slow one — arriving about 10 seconds later —
never overwrote the newer result; long-note wrapping was checked at the
actual longest note in the whole dataset (971 characters, CVX's
Meningococcal ACWY entry), zero horizontal overflow, no CSS change
needed. One dev-environment gotcha worth recording: this frontend is
served with no live-reload (`python -m http.server`), so a browser tab
left open across an editing session keeps running the JS it loaded at
the START of that session — mid-M3, batch cards briefly showed no
preview at all until a stale tab (open since M2) was reloaded. Not a
code defect. Not verified: on Render (no deploy run); Dr. Sameh's own
Chrome check is still pending, same process as PDF's.

**PDF document upload built (2026-09-20/21) — ingestion only; own-browser
check CONFIRMED.** `POST /reports/parse-document` now accepts `.pdf`
next to DOCX/TXT, for BOTH Single and Batch upload, with zero changes to
detect → extract → confidence → review → save: PDF is an ingestion
change (bytes in, text out) and the response is still `{"text": ...}`.
Text layer only, via `pypdf` 6.19.0 (pinned in `requirements.txt`, with
`httpx` for the endpoint tests). There is no OCR, so a scanned/image-only
PDF is refused with a clear message instead of returning nothing.
Limits for EVERY format: 10 MB and 30 pages (DOCX/TXT have no pages, so
they are judged at about 3,000 characters per page). Each failure has its
own approved message — not a real PDF, damaged, password-protected
(AES-encrypted PDFs are refused as protected on purpose: no crypto
package is installed), no text layer, over the page or size limit — and a
corrupt `.docx`, which used to escape as a raw 500, now gets the same
clean 422. Frontend: only the two file inputs' `accept` attributes and
the dropzone hint changed. **Own-browser check CONFIRMED (2026-09-21):**
Dr. Sameh verified directly in his own Chrome that PDF upload works
correctly in both Single report and Batch upload, real file-picker
filtering included. pypdf was kept over pypdfium2 after a side-by-side
on the local 60-file test set (identical text on all 10 compared) plus
one Edge-printed synthetic report (the only differences are hyphens:
pypdf splits soft-hyphenated words, PDFium mangles a hyphen at a line
wrap — one artifact traded for another) — full reasoning in
decisions-log.md, 2026-09-21. Tests: 126 in the last commit → 138 when
this work began → **220 passed + 2 expected xfails** now, and a
24-deliberate-break mutation pass (against a scratch copy, not the repo)
caught every break. **Not done / not verified:** PDF text on Render (no
deploy run); ANY field-level accuracy measurement on PDFs
(extraction and detect-type were deliberately not run on the 60 test
PDFs — a separate, later step); Arabic/right-to-left PDFs and producers
other than ReportLab and Edge. **Recorded for that accuracy step**
(detail in decisions-log.md): a browser-printed PDF's default header and
footer stamp a date on every page (M/D/YY in this machine's en-US
locale), while the date rules read slash dates day-first and try them
before month-name dates — a stamp like `9/3/26` becomes 9 March and
beats a correct body date, with no review flag; and a PDF that mixes
typed and scanned pages is read WITHOUT any warning that the scanned
pages contributed nothing (only a fully image-only PDF is refused).
Separately, while measuring 10 MB uploads, an earlier note blaming the
environment for intermittent stalls was corrected: `python-multipart`
0.0.9's boundary search is slow (about 2 s per MB) only when the
payload's bytes also occur in the request's random hex boundary;
realistic files parse at 0.01-0.05 s per MB. Pre-existing, no action
taken.

**Python environment recovery + LOINC end-to-end verification CONFIRMED +
requirements split decision (2026-08-16).** `backend/venv`'s linked Python
3.10 install (`AppData\Local\Programs\Python\Python310`) lost its
`python.exe` (an external machine issue, unrelated to this project).
Rather than repair the machine-wide install or borrow anything from the
sibling MedNexus Main project (kept strictly isolated throughout), a
fully independent, project-local environment was built: `.runtime/Python310`
(python.org's official embeddable 3.10.11 package, MD5-verified against
python.org's published hash) bootstrapped with pip via the official PyPA
`get-pip.py`, then `virtualenv` (the embeddable distribution ships
without the stdlib `venv`/`ensurepip` modules) to create
`backend/venv_recovery`. Both `.runtime/` and `backend/venv_recovery/`
are gitignored. `start_backend.ps1` now invokes `venv_recovery`'s
interpreter by its explicit full path instead of activating it — see the
updated "Key ground rules" entry below. Full 126-test baseline
reconfirmed on the new environment first; `backend/venv` (broken) kept
in place, untouched, as a rollback artifact. With the environment
working again, LOINC auto-population was run end-to-end through the
real UI for the first time: Measles IgM Serology → `test_code:
"21503-8"`, Poliovirus Stool PCR → `test_code: null` (the deliberate
REJECTED_MISMATCH entry, not a bug) — both confirmed via a real save +
Export JSON pull, matched by full record content (not just test name,
since the export also holds 500+ pre-existing synthetic records with
overlapping facility/test-name combinations). **Requirements split
decision:** running real extraction surfaced that `backend/requirements.txt`
has never included the extraction stack (`openmed[gliner]` — torch,
transformers, spaCy, ~89 packages) — this was already true before the
environment recovery, just newly visible. Decision: keep them split
rather than merge. `requirements.txt` stays the lightweight API/DB/
dashboard/test surface (also exactly what Render's `buildCommand`
installs, and what pytest's fake `ner_fn` needs — GLiNER is never
required for tests or for the Render trial, where `/extract`
deliberately 503s per `render.yaml`'s existing note). A new
`backend/requirements-extraction.txt` will hold the local-only
extraction stack starting with `openmed[gliner]` (installed versions
confirmed: openmed 2.1.0, gliner 0.2.28, torch 2.13.0, transformers
5.13.1, tokenizers 0.22.2). No full transitive lock file yet — deferred
to a future environment-governance milestone.

**LOINC for Laboratory + MedNexus cross-project architecture work
(2026-08-16).** `backend/data/lab_tests.json` expanded from 15 tests
(originally mirroring only 10 diseases) to 71, covering 53 of 54
notifiable diseases (Tetanus excluded — no confirmatory lab test
exists; diagnosis is clinical), sourced from CDC NNDSS laboratory
criteria and then corrected against direct clinical review (adding
confirmatory/molecular tests alongside screening tests for TB, HIV,
Hepatitis B/C, Malaria, Meningococcal, Diphtheria, Brucellosis,
Leptospirosis, Rabies). `backend/data/loinc_codes.json` maps all 71 to
LOINC codes with a 7-value mapping-status taxonomy per entry (EXACT
through REJECTED_MISMATCH) rather than a flat code-or-nothing model —
see "What's already working" below for the three tests deliberately
left uncoded. Wired into the Laboratory save endpoint the same way
ICD-10 was wired into Notifiable Disease's.

Separately: this project's relationship to the broader MedNexus Seven
architecture (a parallel enterprise platform by the same owner) was
formalized this session — an Architecture Crosswalk, two frozen
contracts (Clinical Semantic Context Contract v0.1, Clinical Extraction
Contract v0.1), and an approved Domain Intelligence Track Roadmap now
live in `docs/mednexus-integration/`. This project is Track B (Domain
Intelligence) — full detail in the "MedNexus Seven" section at the top
of this file and in `CLAUDE.md`. No code changed as a result of this
architecture work; it establishes the target integration shape for
later, and this project's current checkpoint (Public Health Stable
Scope Checkpoint v0.1.0) is explicitly scoped to NOT require any of it
to be implemented yet.

**Indicators layer built end-to-end (2026-08-06).** New
`backend/app/services/indicators.py` holds two cross-cutting metrics,
kept separate from each report type's own dashboard query logic:
`vaccination_coverage_by_region` (immunization_records doses joined
against population_strata — same denominator table Notifiable
Disease/Immunization already use for rate-per-100k) and
`test_positivity_by_region` (laboratory_records positive/(positive+
negative) by region, same pct_positive definition the Laboratory
dashboard already uses, just broken out by region where that dashboard
only had a raw count). Combined `GET /indicators/dashboard-data` in
main.py returns both. New `frontend/prototype/indicators-dashboard.html`
renders them (bar charts + a per-region card grid — the region-level
comparison shape didn't fit the other dashboards' time/filter-driven
layout), matches the existing brand system exactly (same style.css, no
new CSS framework), and is linked from the nav on all three other
dashboards. Noted for later: with only 500 synthetic immunization doses
against Kuwait's real population, coverage_pct is ~0.01% everywhere and
not visually differentiated yet — the chart shows doses_administered
instead for now; revisit once data volume is realistic.

**Render Postgres reset again — 3rd time (2026-08-06).**
immunization_records and laboratory_records were found empty (0 rows)
while notifiable_disease_records was untouched (501 rows) — same failure
shape as the first reset (2026-07-28), cause still not conclusively
identified. Both tables repopulated via the existing
`load_immunization_reports.py` / `load_laboratory_reports.py` loaders
(full 500 each, re-confirmed 100% accuracy on every field). Real gotcha
hit and fixed along the way: those loaders only INSERT, they never clear
existing rows first — running a `--limit 10` trial and then the full run
without clearing in between left 10 duplicated rows in each table.
New one-off `scripts/clear_immunization_and_lab_records.py` clears both
tables before a clean reload; worth remembering as a standing gotcha,
not just a one-time fix. Separately, both Render services (web service
and Postgres) were upgraded to paid instance types specifically to stop
the recurring free-tier expiry — this does NOT undo data already lost,
only prevents the *next* reset. Both services are now grouped under one
Render Project ("mednexus-public-health") for easier billing/management
— organizational only, no code or URL changes.

**Terminology normalization started (2026-08-06) — ICD-10 for Notifiable
Disease done, LOINC and vaccine codes not started yet.** New
`backend/data/icd10_codes.json` maps all 54 notifiable diseases to WHO
ICD-10 codes (three-character category level, not the US-billing
ICD-10-CM extended subcodes — matches the project's system-agnostic/
international-standards ground rule). Kept as a lookup file SEPARATE
from `notifiable_diseases.json` on purpose: the gazetteer still drives
name matching during extraction untouched, and the new
`load_icd10_lookup()` in `vocabularies.py` is only consulted at SAVE time
in `main.py` to auto-populate `icd10_code` when the request didn't
already supply one. 9 of the 54 codes are flagged in the file itself
(`_flag` keys) because a single 3-character code can't cleanly represent
a real clinical distinction the case-report schema doesn't currently
capture — Hepatitis A/B/C (acute vs chronic), HIV infection (which
resulting condition), Haemophilus influenzae invasive disease (site-
dependent, no single WHO code fits), Influenza (different ICD-10 chapter
entirely — J09-J11, not A00-B99), Malaria (species not captured),
Syphilis (stage not captured), and Tuberculosis (site + confirmation
method not captured — the highest-scrutiny one given TB's public-health
weight). Dr. Sameh gave provisional approval on the defaults; full
clinical review of the 9 flagged entries is still open. Not yet
end-to-end tested against a real save — next step is confirming
icd10_code actually populates correctly via the UI + an Export JSON
check. LOINC (lab tests) and vaccine codes (likely CVX) are the next two
domains, each planned as its own separate step the same way ICD-10 was.

**Data sourcing reviewed 2026-07-30.** `vaccines.json` was already a real
source (Kuwait MOH's 2025 Childhood Immunization Schedule).
`notifiable_diseases.json` was NOT — it was a synthetic placeholder (10
diseases the developer picked to build the generator around), an
inconsistency flagged and fixed the same day: replaced with a 54-disease
list curated from CDC's official "2025 Nationally Notifiable Conditions"
protocol (approved by CSTE June 2024, implemented January 2025) — the
most complete, current, authoritative notifiable-disease reference
found; no equivalent Kuwait MOH list was locatable via search. The
curation excluded CDC categories that aren't infectious disease or don't
fit this project's case-report schema (cancer, lead-in-blood, silicosis,
pesticide-related illness, foodborne/waterborne OUTBREAK categories,
narrow US lab-classification subtypes like VISA/VRSA) and kept
"Influenza" as a deliberate addition beyond the strict CDC list, since
it's foundational to what's already built and regionally relevant
despite not being a standalone US routine-notification category.
Verified: the expanded gazetteer still extracts all 500 existing
synthetic reports at 100% (a strict superset of the original 10) — the
existing synthetic test corpus still only exercises those original 10
by name, though the real gazetteer now recognizes 54. `lab_tests.json`
is still a synthetic placeholder (built to mirror the original 10
diseases) — reviewing it against a real terminology source (e.g. LOINC)
is the next sourcing item, along with checking whether `vaccines.json`
should expand beyond the pediatric schedule (adult/travel vaccines
aren't covered yet).

**Document upload + auto-detection (2026-07-29).** The "Upload a
document" button is no longer a placeholder — `POST
/reports/parse-document` extracts text from DOCX/TXT (python-docx; PDF
was added 2026-09-20/21 — see the top of this section — CSV is still
not built), and `POST /reports/detect-type` guesses which
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
Testing these through the real UI caught (and fixed) a genuine bug: an
earlier edit had silently deleted the `@app.post(...)` decorator above
`extract_immunization_report`, so the function existed but FastAPI never
registered it as a route — `POST /reports/immunization/extract` returned
a plain 404 until the decorator was restored. All 14 `/reports/*` +
`/health` routes were audited by name afterward, not just the ones
touched in that edit. Both Immunization DOCX demos now confirmed
extracting correctly through the real running backend.

**Laboratory report type completed 2026-07-29.** test_name and
specimen_type via new gazetteers (`data/lab_tests.json`,
`data/specimen_types.json`, 15 tests / 8 specimen types, synthetic
placeholders); pathogen_identified REUSES the disease gazetteer directly
(no separate vocabulary), populated only when result is positive; result
and the two dates (specimen_collection_date, result_date — disambiguated
via a narrow keyword-anchor window, verified against tight shorthand
phrasing like "Collected 22 Mar 2025, result 27/3/25:") all rule-based.
Own dashboard (`laboratory-dashboard.html` +
`GET /reports/laboratory/dashboard-data`) with metrics specific to
testing activity rather than case/dose counts: % positive, % pending,
average turnaround time, tests by type/region/pathogen — no count/rate
toggle, since a test result is an activity metric, not a population
health event the way a case or dose is. Report-type auto-detection
extended from 2-way to 3-way (99.2% on the combined 1500-report corpus,
the only miscategorized) — a real, inherent overlap where a Notifiable
Disease report narrates its own confirmatory lab result using phrasing
close to a standalone lab report, not a bug to force to 100%.

**Two real bugs found and fixed via genuine testing 2026-07-29:** (1)
`/reports/immunization/extract`'s route decorator was silently deleted
during an editing mistake while adding the export endpoint — the
function still existed, FastAPI just never registered it, caught only
when the user tested the real UI ("Not Found", not an application
error). Fixed, and all 19 routes audited by name afterward, not just the
ones touched in that edit. (2) The Laboratory generator never actually
wired "Varicella PCR" to any disease in its own test-selection map
despite listing it in the vocabulary, so it could never appear in
generated data — noticed by the user checking the dashboard's test
dropdown against the vocabulary file directly. Fixed by giving
Chickenpox two test-name options (Chickenpox PCR / Varicella PCR, same
disease, two real naming conventions).

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

263 backend tests passing, plus 2 expected xfails (126 in the last
commit; 138 when the PDF work began, 220 when the PDF work finished —
see the PDF and terminology-preview entries above).

**IMMEDIATE NEXT STEP:** Confirmed — ICD-10 auto-population verified
end-to-end against a real save (Influenza → J11 confirmed in Export
JSON, 2026-08-06), LOINC auto-population verified end-to-end the same
way (Measles IgM Serology → 21503-8, Poliovirus Stool PCR → null,
2026-08-16 — see the entry above), AND CVX auto-population verified
end-to-end the same way (BCG → 19, Rota → 116, 2026-08-17 — see the
entry below). Notifiable Disease's `lab_test_type` field and
Immunization's `vaccine_code` field were previously listed as
unattempted extraction targets and are both superseded by this work;
not separately tracked. Remaining, in order:
1. No pytest coverage yet for the newest code (indicators.py,
   load_icd10_lookup, load_loinc_lookup, load_cvx_lookup, the
   /indicators/dashboard-data endpoint) — the 126 passing tests predate
   all of it. Worth closing before this drifts further from "everything
   measured," and required before the v0.1.0 checkpoint (see the
   MedNexus Seven section above).
2. First GitHub release tag (`v0.1.0`) — see the MedNexus Seven section
   above for exactly what it should and shouldn't claim.
3. Syndromic/Outbreak report types (schemas exist, no extraction logic)
   — explicitly OUT of the v0.1.0 checkpoint; begins after it, and after
   Laboratory (next domain vertical, see MedNexus Seven section above).
4. CSV document upload (DOCX, TXT and text-layer PDF are done; OCR for
   scanned PDFs is not) — also OUT of the v0.1.0 checkpoint.
5. Point the frontend at the deployed Render URL instead of
   `http://127.0.0.1:8002` (still hardcoded in `app.js` and all four
   dashboards) — more relevant now that indicators-dashboard.html exists
   too. Deploying the frontend itself as a Render Static Site (raised
   2026-08-06, not yet done) would make demos to decision-makers a
   shared link instead of a two-terminal local setup.
6. Lower-priority extraction fields still not attempted: Notifiable
   Disease's occupation/travel_related/travel_country/vaccination_status/
   outcome, and Immunization's `lot_number` (dose_number/route already
   attempted rule-based fields, unaffected by this work).
7. PDF field-level accuracy testing — run extraction on the 60 local
   test PDFs and compare the fields to their `ground_truth.csv`. Kept
   deliberately separate from the ingestion work and not started or
   prioritized yet. Known things to measure or decide first are in the
   PDF entry above and in decisions-log.md, 2026-09-21: browser print
   stamps vs the day-first date rules, partly scanned PDFs, and
   soft-hyphen/line-wrap splits.

## What's already working (locally)

- Full extraction pipeline for **Notifiable Disease** report type: raw
  text → GLiNER-based NER + rule-based fields + gazetteers → confidence
  report → editable review UI → save to Postgres.
- Full extraction pipeline for **Immunization** report type: raw text →
  GLiNER NER + vaccine/region gazetteers + rule-based fields (dose
  number, route, adverse event, patient_age_months) → confidence report
  → save to Postgres, plus its own dashboard.
- **Document upload**: DOCX/TXT/PDF parsing (`services/document_parsing.py`;
  PDF is text layer only — see the PDF bullet below)
  + automatic report-type detection (`services/report_type_detection.py`,
  100% correct on all 1000 real synthetic reports) — the frontend
  dropzone is fully wired, not a placeholder.
- **Batch/cohort system**: save-time batch selection, per-dashboard batch
  filter, non-destructive (existing data untouched, `batch_label` is
  nullable).
- **Export**: JSON/CSV download per batch (or everything) on both
  dashboards — the safety net for manually-saved records with no other
  backup.
- 263 backend tests passing plus 2 expected xfails (`pytest tests/ -v`
  from `backend/`); 126 in the last commit.
- **Terminology-code preview** (2026-09-21/22): `GET
  /terminology/preview` shows what icd10_code/vaccine_code/test_code
  would resolve to live, in the review table (Single and Batch), before
  save — built on the SAME save-time lookups, via three new additive
  `get_*_entry()` functions in `vocabularies.py`; nothing about
  extraction, confidence or save changed. See the dated entry above for
  the `in_vocabulary` design and the M4 verification detail.
- Negation-aware extraction in BOTH directions ("ruled out dengue" and
  "dengue was ruled out"), bounded to the sentence so a negation can't leak
  onto a neighbouring diagnosis — applies to both NER entities and
  gazetteer matches. Immunization's vaccine_name doesn't need this.
- Closed-vocabulary matching via data-driven gazetteers for region,
  disease name, AND vaccine name — regions come from population_strata,
  diseases from `backend/data/notifiable_diseases.json` (54 diseases,
  real — curated from CDC's 2025 Nationally Notifiable Conditions list,
  see 2026-07-30 entry above), vaccines from `backend/data/vaccines.json`
  (real, from the Kuwait MOH schedule). None hardcoded in extraction.
- **ICD-10 codes for Notifiable Disease** (2026-08-06): all 54 diseases
  mapped in `backend/data/icd10_codes.json`, auto-populated at save time
  via `load_icd10_lookup()` — separate from the gazetteer, doesn't touch
  extraction matching. 9 entries flagged for Dr. Sameh's clinical review
  (see 2026-08-06 entry above). End-to-end save verification CONFIRMED
  (Influenza → J11 in Export JSON, 2026-08-06 — see the IMMEDIATE NEXT
  STEP paragraph above).
- **Indicators layer** (2026-08-06): `services/indicators.py`
  (vaccination coverage % by region, test positivity % by region),
  combined `GET /indicators/dashboard-data`, and
  `frontend/prototype/indicators-dashboard.html` — linked from all four
  dashboards' nav.
- **LOINC codes for Laboratory** (2026-08-16): all 71 lab tests mapped
  in `backend/data/loinc_codes.json` (richer than the ICD-10 lookup —
  each entry carries a `status` from a 7-value mapping taxonomy: EXACT,
  ACCEPTABLE_GENERIC_SPECIMEN, ACCEPTABLE_GENUS_LEVEL, PROXY, COMPOSITE,
  NO_DIRECT_LOINC, REJECTED_MISMATCH), auto-populated at save time via
  `get_loinc_code()` — same separated-lookup pattern as ICD-10. Three
  tests deliberately left uncoded after clinical review (Poliovirus
  Stool PCR, Hantavirus IgM Serology, Leprosy Skin Biopsy) rather than
  forced to a wrong/misleading code. `lab_tests.json` itself was
  expanded 15→71 in the same pass (see 2026-08-16 entry below) — the
  "still a synthetic placeholder" note that used to be here is resolved.
  End-to-end save verification CONFIRMED (2026-08-16, see entry above):
  Measles IgM Serology → 21503-8, Poliovirus Stool PCR → null.
- **CVX codes for Immunization** (2026-08-16/17): all 12 vaccines mapped
  in `backend/data/cvx_codes.json` — 8 EXACT (single unambiguous active
  CDC code) and 4 ACCEPTABLE_GENERIC_FORMULATION, each clinically
  reviewed against the Kuwait 2025 Childhood Immunization Schedule
  (Dr. Sameh, 2026-08-16) and carrying a `confirmed_by_schedule` flag —
  `true` where the schedule itself confirms the specific default
  (Hepatitis B's birth-dose timing, Rota's 3-dose pentavalent pattern),
  `false` where the schedule confirms only the vaccine family, not the
  exact product (Meningococcal ACWY's carrier protein, Pneumococcal's
  valency) — a provisional default, not forced false precision.
  Auto-populated at save time via `get_cvx_code()` — same
  separated-lookup pattern as ICD-10/LOINC. End-to-end save verification
  CONFIRMED (2026-08-17, see entry below): BCG → 19, Rota → 116.
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
  Disease), `immunization-dashboard.html`, `laboratory-dashboard.html`,
  and `indicators-dashboard.html` — combined filters including Batch,
  Chart.js charts, count/rate toggle, Export buttons (Indicators page is
  filter-free for now — see 2026-08-06 entry above for why).
- **Batch Upload** (2026-09-17): drag-and-drop or multi-select up to 10
  files at once, any mix of the three report types, processed
  sequentially through the same parse/detect/extract endpoints the
  single-report flow already used — zero new backend endpoints anywhere
  in this feature. Progress is cold/warm-aware: the first extraction
  call of the session shows a slower amber "loading the model, up to a
  minute" indicator, every call after it (same batch or a later one)
  shows a fast, light indicator instead — timed directly against the
  real backend before any UI was built (~29-58s cold, ~0.2-0.6s warm),
  which is also what ruled out needing concurrent processing. Each file
  becomes its own editable review card via `renderFieldsTable()` and
  `collectEditedRecord()` — factored out of the single-report flow and
  shared, not duplicated — with a "Reviewed — ready to save" checkbox
  that starts unchecked on every card, always: editing a field or a
  successful detection never checks it, and there is deliberately no
  select-all/mark-all-reviewed control anywhere, confirmed absent by
  design and by live test. A file that can't be confidently classified
  shows a five-type mini-picker and blocks only that one card; every
  other file keeps processing regardless. The batch-wide save step
  unions all three types' existing `/batches` endpoints client-side (one
  shared picker, not per-card) so a mixed batch can target one batch
  label spanning multiple tables, then saves only the checked cards
  through their own type's existing `/save` endpoint, updating each card
  with its own ✓/✗ result — one failed card (e.g. an edited value the
  schema rejects) never blocks or loses the others, and stays
  reviewed/retryable without resaving anything already successful. Two
  real bugs found and fixed via live testing, not just written and
  assumed correct: a CSS `[hidden]` specificity bug that showed the Save
  button before any file was selected (a same-specificity class rule was
  beating the attribute's own `display:none`), and a FastAPI 422
  validation error rendering as `[object Object]` because `detail` is a
  structured array, not a string — fixed with a shared
  `formatSaveError()` helper that also quietly fixed the identical
  latent bug already sitting in the pre-existing single-report
  `saveRecord()`, which had never actually been exercised by a real
  validation failure before.
- **Upload page layout and save-step conveniences** (2026-09-18/20,
  frontend only — no backend change, no change to extraction, review or
  saving): a **Single report / Batch upload mode switch** (two
  alternative paths; it only shows/hides the two panes, and `#batch` in
  the URL opens Batch); **read-only report-type cards** in the Batch pane
  ("nothing to select" — Batch detects each file's type); post-save
  **"View <Type> Dashboard" links** (Single: one; Batch: one per saved
  type; they carry `?batch=<label>` when a batch was used, the three
  per-type dashboards read `?batch=` on first load, and they open in a
  new tab); and a **Batch "Save to" picker filtered by the ticked
  reports' types** (a client-side union of the three `/batches`
  endpoints; convenience only — saving is unchanged, and a pick that
  stops matching stays selected, marked "— no matching records"). No
  select-all/mark-all-reviewed control exists or was added. Checked by
  DOM inspection and headless-Edge screenshots against the real backend;
  own-browser confirmation isn't recorded here. Detail: decisions-log.md,
  2026-09-20.
- **PDF upload** (2026-09-20/21): `extract_text_from_pdf` and
  `normalize_pdf_text` in `services/document_parsing.py` (pypdf, text
  layer only), behind the same `POST /reports/parse-document` that
  DOCX/TXT already used — Single and Batch upload both accept `.pdf`, and
  the only frontend change is the file inputs' `accept` attributes and
  the dropzone hint. Limits for every format: 10 MB and 30 pages
  (DOCX/TXT at about 3,000 characters per page). Status codes: 415
  unsupported type, 413 over 10 MB, 422 for every unreadable or
  over-length file, each with its own message, shown verbatim in both
  flows. Parsing runs in a worker thread so a slow PDF can't stall other
  requests. Tests: `test_document_parsing.py`, `test_pdf_static_fixtures.py`
  and `test_parse_document_endpoint.py`, with `tests/pdf_fixtures.py` (a
  stdlib PDF builder) and `tests/fixtures/` (an Edge-printed synthetic
  report and three tiny AES-encrypted files; README inside). Diagnostic:
  `python scripts/pdf_ingestion_profile.py <folder>` from `backend/`
  (census of a folder of PDFs; `--compare FILE...` against
  pypdfium2/pdfminer.six when those are on PYTHONPATH) — statistics and
  short excerpts only. Own-browser check CONFIRMED by Dr. Sameh
  (2026-09-21): PDF upload works correctly in both Single report and
  Batch upload, real file-picker filtering included.

## What's not built yet

- Syndromic, Outbreak report types (schemas exist in
  `backend/app/schemas/`, no extraction logic yet — reuse
  `entity_selection.py` and `confidence.py`, don't reimplement them).
- Terminology normalization: ICD-10 (2026-08-06), LOINC (2026-08-16),
  and CVX (2026-08-17) all done — see "What's already working" above.
  Immunization's `lot_number` remains a separate, still-unattempted field.
- No pytest coverage yet for indicators.py, load_icd10_lookup(),
  load_loinc_lookup(), load_cvx_lookup(), or /indicators/dashboard-data —
  the 126 passing tests predate all of it. Required before the v0.1.0
  checkpoint.
- Two Indicators layer improvements identified while comparing our
  design against the WHO Immunization Data portal
  (immunizationdata.who.int), 2026-08-17: (1) a time dimension —
  coverage/positivity trends over time (by month or year), not just the
  current single-snapshot-per-region view. This is the more valuable of
  the two for real decision-making; the WHO portal centers on
  trendlines rather than point-in-time numbers. (2) A vaccine-specific
  filter dropdown on the Indicators dashboard UI —
  `vaccination_coverage_by_region()` already accepts a `vaccine_name`
  parameter, but no frontend control exposes it yet; a small UI
  addition, not new backend work. Both deferred until after the current
  round of blind-testing/bug-fixing wraps up — not urgent, not part of
  the v0.1.0 checkpoint scope, just tracked so they aren't lost.
- CSV document upload. PDF upload reads the text layer only: no OCR
  (a scanned/image-only PDF is refused with a clear message), a PDF that
  mixes typed and scanned pages is read without any warning about the
  scanned pages, and no field-level accuracy pass has been run on PDFs
  yet. Also untested: Arabic/right-to-left PDFs and producers other than
  ReportLab and Edge. See the 2026-09-21 PDF entry in decisions-log.md.
- Frontend is not yet pointed at the deployed Render URL — still
  hardcoded to `http://127.0.0.1:8002` in `app.js` and all four
  dashboard pages. Frontend itself also isn't deployed anywhere yet
  (still local-only via `python -m http.server`) — raised 2026-08-06 as
  worth doing (Render Static Site, free) once there's something ready to
  demo, not urgent before that.
- Lower-priority extraction fields: Notifiable Disease's
  occupation/travel_related/travel_country/vaccination_status/outcome,
  Immunization's vaccine_code/lot_number.
- A separate backup store for batches — right now Export (JSON/CSV) is
  the only safety net; nothing automatic yet.
- Dashboard refresh takes 3-4s: ~12 separate queries against Render's
  free-tier Postgres in Oregon. Latency, not a code problem.

## Local dev routine (two terminals running servers, every session)

See `README.md`. Terminal 1 (backend, port 8002 — 8001 is reserved for
MedNexus Main, changed 2026-08-16) needs `$env:DATABASE_URL`
set to the Render external connection string before starting uvicorn, so
saves and dashboard queries hit the same database — otherwise it falls
back to a local Postgres URL that isn't set up. Terminal 2: frontend
static server, port 5500 (serves `index.html` and all four dashboard
pages). Never open the HTML files as a `file://` path (CORS/private-network
blocking). Metabase (Terminal 3) is no longer part of the routine.

A third terminal is still needed whenever typing an actual command (git,
a one-off script, pytest) — Terminals 1 and 2 are permanently occupied
running their server process and won't accept input while running. This
third terminal doesn't need to stay open between sessions the way the
first two do; open/close it as needed. Clarified 2026-08-06 after real
confusion about why "two terminals" didn't match needing to run git
commands somewhere.

## Key ground rules established (see docs/decisions-log.md for full reasoning)

- Core schemas stay system-agnostic — no country/ministry-specific logic
  in extraction or normalization. Ministry integrations (DHIS2, etc.) are
  optional adapters layered on top, never a dependency.
- Never put real patient data on Render or any shared/cloud service —
  synthetic data only until access control is properly designed.
- `backend/models/` (GLiNER weights), `venv/`, `venv_recovery/`, and the
  project-local `.runtime/` (portable Python interpreter, see the
  2026-08-16 environment-recovery entry above) are all gitignored —
  models reproducible via `scripts/download_gliner_model.py`,
  environments reproducible from `requirements.txt` (+
  `requirements-extraction.txt` once added) — none of it committed.
- Commit after every complete, tested change — not at end of day. See
  decisions-log.md's most recent entries for exactly what's changed and why.
- `init_db()` (`Base.metadata.create_all()`) only creates MISSING tables —
  it never alters an existing table when the model changes. The Render
  database has reset three times now (2026-07-28, 2026-07-30, and
  2026-08-06 — the second one under a new service/database name, so a
  full recreation, not an in-place wipe). Both Render services were
  upgraded to paid plans 2026-08-06 specifically to stop this recurring;
  root cause across all three resets still isn't conclusively confirmed.
  When a schema mismatch error appears (a column "does not exist"), run
  `python -m scripts.add_batch_label_column` first (safe, idempotent,
  adds the one column that keeps going missing) — only drop-and-recreate
  a table if the error is about a DIFFERENT missing column that script
  doesn't cover. Switch to Alembic migrations once real (non-synthetic)
  data exists and dropping tables is no longer safe.
- `load_immunization_reports.py` / `load_laboratory_reports.py` only
  INSERT — they never clear existing rows first. Running `--limit N` as
  a trial and then the full run without clearing in between leaves N
  duplicated rows behind (hit and fixed 2026-08-06). Run
  `python -m scripts.clear_immunization_and_lab_records` before any full
  reload that follows a limited trial run, every time.
- Real PDFs never go in git: `.gitignore` ignores `*.pdf` everywhere
  except directly inside `backend/tests/fixtures/` (synthetic fixtures
  only), and ignores `backend/data/Test Reports/` and
  `backend/data/pdf_test_reports/` (the 60 local test PDFs and their
  `ground_truth.csv`). After pulling the PDF change, re-run
  `pip install -r requirements.txt` once — it adds `pypdf`, and `httpx`
  for the endpoint tests.
- PowerShell one-liners with nested double-quoted strings inside
  `python -c "..."` are fragile — PowerShell doesn't treat `\"` as an
  escaped quote the way bash does. Write a short `.py` file instead of a
  multi-statement inline command, every time.
- Local startup no longer needs `$env:DATABASE_URL` typed per session —
  `backend/.env` (gitignored; copy from `.env.example`) holds it, loaded
  automatically by `app/db.py` via python-dotenv. Starting the backend is
  now just `cd backend` then `.\start_backend.ps1` — that script invokes
  `venv_recovery`'s interpreter directly by its full path and starts
  uvicorn itself (no `Activate.ps1` step, no PATH dependency; changed
  2026-08-16 from the old venv-activation pattern as part of the
  environment recovery — see the entry above). Two one-time local machine
  settings this depended on, both
  already done as of 2026-07-30 but worth knowing if set up on a NEW
  machine: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy
  RemoteSigned` (PowerShell blocks running any local .ps1 by default),
  and `Unblock-File -Path .\start_backend.ps1` (Windows flags any file
  downloaded from a browser, .ps1 included, as untrusted even after the
  execution policy is relaxed).

## How to resume in a new chat

Paste this file, or just say "continue the MedNexus public health project"
and share the GitHub repo: https://github.com/drsamehmomen7/mednexus-public-health
