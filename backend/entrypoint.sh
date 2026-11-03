#!/bin/sh
set -e

# Optional first-boot admin (non-interactive). Password must be ≥ 10 chars.
if [ -n "${ADMIN_USERNAME:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  python - <<'PY'
import os
from app import models  # noqa: F401
from app.auth import hash_password
from app.db import Base, SessionLocal, engine
from app.models import AdminUser

Base.metadata.create_all(engine)
username = os.environ["ADMIN_USERNAME"]
password = os.environ["ADMIN_PASSWORD"]
if len(password) < 10:
    raise SystemExit("ADMIN_PASSWORD must be at least 10 characters")
with SessionLocal() as db:
    user = db.query(AdminUser).filter_by(username=username).first()
    if user:
        print(f"Admin '{username}' already exists — leaving password unchanged")
    else:
        db.add(AdminUser(username=username, password_hash=hash_password(password)))
        db.commit()
        print(f"Admin '{username}' created")
PY
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
