# MedNexus — Public Health Report Intelligence

Extracts structured data from public health reports (notifiable disease
cases, immunization records, laboratory reports, syndromic surveillance,
outbreak reports) and prepares it for statistics and indicators.

Independent project, shares visual identity with the MedNexus
de-identification tool.

## Current status

Prototype phase — static UI only, no backend yet.

## Run the prototype locally

No installation needed for the frontend by itself, but the full pipeline
(extraction) needs both servers running at the same time, in two separate
terminals.

### Every time you reopen VSCode

**Terminal 1 — backend (port 8001):**
```powershell
cd C:\mednexus-public-health\backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8001
```

**Terminal 2 — frontend (port 5500):**
```powershell
cd C:\mednexus-public-health\frontend\prototype
python -m http.server 5500
```

**Terminal 3 — Metabase (port 3000, analytics dashboard):**
```powershell
cd C:\metabase
java --add-opens java.base/java.nio=ALL-UNNAMED -jar metabase.jar
```
Not part of this repo (lives in `C:\metabase`, not tracked in git) and
not required for the extraction pipeline itself — only needed when you
want to view/update the indicators dashboard. Requires Java 21+ (`java
-version` to check). Once running, open `http://localhost:3000`.

Leave both running, then open `http://127.0.0.1:5500` in the browser.
Do NOT open `index.html` directly as a `file://` path — the browser blocks
requests from local files to localhost servers, so the extract button will
silently fail.

One-time setup (already done, listed here for reference): `python -m venv
venv` inside `backend/`, then `pip install -r requirements.txt` and
`pip install "openmed[gliner]"`, then `python scripts/download_gliner_model.py`.

## Project structure

```
docs/                  Living architecture docs, decisions log, report type definitions
frontend/prototype/    Static UI prototype (HTML/CSS/JS, no build step)
backend/               Not started yet
tests/                 Not started yet
```

## Documentation

See `docs/architecture.md` for the current plan and `docs/decisions-log.md`
for why each structural choice was made.
