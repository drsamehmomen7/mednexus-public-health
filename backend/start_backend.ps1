# One command to start the backend, every time.
#
# Usage: from C:\mednexus-public-health\backend, run:
#     .\start_backend.ps1
#
# What it does, in order:
#   1. Activates the venv
#   2. Starts uvicorn on port 8001
# DATABASE_URL itself comes from backend\.env (see .env.example) —
# db.py loads it automatically, nothing to set here.

Set-Location $PSScriptRoot
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8001
