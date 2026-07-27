# Current Status — read this first in any new chat

Last updated: 2026-07-26

## Where we are right now

All 3 steps of the short-term roadmap are complete AND validated: data
store → Render deploy → Metabase. Metabase (Open Source, self-hosted,
free) runs locally from `C:\metabase\metabase.jar` via
`java --add-opens java.base/java.nio=ALL-UNNAMED -jar metabase.jar`
(needs Java 21+; not in git, not part of this repo), connected to the
Render Postgres instance.

Beyond the roadmap, phase 2 of the Notifiable Disease domain is also
done: the local backend now points at Render Postgres via
`$env:DATABASE_URL` (see Local dev routine below) — so any record saved
locally through the review UI appears in Metabase immediately, no manual
sync step. The dashboard ("Notifiable Disease Overview") now has 6
questions: Cases by Disease (bar), Cases by Region (bar), Cases by Sex
(pie), Cases by Age Group (bar, ordered 0-4→65+), Cases Over Time (line),
% Needing Review (number). 8 total records in Render Postgres (7 seeded
synthetic + 1 saved live through the local UI during testing).

**Immediate next step**: docx file upload for Notifiable Disease reports
— a new backend endpoint to extract text from an uploaded .docx (via
python-docx) and feed it into the existing extraction pipeline, plus a
file input on the frontend. Agreed but not started yet.

Also still undecided beyond that: (a) more report types (Immunization
next, reusing entity_selection.py/confidence.py), (b) terminology
normalization (ICD-10/LOINC/vaccine codes). Ask which once docx upload
is done, rather than assuming.

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
