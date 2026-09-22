# CLAUDE.md — Start Here

This file is the entry point for any Claude Code session working in
this repository. Read `CURRENT_STATUS.md` next for full current-state
detail; this file is the short, durable orientation layer.

## What this project is

MedNexus Public Health: extracts structured public-health data from
free-text reports (Notifiable Disease, Immunization, Laboratory),
with a mandatory human-review gate before anything is saved. Backend:
FastAPI + PostgreSQL (Render). Frontend: static HTML/CSS/JS, no build
step. Extraction: GLiNER (via OpenMed) + gazetteers + rule-based
fields, run entirely locally — no report text leaves the machine
during extraction.

## This project's place in MedNexus

This repository is **Track B (Domain Intelligence)** of the broader
MedNexus Seven architecture. It is an independent codebase — not
merged with, and with no code dependency on, the separate `MedNexus`
(Main) repository. The two are integrated only at the level of shared
architectural contracts. See `docs/mednexus-integration/` for the
authoritative cross-project documents:

- `architecture-crosswalk-v1.1.md` — how this project maps onto the
  MedNexus Seven journey (UNDERSTAND → PROTECT → EXTRACT →
  STANDARDIZE → ANALYZE → VISUALIZE → INDICATORS; INGEST is part of
  UNDERSTAND, not a separate stage).
- `clinical-semantic-context-contract-v0.1.md` and
  `clinical-extraction-contract-v0.1.md` — the frozen contracts this
  project's future integration with MedNexus Main's UNDERSTAND/PROTECT
  stages will be built against. Not yet implemented here — this
  project currently does its own lightweight report-type detection and
  has no PROTECT stage at all (see "Standing ground rules" below).
- `domain-intelligence-track-roadmap.md` — the approved roadmap:
  finish this project's current checkpoint, then Laboratory →
  Pathology → Radiology as future domain verticals.

**Do not treat MedNexus Main's code, patterns, or file layout as
authoritative for this repository.** This project's own established
patterns (below) are what a session here should follow. The
relationship is contractual, not structural.

## Standing ground rules (do not violate without an explicit decision on record)

1. **Mandatory human review before any save.** No code path may persist
   an extracted record without it. No exceptions.
2. **Per-field confidence with explicit source** (`model` / `gazetteer`
   / `rule_based`), not a single overall score.
3. **Terminology lookups (ICD-10/LOINC/CVX) are separate from
   extraction-time gazetteer matching.** Consulted only at save time. A
   terminology mapping error must never affect extraction recognition
   or confidence — see `docs/mednexus-integration/clinical-extraction-
   contract-v0.1.md` Section 3 for why this is now a formal MedNexus
   Seven requirement, not just local convention.
4. **Report accuracy only after measuring it.** Never estimate or
   assume a number. Document negative results explicitly (e.g. "no
   usable LOINC code exists for this test") rather than picking the
   closest wrong one.
5. **System-agnostic core.** Kuwait-specific reference data (regions,
   population, vaccine schedule) lives in `backend/data/*.json` /
   `population_strata`, never hardcoded into extraction or schema
   logic.
6. **No real patient data on this infrastructure.** Every report
   processed to date is synthetic. Introducing real PHI requires (a) a
   working PROTECT stage — not built yet — and (b) a separate,
   explicit decision with the Ministry of Health about approved
   infrastructure. Neither has happened. Do not write code that
   assumes otherwise.

## Working policy for this repository specifically

- **File edits**: when editing an existing file, inspect it directly,
  edit it directly, and verify with a diff before considering the
  change done — don't guess at contents from memory.
- **One step at a time**, verified before moving to the next, is the
  established working rhythm on this project (see
  `docs/decisions-log.md` for the pattern in practice across ICD-10,
  LOINC, and the Indicators layer work).
- **Docs stay in sync**: `README.md`, `CURRENT_STATUS.md`, and
  `docs/decisions-log.md` are living documents, updated at each
  meaningful milestone — not just when explicitly asked.
- **Git safety**: no force-push, no destructive reset/branch deletion,
  no commit or push unless explicitly requested for that specific
  change. Always show `git status`/diff before a checkpoint commit.

## Current checkpoint target

**Public Health Stable Scope Checkpoint v0.1.0** — a *scope* checkpoint
(not "complete," not "production ready," not "real-world validated").
See `CURRENT_STATUS.md` for exactly what remains before it's reached,
and `docs/mednexus-integration/domain-intelligence-track-roadmap.md`
Section B for its full definition and explicit exclusions.
