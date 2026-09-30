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
its own dashboard — all backed by 263 passing tests (plus 2 expected
failures that mark known PDF text limits) and a confirmed 100% field
accuracy across each type's own 500-report synthetic run. An Indicators
layer sits above all three (vaccination coverage % and test positivity %
by region), with its own dashboard page. The frontend also has real
document upload (DOCX, TXT, and text-based PDF — no OCR, so scanned
PDFs aren't read) with automatic report-type detection, a batch/cohort
system for grouping saved records, JSON/CSV export, and a full visual
redesign (brand identity, landing page, four
dashboards). Terminology normalization is done for all three report
types: ICD-10 (Notifiable Disease), LOINC (Laboratory) and CVX
(Immunization) codes are filled in at save time, each confirmed against
a real save (9 of the 54 ICD-10 entries are still flagged for clinical
review). See `CURRENT_STATUS.md` for exactly where things stand and
what's next.

## Run the prototype locally

No installation needed for the frontend by itself, but the full pipeline
(extraction) needs two servers running at the same time, in two separate
terminals — plus a third terminal, opened as needed (not left running),
for anything else you actually type (git, one-off scripts, pytest).
Terminals 1 and 2 are permanently busy running their server process and
won't accept typed input while running.

### Every time you reopen VSCode

**Terminal 1 — backend (port 8002):**
```powershell
cd D:\mednexus-public-health\backend
.\start_backend.ps1
```
`start_backend.ps1` runs `venv_recovery`'s Python by its full path (no
activation step) and starts uvicorn in one step.
`DATABASE_URL` no longer needs typing per session — it's read from
`backend/.env` (gitignored; copy from `backend/env.example` on a new machine),
so saves and dashboard queries hit the same Render Postgres instance
automatically. A real `$env:DATABASE_URL`, if one happens to be set,
still overrides the `.env` file.

**Terminal 2 — frontend (port 5500):**
```powershell
cd D:\mednexus-public-health
.\backend\venv_recovery\Scripts\python.exe frontend\serve_dev.py
```
`serve_dev.py` is `python -m http.server` plus a `Cache-Control: no-cache`
header, so edited CSS/JS show up on a normal reload. It always serves
`frontend/prototype/` on `127.0.0.1:5500`, whatever folder it is started
from. There is still no live-reload: a tab left open keeps the JS it
loaded until it is reloaded.

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

One-time setup (already done, listed here for reference; why it looks
like this: `docs/decisions-log.md`, 2026-08-16). The backend runs on a
project-local Python, not a system install: `.runtime\Python310` is
python.org's embeddable Python 3.10.11 with pip (PyPA's `get-pip.py`) and
`virtualenv` added — the embeddable package has no `venv` module. From
the repo root, `.runtime\Python310\python.exe -m virtualenv
backend\venv_recovery` creates the environment; then, with
`backend\venv_recovery\Scripts\python.exe -m pip`, install
`-r backend\requirements.txt` and `"openmed[gliner]"`, and run
`scripts\download_gliner_model.py` from `backend\`. Both folders are
gitignored. Also one-time on a new machine: `Set-ExecutionPolicy -Scope
CurrentUser -ExecutionPolicy RemoteSigned` (PowerShell blocks local `.ps1` scripts by
default) and `Unblock-File -Path .\start_backend.ps1` (Windows flags
downloaded `.ps1` files as untrusted even after that policy change).

After pulling the PDF-upload change, re-run
`pip install -r requirements.txt` once: it adds `pypdf` (PDF text
extraction) and `httpx` (needed by the endpoint tests).
`backend/venv_recovery` already has both.

## Project structure

```
docs/                  Living architecture docs, decisions log, report type definitions
frontend/prototype/    Static UI prototype (HTML/CSS/JS, no build step) + four dashboards
backend/               FastAPI app, extraction pipeline, gazetteers, scripts, tests
backend/tests/         263 pytest tests (+2 expected xfails) covering extraction, negation,
                        gazetteers, schema, and document ingestion (DOCX/TXT/PDF parsing
                        and the /reports/parse-document endpoint); does not yet cover the
                        Indicators layer or ICD-10 lookup — see CURRENT_STATUS.md
                        "What's not built yet"
backend/tests/fixtures/ Synthetic PDF fixtures (README inside). Real PDFs are gitignored
                        everywhere else.
```

## Documentation

See `docs/architecture.md` for the current plan and `docs/decisions-log.md`
for why each structural choice was made.
