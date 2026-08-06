# MedNexus — Public Health Report Intelligence

Extracts structured data from public health reports (notifiable disease
cases, immunization records, laboratory reports, syndromic surveillance,
outbreak reports) and prepares it for statistics and indicators.

Independent project, shares visual identity with the MedNexus
de-identification tool.

## Current status

Notifiable Disease, Immunization, AND Laboratory report types are all
end-to-end complete and measured: extraction (GLiNER + gazetteers +
rule-based fields), confidence reporting, save to Postgres, each with
its own dashboard — all backed by 126 passing tests and a confirmed
100% field accuracy across each type's own 500-report synthetic run.
An Indicators layer sits above all three (vaccination coverage % and
test positivity % by region), with its own dashboard page. The frontend
also has real document upload (DOCX/TXT) with automatic report-type
detection, a batch/cohort system for grouping saved records, JSON/CSV
export, and a full visual redesign (brand identity, landing page, four
dashboards). ICD-10 terminology normalization is in progress for
Notifiable Disease; LOINC and vaccine codes are next. See
`CURRENT_STATUS.md` for exactly where things stand and what's next.

## Run the prototype locally

No installation needed for the frontend by itself, but the full pipeline
(extraction) needs two servers running at the same time, in two separate
terminals — plus a third terminal, opened as needed (not left running),
for anything else you actually type (git, one-off scripts, pytest).
Terminals 1 and 2 are permanently busy running their server process and
won't accept typed input while running.

### Every time you reopen VSCode

**Terminal 1 — backend (port 8001):**
```powershell
cd C:\mednexus-public-health\backend
.\start_backend.ps1
```
`start_backend.ps1` activates the venv and starts uvicorn in one step.
`DATABASE_URL` no longer needs typing per session — it's read from
`backend/.env` (gitignored; copy from `.env.example` on a new machine),
so saves and dashboard queries hit the same Render Postgres instance
automatically. A real `$env:DATABASE_URL`, if one happens to be set,
still overrides the `.env` file.

**Terminal 2 — frontend (port 5500):**
```powershell
cd C:\mednexus-public-health\frontend\prototype
python -m http.server 5500
```

Leave both running, then open `http://127.0.0.1:5500` in the browser for
the extraction page, `http://127.0.0.1:5500/dashboard.html` for the
Notifiable Disease dashboard, `immunization-dashboard.html` /
`laboratory-dashboard.html` for their own dashboards, or
`indicators-dashboard.html` for the cross-report Indicators page.

(Metabase was used briefly and dropped in favour of the custom dashboard
pages — see `docs/decisions-log.md`, 2026-07-27.)
Do NOT open any HTML file directly as a `file://` path — the browser
blocks requests from local files to localhost servers, so the extract
button (and every dashboard's data fetch) will silently fail.

One-time setup (already done, listed here for reference): `python -m venv
venv` inside `backend/`, then `pip install -r requirements.txt` and
`pip install "openmed[gliner]"`, then `python scripts/download_gliner_model.py`.
Also one-time on a new machine: `Set-ExecutionPolicy -Scope CurrentUser
-ExecutionPolicy RemoteSigned` (PowerShell blocks local `.ps1` scripts by
default) and `Unblock-File -Path .\start_backend.ps1` (Windows flags
downloaded `.ps1` files as untrusted even after that policy change).

## Project structure

```
docs/                  Living architecture docs, decisions log, report type definitions
frontend/prototype/    Static UI prototype (HTML/CSS/JS, no build step) + four dashboards
backend/               FastAPI app, extraction pipeline, gazetteers, scripts, tests
backend/tests/         126 pytest tests covering extraction, negation, gazetteers, schema
                        (does not yet cover the Indicators layer or ICD-10 lookup — see
                        CURRENT_STATUS.md "What's not built yet")
```

## Documentation

See `docs/architecture.md` for the current plan and `docs/decisions-log.md`
for why each structural choice was made.
