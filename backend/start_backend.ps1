# One command to start the backend, every time.
#
# Usage: from C:\mednexus-public-health\backend, run:
#     .\start_backend.ps1
#
# What it does, in order:
#   1. Invokes the venv_recovery interpreter directly (no activation, no PATH)
#   2. Starts uvicorn on port 8002
# DATABASE_URL itself comes from backend\.env (see .env.example) —
# db.py loads it automatically, nothing to set here.
# Port convention: MedNexus Main uses 8001, Public Health uses 8002.

Set-Location $PSScriptRoot
.\venv_recovery\Scripts\python.exe -m uvicorn app.main:app --reload --port 8002
