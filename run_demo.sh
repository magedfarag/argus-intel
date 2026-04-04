#!/usr/bin/env bash
set -euo pipefail
if [ ! -d ".venv" ]; then
  python -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt
exec uvicorn app.main:app --reload
