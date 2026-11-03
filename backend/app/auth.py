"""Admin authentication: scrypt password hashing, server-side sessions in an HttpOnly cookie,
CSRF header check on mutating requests, simple login throttling, and a read-only Arena token."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time as _time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import load_raw
from .db import get_db
from .models import AdminUser, AuthSession, utcnow

COOKIE = "ffl_session"
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12"))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=64)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, s, h = stored.split("$")
        dk = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2 ** 14, r=8, p=1, dklen=64)
        return hmac.compare_digest(dk, base64.b64decode(h))
    except Exception:
        return False


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: AdminUser) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=_th(token), user_id=user.id, expires_at=utcnow() + timedelta(hours=SESSION_HOURS)))
    db.query(AuthSession).filter(AuthSession.expires_at < utcnow()).delete()
    return token


def end_session(db: Session, token: str | None):
    if token:
        db.query(AuthSession).filter(AuthSession.token_hash == _th(token)).delete()


_attempts: dict[str, deque] = defaultdict(deque)


def throttle(key: str, limit: int = 8, window: int = 300):
    """Raise 429 when there were too many FAILED attempts for this key in the window."""
    q, now = _attempts[key], _time.time()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many failed login attempts. Try again in a few minutes.")


def record_failure(key: str):
    _attempts[key].append(_time.time())


def clear_failures(key: str):
    _attempts.pop(key, None)


def current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Not signed in")
    s = db.get(AuthSession, _th(token))
    if s is None or s.expires_at < utcnow():
        raise HTTPException(401, "Session expired")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-Requested-With") != "ffl":
        raise HTTPException(403, "Missing CSRF header")
    return s.user


def arena_access(request: Request, db: Session = Depends(get_db)) -> str:
    """Arena (TV display) accepts either an admin session or the read-only arena token."""
    token = request.cookies.get(COOKIE)
    if token:
        s = db.get(AuthSession, _th(token))
        if s and s.expires_at >= utcnow():
            return "admin"
    t = request.query_params.get("token") or request.headers.get("X-Arena-Token")
    stored = load_raw(db).get("arena_token_hash")
    if t and stored and hmac.compare_digest(_th(t), stored):
        return "arena"
    raise HTTPException(401, "Arena access requires sign-in or a valid display link")


def new_arena_token() -> tuple[str, str]:
    t = secrets.token_urlsafe(24)
    return t, _th(t)
