#!/bin/sh
set -eu

echo "[backend] waiting for postgres..."
python - <<'PY'
import os
import time
from urllib.parse import urlparse

import psycopg

database_url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
deadline = time.time() + 90
last_error = None

while time.time() < deadline:
    try:
        with psycopg.connect(database_url):
            print("[backend] database is ready")
            raise SystemExit(0)
    except Exception as exc:  # noqa: BLE001
        last_error = exc
        time.sleep(2)

raise SystemExit(f"[backend] database not ready: {last_error}")
PY

echo "[backend] running migrations..."
alembic upgrade head

echo "[backend] seeding defaults..."
python scripts/seed_defaults.py

echo "[backend] starting api..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
