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

from .db import get_db
from .models import AdminUser, AuthSession, Setting, Team, utcnow
from .tenancy import bind_team, unscoped

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


TEAM_HEADER = "X-Team-Id"


def _session_user(request: Request, db: Session) -> AdminUser | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    s = db.get(AuthSession, _th(token))
    if s is None or s.expires_at < utcnow():
        return None
    return s.user


def resolve_team(request: Request, db: Session, user: AdminUser) -> Team:
    """A team admin is always locked to its own team. A super admin picks a team with the
    X-Team-Id header (the team switcher); without one, the first active team is used."""
    if not user.is_super:
        team = db.get(Team, user.team_id) if user.team_id else None
        if team is None or not team.active:
            raise HTTPException(403, "Your team is not active - contact the super admin")
        return team
    raw = request.headers.get(TEAM_HEADER) or request.query_params.get("team")
    team = None
    if raw:
        try:
            team = db.get(Team, int(raw))
        except ValueError:
            team = db.query(Team).filter(Team.slug == raw).first()
    if team is None:
        team = db.query(Team).filter(Team.active.is_(True)).order_by(Team.id).first() or \
            db.query(Team).order_by(Team.id).first()
    if team is None:
        raise HTTPException(409, "No team exists yet - create one under Teams & logins")
    return team


def signed_in(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    """Signed in, CSRF-checked, NOT bound to a team (used by /auth endpoints)."""
    user = _session_user(request, db)
    if user is None:
        raise HTTPException(401, "Not signed in" if not request.cookies.get(COOKIE) else "Session expired")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-Requested-With") != "ffl":
        raise HTTPException(403, "Missing CSRF header")
    return user


def current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    """Signed-in admin; binds the request's database session to the admin's current team, so every
    query in the request only sees that team's data."""
    user = signed_in(request, db)
    team = resolve_team(request, db, user)
    bind_team(db, team.id)
    request.state.team = team
    return user


def super_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    user = current_admin(request, db)
    if not user.is_super:
        raise HTTPException(403, "Only the super admin can do this")
    return user


def arena_access(request: Request, db: Session = Depends(get_db)) -> str:
    """Arena (TV display) accepts either an admin session or a team's read-only arena token."""
    user = _session_user(request, db)
    if user is not None:
        bind_team(db, resolve_team(request, db, user).id)
        return "admin"
    t = request.query_params.get("token") or request.headers.get("X-Arena-Token")
    if t:
        h = _th(t)
        unscoped(db)
        rows = db.query(Setting).filter(Setting.key == "arena_token_hash").all()
        match = next((r for r in rows if r.value and hmac.compare_digest(h, str(r.value))), None)
        team = db.get(Team, match.team_id) if match else None
        if team and team.active:
            bind_team(db, team.id)
            return "arena"
    raise HTTPException(401, "Arena access requires sign-in or a valid display link")


def new_arena_token() -> tuple[str, str]:
    t = secrets.token_urlsafe(24)
    return t, _th(t)
