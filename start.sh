#!/usr/bin/env bash
# Start the FireFlink 4.0 League Tracker on http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d frontend/dist ]; then (cd frontend && npm install && npm run build); fi
cd backend
exec .venv/bin/uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
