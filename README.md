# MedNexus — Public Health Report Intelligence

Extracts structured data from public health reports (notifiable disease
cases, immunization records, laboratory reports, syndromic surveillance,
outbreak reports) and prepares it for statistics and indicators.

Independent project, shares visual identity with the MedNexus
de-identification tool.

## Current status

Notifiable Disease AND Immunization report types are both end-to-end
complete and measured: extraction (GLiNER + gazetteers + rule-based
fields), confidence reporting, save to Postgres, each with its own
dashboard — all backed by 120 passing tests and a confirmed 100% field
accuracy across each type's own 500-report synthetic run. The frontend
also has real document upload (DOCX/TXT) with automatic report-type
detection, a batch/cohort system for grouping saved records, JSON/CSV
export, and a full visual redesign (brand identity, landing page,
both dashboards). See `CURRENT_STATUS.md` for exactly where things
stand and what's next.

## Run the prototype locally

No installation needed for the frontend by itself, but the full pipeline
(extraction) needs both servers running at the same time, in two separate
terminals.

### Every time you reopen VSCode

**Terminal 1 — backend (port 8001):**
```powershell
cd C:\mednexus-public-health\backend
.\venv\Scripts\Activate.ps1
$env:DATABASE_URL = "<Render external Postgres connection string>"
python -m uvicorn app.main:app --reload --port 8001
```
The `DATABASE_URL` line points the local backend at the same Render
Postgres instance Metabase reads from, so anything saved locally through
the review UI shows up on the dashboard immediately. Without it, the
backend falls back to a local Postgres URL that isn't set up, and saves
fail. This only lasts for the life of the terminal — set it again each
time you open a new Terminal 1. (Connection string omitted here
deliberately — it contains a password; keep it out of anything committed
to git.)

**Terminal 2 — frontend (port 5500):**
```powershell
cd C:\mednexus-public-health\frontend\prototype
python -m http.server 5500
```

Leave both running, then open `http://127.0.0.1:5500` in the browser for
the extraction page, or `http://127.0.0.1:5500/dashboard.html` for the
indicators dashboard.

(Metabase was used briefly and dropped in favour of the custom dashboard
page — see `docs/decisions-log.md`, 2026-07-27. No third terminal needed.)
Do NOT open `index.html` directly as a `file://` path — the browser blocks
requests from local files to localhost servers, so the extract button will
silently fail.

One-time setup (already done, listed here for reference): `python -m venv
venv` inside `backend/`, then `pip install -r requirements.txt` and
`pip install "openmed[gliner]"`, then `python scripts/download_gliner_model.py`.

## Project structure

```
docs/                  Living architecture docs, decisions log, report type definitions
frontend/prototype/    Static UI prototype (HTML/CSS/JS, no build step) + dashboard
backend/               FastAPI app, extraction pipeline, gazetteers, scripts, tests
backend/tests/         69 pytest tests covering extraction, negation, gazetteers, schema
```

## Documentation

See `docs/architecture.md` for the current plan and `docs/decisions-log.md`
for why each structural choice was made.
