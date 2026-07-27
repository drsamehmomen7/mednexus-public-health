# Current Status — read this first in any new chat

Last updated: 2026-07-26

## Where we are right now

All 3 steps of the short-term roadmap are complete AND validated: data
store → Render deploy → Metabase. Metabase (Open Source, self-hosted,
free) runs locally from `C:\metabase\metabase.jar` via
`java --add-opens java.base/java.nio=ALL-UNNAMED -jar metabase.jar`
(needs Java 21+; not in git, not part of this repo), connected to the
Render Postgres instance.

Beyond the roadmap, the Notifiable Disease domain has had two extra
phases of work, both driven by the user pushing back that a working
pipeline isn't the same as a decision-ready one:

- **Phase 2 (live sync)**: local backend now points at Render Postgres
  via `$env:DATABASE_URL` (see Local dev routine below) — any record
  saved locally through the review UI appears in Metabase immediately.
- **Phase 3 (dashboard v2)**: dashboard "Notifiable Disease Overview" now
  has 7 questions with real chart types (bar/pie/line, not flat tables):
  Cases by Disease, Cases by Region, Cases by Sex, Cases by Age Group,
  Cases Over Time, % Needing Review, and Rate per 100k by Region (joined
  against a new `region_population` reference table — real public 2025
  Kuwait governorate population estimates, not synthetic). A
  dashboard-level "Disease" filter cross-filters 6 of the 7 questions at
  once. Explicitly not attempted: ethnicity breakdown (sensitive
  attribute, deliberately uncollected) or a region choropleth map
  (Metabase has no native support for custom Kuwait boundaries).

Docx file upload — previously the agreed next step — was **descoped
entirely**, not deferred: the user confirmed the real workflow is
free-text only (a clinician types or pastes a report, extracts, saves),
with no file upload and no live hospital system integration.

**Open question, not yet decided**: is the Notifiable Disease domain now
mature enough to be worth showing a decision-maker, justifying a move to
more report types (Immunization next) — or does it need further
depth first? Ask at the start of the next session rather than assuming
either way.

## What's already working (locally)

- Full extraction pipeline for **Notifiable Disease** report type: raw
  text → GLiNER-based NER + rule-based fields → confidence report →
  editable review UI → save to Postgres.
- 41 backend tests passing (`pytest tests/ -v` from `backend/`).
- Negation-aware extraction (won't pick a "ruled out" diagnosis) and
  needed_review flagging (low-confidence fields flagged for a human).
- Frontend prototype (static HTML/CSS/JS) at `frontend/prototype/`,
  green-themed, distinct from the sibling de-identification tool.

## What's not built yet

- Immunization, Laboratory, Syndromic, Outbreak report types (schemas
  exist in `backend/app/schemas/`, no extraction logic yet — reuse
  `entity_selection.py` and `confidence.py`, don't reimplement them).
- Terminology normalization (ICD-10, LOINC, vaccine codes).
- File upload of any kind — deliberately out of scope; workflow is
  free-text only (see Where we are right now).
- Frontend is not yet pointed at the deployed Render URL — still hardcoded
  to `http://127.0.0.1:8001` in `frontend/prototype/app.js`.

## Local dev routine (three terminals, every session)

See `README.md`. Terminal 1 (backend, port 8001) now needs
`$env:DATABASE_URL` set to the Render external connection string before
starting uvicorn, so local saves land in the same Postgres Metabase
reads from — otherwise it falls back to a local Postgres URL that
doesn't exist. Terminal 2: frontend static server, port 5500. Terminal 3:
Metabase, port 3000 (optional — only needed to view/update the
dashboard). Never open `index.html` as a `file://` path (CORS/private-
network blocking).

## Key ground rules established (see docs/decisions-log.md for full reasoning)

- Core schemas stay system-agnostic — no country/ministry-specific logic
  in extraction or normalization. Ministry integrations (DHIS2, etc.) are
  optional adapters layered on top, never a dependency.
- Never put real patient data on Render or any shared/cloud service —
  synthetic data only until access control is properly designed.
- `backend/models/` (GLiNER weights) and `venv/` are gitignored —
  reproducible via `scripts/download_gliner_model.py`, not committed.
- Commit after every complete, tested change — not at end of day. See
  decisions-log.md's most recent entries for exactly what's changed and why.

## How to resume in a new chat

Paste this file, or just say "continue the MedNexus public health project"
and share the GitHub repo: https://github.com/drsamehmomen7/mednexus-public-health
