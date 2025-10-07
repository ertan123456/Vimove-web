#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv || true
source .venv/bin/activate

python -m pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt

echo "Server starting: http://127.0.0.1:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
