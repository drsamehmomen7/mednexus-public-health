# Current Status — read this first in any new chat

Last updated: 2026-07-26

## Where we are right now

All 3 steps of the short-term roadmap are now complete: data store →
Render deploy → Metabase. Metabase (Open Source, self-hosted, free) runs
locally from `C:\metabase\metabase.jar` via
`java --add-opens java.base/java.nio=ALL-UNNAMED -jar metabase.jar`
(needs Java 21+; not in git, not part of this repo), connected to the
Render Postgres instance. Dashboard "Notifiable Disease Overview" has 4
saved questions: Cases by Disease, Cases by Region, % Needing Review,
Cases Over Time. All currently show 1 row — only the single test record
(id=1) exists on Render so far.

**Immediate next step**: seed a handful more synthetic notifiable-disease
records (varying disease, region, needed_review) so the dashboard
actually shows shape — then decide what's next: more report types
(Immunization, etc.) or terminology normalization.

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
- Dashboard only has 1 real row so far — needs more seeded synthetic data.
- Frontend is not yet pointed at the deployed Render URL — still hardcoded
  to `http://127.0.0.1:8001` in `frontend/prototype/app.js`.

## Local dev routine (two terminals, every session)

See `README.md` — backend on port 8001, frontend static server on 5500,
never open `index.html` as a `file://` path (CORS/private-network blocking).

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
