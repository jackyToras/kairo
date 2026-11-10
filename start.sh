#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  uv venv .venv
  uv pip install --python .venv/bin/python -e ".[dev]"
fi

if [ ! -d "frontend/dist" ]; then
  (cd frontend && npm install && npm run build)
fi

echo "Starting Kairo on http://localhost:8000 ..."
.venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
