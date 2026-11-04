"""REST API. Every league-data endpoint requires the admin session (Arena: session or display token)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..config import DEFAULTS, EDITABLE_KEYS, NEW_TEAM_DEFAULTS, load_config, load_raw, save_setting, to_config
from ..constants import (CONTRACT_STATUSES, CURRENCY_OPTIONS, DEMO_ON_OPTIONS, DEMO_STATUSES, DEMO_TYPES,
                         OPPORTUNITY_OPTIONS, POC_STATUSES)
from ..db import get_db
from ..models import (ROLE_SUPER, ROLE_TEAM, ActivityEvent, AdminUser, AuditLog, AuthSession, AwardFinalization,
                      BDMember, DayClosure, DemoRecord, ExchangeRate, ImportHistory, RevenueRecord, Setting, Team)
from ..tenancy import bind_team
from ..services import exporter as X
from ..services import gsheet as G
from ..services import importer as I
from ..services import league as L
from ..services import records as R
from ..services import snapshot as S
from .serializers import demo_out, revenue_out

router = APIRouter(prefix="/api")
Admin = Depends(auth.current_admin)
Super = Depends(auth.super_admin)
SignedIn = Depends(auth.signed_in)


def _commit(db: Session):
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def _v(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except R.ValidationError as e:
        raise HTTPException(422, {"errors": e.errors})


# ----------------------------------------------------------------------------------------- live sheet mode
SHEET_MSG = ("Live Google Sheet mode is on - the sheet is the source of truth. Make this change in the Google Sheet; "
             "it appears here within a minute.")
DEMO_APP_ONLY = {"poc_started_on", "poc_remarks"}
REV_APP_ONLY = {"fx_rate_override", "fx_rate_override_date"}


def live_mode(db: Session) -> bool:
    raw = load_raw(db)
    return bool(raw.get("gsheet_sync_enabled") and raw.get("gsheet_url"))


def _guard_live(db: Session):
    if live_mode(db):
        raise HTTPException(409, SHEET_MSG)


def _guard_live_update(db: Session, rec, payload: dict, fields: list[str], app_only: set[str]):
    if not live_mode(db):
        return
    def n(k, v):
        v = R._ser(v)
        if v in (None, ""):
            return None
        if k == "demo_time":
            return str(v)[:5]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return round(float(v), 4)
        return str(v)

    current = R.snapshot_of(rec, fields)
    changed = [k for k in fields if k not in app_only and k in payload and n(k, payload[k]) != n(k, current.get(k))]
    if changed:
        raise HTTPException(409, f"{SHEET_MSG} (fields: {', '.join(changed)})")


def sync_public(db: Session) -> dict:
    raw = load_raw(db)
    st = raw.get(G.STATUS_KEY) or {}
    return {"enabled": live_mode(db), "url": raw.get("gsheet_url"), "interval": raw.get("gsheet_sync_interval_seconds"),
            "last_success": st.get("last_success"), "last_attempt": st.get("last_attempt"),
            "last_change": st.get("last_change"), "error": st.get("error")}


# ----------------------------------------------------------------------------------------- auth
class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else '?'}:{body.username.lower()}"
    auth.throttle(key)
    user = db.query(AdminUser).filter(AdminUser.username == body.username).first()
    if not user or not auth.verify_password(body.password, user.password_hash):
        auth.record_failure(key)
        raise HTTPException(401, "Invalid username or password")
    if not user.is_super and (user.team is None or not user.team.active):
        raise HTTPException(403, "Your team is not active - contact the super admin")
    auth.clear_failures(key)
    token = auth.create_session(db, user)
    bind_team(db, auth.resolve_team(request, db, user).id)
    R.audit(db, user.username, "auth", user.id, "login")
    _commit(db)
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax", secure=auth.COOKIE_SECURE,
                        max_age=auth.SESSION_HOURS * 3600, path="/")
    return {"username": user.username, "role": user.role}


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth.end_session(db, request.cookies.get(auth.COOKIE))
    _commit(db)
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


def _team_out(t: Team) -> dict:
    return {"id": t.id, "name": t.name, "slug": t.slug, "active": t.active}


@router.get("/auth/me")
def me(request: Request, user: AdminUser = SignedIn, db: Session = Depends(get_db)):
    team = auth.resolve_team(request, db, user)
    teams = db.query(Team).order_by(Team.name).all() if user.is_super else [team]
    return {"username": user.username, "role": user.role, "is_super": user.is_super,
            "team": _team_out(team), "teams": [_team_out(t) for t in teams]}


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


@router.post("/auth/password")
def change_password(body: PasswordIn, request: Request, user: AdminUser = SignedIn, db: Session = Depends(get_db)):
    if not auth.verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    u = db.get(AdminUser, user.id)
    u.password_hash = auth.hash_password(body.new_password)
    bind_team(db, auth.resolve_team(request, db, user).id)
    R.audit(db, user.username, "auth", user.id, "password_change")
    _commit(db)
    return {"ok": True}


# ----------------------------------------------------------------------------------------- meta
@router.get("/meta")
def meta(user: AdminUser = Admin, db: Session = Depends(get_db)):
    cfg = load_config(db)
    bds = db.query(BDMember).order_by(BDMember.display_order, BDMember.name).all()
    dom = sorted({x for (x,) in db.query(DemoRecord.domain).distinct() if x} |
                 {x for (x,) in db.query(RevenueRecord.domain).distinct() if x})
    cty = sorted({x for (x,) in db.query(DemoRecord.country).distinct() if x} |
                 {x for (x,) in db.query(DemoRecord.city).distinct() if x} |
                 {x for (x,) in db.query(RevenueRecord.country).distinct() if x})
    cur = sorted(set(CURRENCY_OPTIONS) | {x for (x,) in db.query(RevenueRecord.currency).distinct() if x} |
                 {r.currency for r in db.query(ExchangeRate).all()})
    return {
        "bds": [{"id": b.id, "name": b.name, "active": b.active} for b in bds],
        "demo_types": DEMO_TYPES, "demo_statuses": DEMO_STATUSES, "poc_statuses": POC_STATUSES,
        "demo_on_options": DEMO_ON_OPTIONS, "contract_statuses": CONTRACT_STATUSES,
        "opportunity_options": OPPORTUNITY_OPTIONS, "currencies": cur, "domains": dom, "countries": cty,
        "regions": list(cfg.f2f_regions.keys()), "timezone": cfg.timezone,
        "live_mode": live_mode(db), "sheet_url": load_raw(db).get("gsheet_url"),
        "require_qualified": cfg.require_qualified, "f2f_from_location": cfg.f2f_from_location,
    }


# ----------------------------------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(user: AdminUser = Admin, db: Session = Depends(get_db)):
    snap = S.build(db)
    snap["activity"] = _activity(db, 25)
    snap["sync"] = sync_public(db)
    return snap


def _activity(db: Session, limit: int, bd_id: int | None = None) -> list[dict]:
    q = db.query(ActivityEvent)
    if bd_id:
        q = q.filter(ActivityEvent.bd_id == bd_id)
    return [{"id": a.id, "at": a.at.isoformat() + "Z", "kind": a.kind, "message": a.message, "bd_id": a.bd_id,
             "actor": a.actor, "meta": a.meta} for a in q.order_by(ActivityEvent.id.desc()).limit(limit)]


@router.get("/activity")
def activity(limit: int = 50, bd_id: int | None = None, user: AdminUser = Admin, db: Session = Depends(get_db)):
    return _activity(db, min(limit, 500), bd_id)


@router.get("/arena")
def arena(_: str = Depends(auth.arena_access), db: Session = Depends(get_db)):
    snap = S.build(db)
    snap["activity"] = _activity(db, 8)
    snap["revenue"].pop("by_domain", None)
    st = sync_public(db)
    snap["sync"] = {k: st[k] for k in ("enabled", "last_success", "error")}
    return snap


@router.get("/bd/{bd_id}")
def bd_performance(bd_id: int, user: AdminUser = Admin, db: Session = Depends(get_db)):
    bd = db.get(BDMember, bd_id)
    if not bd:
        raise HTTPException(404, "BD not found")
    snap = S.build(db)
    cfg = load_config(db)
    demos = db.query(DemoRecord).filter(DemoRecord.bd_id == bd_id, DemoRecord.deleted_at.is_(None)).all()
    rates = db.query(ExchangeRate).all()
    revs = db.query(RevenueRecord).filter(RevenueRecord.bd_id == bd_id, RevenueRecord.deleted_at.is_(None)).all()
    row = next((r for r in snap["overall"] if r["bd_id"] == bd_id), None)
    daily = snap["daily"]["per_bd"].get(bd_id)
    rev = next((r for r in snap["revenue"]["per_bd"] if r["bd_id"] == bd_id), None)
    weekly = [{"label": w["label"], "start": w["start"], "end": w["end"], "state": w["state"],
               "total": next((s["total"] for s in w["standings"] if s["bd_id"] == bd_id), 0),
               "rank": next((s["rank"] for s in w["standings"] if s["bd_id"] == bd_id), None)}
              for w in snap["weeks"]]
    f2f_row = next((r for r in snap["f2f"]["leaderboard"] if r["bd_id"] == bd_id), None)
    return {
        "bd": {"id": bd.id, "name": bd.name, "active": bd.active},
        "league": snap["league"],
        "standing": row, "daily": daily, "revenue": rev, "weekly": weekly,
        "f2f_challenge": f2f_row,
        "badges": L.badges_for(row["total"] if row else 0, f2f_row["f2f"] if f2f_row else 0,
                               daily["best_streak"] if daily else 0),
        "counts": {
            "scheduled": sum(1 for d in demos if d.status == "Scheduled"),
            "completed": sum(1 for d in demos if d.status == "Completed"),
            "completed_unqualified": sum(1 for d in demos if L.is_completed_unqualified(d, cfg)),
            "no_show": sum(1 for d in demos if d.status == "No Show"),
            "pipeline": sum(1 for d in demos if d.status == "Pipeline"),
        },
        "poc": [demo_out(d, cfg) for d in demos if d.status in POC_STATUSES],
        "demos": [demo_out(d, cfg) for d in sorted(demos, key=lambda x: (x.demo_date or date.min), reverse=True)],
        "revenue_records": [revenue_out(r, L.evaluate_revenue(r, cfg, rates)) for r in revs],
        "activity": _activity(db, 20, bd_id),
        "total_bds": len(snap["overall"]),
    }


# ----------------------------------------------------------------------------------------- demos
class DemoIn(BaseModel):
    sl_no: int | None = None
    bd_id: int
    customer_name: str
    domain: str | None = None
    country: str | None = None
    city: str | None = None
    demo_type: str | None = None
    demo_on: str | None = None
    demo_date: date | None = None
    demo_time: str | None = None
    time_zone: str | None = None
    status: str
    qualified: str | None = None
    poc_started_on: date | None = None
    poc_remarks: str | None = None


@router.get("/demos")
def list_demos(deleted: bool = False, user: AdminUser = Admin, db: Session = Depends(get_db)):
    cfg = load_config(db)
    q = db.query(DemoRecord)
    q = q.filter(DemoRecord.deleted_at.isnot(None)) if deleted else q.filter(DemoRecord.deleted_at.is_(None))
    rows = q.all()
    rows.sort(key=lambda d: (d.demo_date is None, d.demo_date or date.min, d.demo_time or datetime.min.time()),
              reverse=False)
    return [demo_out(d, cfg) for d in rows]


def _demo_payload(body: DemoIn) -> dict:
    d = body.model_dump()
    d["demo_date"] = body.demo_date.isoformat() if body.demo_date else None
    d["poc_started_on"] = body.poc_started_on.isoformat() if body.poc_started_on else None
    return d


@router.post("/demos")
def create_demo(body: DemoIn, user: AdminUser = Admin, db: Session = Depends(get_db)):
    _guard_live(db)
    if body.sl_no is None:
        body.sl_no = (max((x for (x,) in db.query(DemoRecord.sl_no).all() if x), default=0)) + 1
    rec = _v(R.create_demo, db, _demo_payload(body), user.username)
    _commit(db)
    return demo_out(rec, load_config(db))


@router.put("/demos/{demo_id}")
def update_demo(demo_id: str, body: DemoIn, user: AdminUser = Admin, db: Session = Depends(get_db)):
    rec = db.get(DemoRecord, demo_id)
    if not rec or rec.deleted_at:
        raise HTTPException(404, "Demo not found")
    payload = _demo_payload(body)
    _guard_live_update(db, rec, payload, R.DEMO_FIELDS, DEMO_APP_ONLY)
    rec = _v(R.update_demo, db, rec, payload, user.username)
    _commit(db)
    return demo_out(rec, load_config(db))


@router.delete("/demos/{demo_id}")
def delete_demo(demo_id: str, user: AdminUser = Admin, db: Session = Depends(get_db)):
    rec = db.get(DemoRecord, demo_id)
    if not rec or rec.deleted_at:
        raise HTTPException(404, "Demo not found")
    _guard_live(db)
    R.soft_delete(db, rec, "demo", user.username)
    _commit(db)
    return {"ok": True}


@router.post("/demos/{demo_id}/restore")
def restore_demo(demo_id: str, user: AdminUser = Admin, db: Session = Depends(get_db)):
    rec = db.get(DemoRecord, demo_id)
    if not rec or not rec.deleted_at:
        raise HTTPException(404, "Deleted demo not found")
    _guard_live(db)
    R.restore(db, rec, "demo", user.username)
    _commit(db)
    return {"ok": True}


# ----------------------------------------------------------------------------------------- revenue
class RevenueIn(BaseModel):
    sl_no: int | None = None
    bd_id: int
    customer_name: str
    country: str | None = None
    domain: str | None = None
    opportunity_name: str
    contract_status: str
    currency: str
    contract_value: float
    contract_signed_date: date | None = None
    amount_credited_date: date | None = None
    customer_onboarding_date: date | None = None
    remarks: str | None = None
    fx_rate_override: float | None = None
    fx_rate_override_date: date | None = None
    confirm_not_duplicate: bool = False


def _rev_payload(body: RevenueIn) -> dict:
    d = body.model_dump(exclude={"confirm_not_duplicate"})
    for k in ("contract_signed_date", "amount_credited_date", "customer_onboarding_date", "fx_rate_override_date"):
        d[k] = d[k].isoformat() if d[k] else None
    return d


@router.get("/revenue")
def list_revenue(deleted: bool = False, user: AdminUser = Admin, db: Session = Depends(get_db)):
    cfg = load_config(db)
    rates = db.query(ExchangeRate).all()
    q = db.query(RevenueRecord)
    q = q.filter(RevenueRecord.deleted_at.isnot(None)) if deleted else q.filter(RevenueRecord.deleted_at.is_(None))
    return [revenue_out(r, L.evaluate_revenue(r, cfg, rates)) for r in q.order_by(RevenueRecord.created_at).all()]


@router.post("/revenue")
def create_revenue(body: RevenueIn, user: AdminUser = Admin, db: Session = Depends(get_db)):
    _guard_live(db)
    payload = _rev_payload(body)
    dups = R.possible_revenue_duplicates(db, payload)
    if dups and not body.confirm_not_duplicate:
        raise HTTPException(409, {"message": "This customer + opportunity already exists. Update the existing record "
                                             "instead (e.g. Signed → Amount Credited) so revenue is counted once.",
                                  "duplicates": [{"id": d.id, "bd_name": d.bd.name, "contract_status": d.contract_status,
                                                  "contract_value": float(d.contract_value)} for d in dups]})
    if payload.get("sl_no") is None:
        payload["sl_no"] = (max((x for (x,) in db.query(RevenueRecord.sl_no).all() if x), default=0)) + 1
    rec = _v(R.create_revenue, db, payload, user.username)
    _commit(db)
    cfg = load_config(db)
    return revenue_out(rec, L.evaluate_revenue(rec, cfg, db.query(ExchangeRate).all()))


@router.put("/revenue/{rev_id}")
def update_revenue(rev_id: str, body: RevenueIn, user: AdminUser = Admin, db: Session = Depends(get_db)):
    rec = db.get(RevenueRecord, rev_id)
    if not rec or rec.deleted_at:
        raise HTTPException(404, "Revenue record not found")
    payload = _rev_payload(body)
    _guard_live_update(db, rec, payload, R.REVENUE_FIELDS, REV_APP_ONLY)
    rec = _v(R.update_revenue, db, rec, payload, user.username)
    _commit(db)
    cfg = load_config(db)
    return revenue_out(rec, L.evaluate_revenue(rec, cfg, db.query(ExchangeRate).all()))


@router.delete("/revenue/{rev_id}")
def delete_revenue(rev_id: str, user: AdminUser = Admin, db: Session = Depends(get_db)):
    rec = db.get(RevenueRecord, rev_id)
    if not rec or rec.deleted_at:
        raise HTTPException(404, "Revenue record not found")
    _guard_live(db)
    R.soft_delete(db, rec, "revenue", user.username)
    _commit(db)
    return {"ok": True}


@router.post("/revenue/{rev_id}/restore")
def restore_revenue(rev_id: str, user: AdminUser = Admin, db: Session = Depends(get_db)):
    rec = db.get(RevenueRecord, rev_id)
    if not rec or not rec.deleted_at:
        raise HTTPException(404, "Deleted record not found")
    _guard_live(db)
    R.restore(db, rec, "revenue", user.username)
    _commit(db)
    return {"ok": True}


# ----------------------------------------------------------------------------------------- exchange rates
class RateIn(BaseModel):
    currency: str = Field(min_length=3, max_length=10)
    rate_to_inr: float = Field(gt=0)
    effective_date: date
    basis: str = Field(min_length=2, description="Where the rate comes from, e.g. 'RBI reference rate'")


@router.get("/rates")
def list_rates(user: AdminUser = Admin, db: Session = Depends(get_db)):
    return [{"id": r.id, "currency": r.currency, "rate_to_inr": float(r.rate_to_inr),
             "effective_date": r.effective_date.isoformat(), "basis": r.basis, "created_by": r.created_by,
             "created_at": r.created_at.isoformat() + "Z"}
            for r in db.query(ExchangeRate).order_by(ExchangeRate.currency, ExchangeRate.effective_date.desc())]


@router.post("/rates")
def add_rate(body: RateIn, user: AdminUser = Admin, db: Session = Depends(get_db)):
    cur = body.currency.upper()
    if cur == "INR":
        raise HTTPException(422, "INR needs no conversion rate")
    existing = db.query(ExchangeRate).filter_by(currency=cur, effective_date=body.effective_date).first()
    before = None
    if existing:
        before = {"rate_to_inr": float(existing.rate_to_inr), "basis": existing.basis}
        existing.rate_to_inr, existing.basis = body.rate_to_inr, body.basis
        rid = existing.id
    else:
        r = ExchangeRate(currency=cur, rate_to_inr=body.rate_to_inr, effective_date=body.effective_date,
                         basis=body.basis, created_by=user.username)
        db.add(r)
        db.flush()
        rid = r.id
    R.audit(db, user.username, "exchange_rate", rid, "update" if before else "create", before=before,
            after={"currency": cur, "rate_to_inr": body.rate_to_inr, "effective_date": body.effective_date.isoformat(),
                   "basis": body.basis})
    _commit(db)
    return {"ok": True}


@router.delete("/rates/{rate_id}")
def delete_rate(rate_id: int, user: AdminUser = Admin, db: Session = Depends(get_db)):
    r = db.get(ExchangeRate, rate_id)
    if not r:
        raise HTTPException(404, "Rate not found")
    R.audit(db, user.username, "exchange_rate", rate_id, "delete",
            before={"currency": r.currency, "rate_to_inr": float(r.rate_to_inr),
                    "effective_date": r.effective_date.isoformat()})
    db.delete(r)
    _commit(db)
    return {"ok": True}


# ----------------------------------------------------------------------------------------- day closure
@router.post("/days/{day}/close")
def close_day(day: date, user: AdminUser = Admin, db: Session = Depends(get_db)):
    cfg = load_config(db)
    today = L.now_local(cfg).date()
    if day > today:
        raise HTTPException(422, "Cannot close a future day")
    if not L.is_working_day(day):
        raise HTTPException(422, "Sunday is a non-working day - there is no target to close")
    if not L.in_league(day, cfg):
        raise HTTPException(422, "Day is outside the league period")
    if db.query(DayClosure).filter(DayClosure.day == day).first():
        return {"ok": True, "already": True}
    before_sig = R.ranks_signature(db)
    db.add(DayClosure(day=day, closed_by=user.username))
    R.audit(db, user.username, "day", day.isoformat(), "close_day")
    R.activity(db, "day_closed", f"Day {day.strftime('%a %d %b')} closed by admin - daily targets finalised",
               None, user.username)
    R.emit_rank_events(db, before_sig, user.username)
    _commit(db)
    return {"ok": True}


@router.post("/days/{day}/reopen")
def reopen_day(day: date, user: AdminUser = Admin, db: Session = Depends(get_db)):
    cfg = load_config(db)
    c = db.query(DayClosure).filter(DayClosure.day == day).first()
    if not c:
        raise HTTPException(404, "Day was not manually closed")
    if L.day_is_closed(day, cfg, L.now_local(cfg), set()):
        raise HTTPException(422, "The cutoff has already passed - this day is final")
    db.delete(c)
    R.audit(db, user.username, "day", day.isoformat(), "reopen_day")
    _commit(db)
    return {"ok": True}


# ----------------------------------------------------------------------------------------- awards
class FinalizeIn(BaseModel):
    award_key: str
    period_key: str
    notes: str | None = None


@router.post("/awards/finalize")
def finalize_award(body: FinalizeIn, user: AdminUser = Admin, db: Session = Depends(get_db)):
    snap = S.build(db)
    cfg = load_config(db)
    today = L.now_local(cfg).date()
    if body.award_key == "weekly_demo":
        w = next((w for w in snap["weeks"] if w["key"] == body.period_key), None)
        if not w:
            raise HTTPException(404, "Week not found")
        if date.fromisoformat(w["end"]) >= today:
            raise HTTPException(422, "A week can be finalised only after it has ended")
        result = {"leaders": w["leaders"], "tie": w["tie"], "standings": w["standings"]}
        ps, pe = date.fromisoformat(w["start"]), date.fromisoformat(w["end"])
    elif body.award_key in ("league_champion", "revenue", "f2f"):
        if body.period_key != "league":
            raise HTTPException(422, "period_key must be 'league'")
        if today <= cfg.league_end:
            raise HTTPException(422, "League awards can be finalised only after the league ends (20 Dec 2026)")
        a = snap["awards"][body.award_key]
        result = {k: a.get(k) for k in ("leaders", "champions", "tie", "tie_note") if k in a}
        if body.award_key == "league_champion":
            result["standings"] = snap["overall"]
        ps, pe = cfg.league_start, cfg.league_end
    else:
        raise HTTPException(422, "Unknown award")
    if db.query(AwardFinalization).filter_by(award_key=body.award_key, period_key=body.period_key).first():
        raise HTTPException(409, "Already finalised")
    f = AwardFinalization(award_key=body.award_key, period_key=body.period_key, period_start=ps, period_end=pe,
                          result=result, notes=body.notes, finalized_by=user.username)
    db.add(f)
    db.flush()
    R.audit(db, user.username, "award", f.id, "finalize", after={"award": body.award_key, "period": body.period_key,
                                                                  "result": result})
    names = ", ".join(x["bd_name"] for x in (result.get("leaders") or result.get("champions") or []))
    title = (cfg.raw.get("awards", {}).get(body.award_key) or {}).get("title", body.award_key)
    R.activity(db, "award_finalized", f"🏆 {title} finalised: {names or 'no eligible winner'}", None, user.username,
               {"award_key": body.award_key, "period_key": body.period_key, "finalization_id": f.id})
    _commit(db)
    return {"ok": True, "id": f.id}


@router.delete("/awards/finalize/{fid}")
def unfinalize_award(fid: int, user: AdminUser = Admin, db: Session = Depends(get_db)):
    f = db.get(AwardFinalization, fid)
    if not f:
        raise HTTPException(404, "Not found")
    R.audit(db, user.username, "award", fid, "unfinalize", before={"award": f.award_key, "period": f.period_key,
                                                                   "result": f.result})
    db.delete(f)
    _commit(db)
    return {"ok": True}


# ----------------------------------------------------------------------------------------- reports
class Filters(BaseModel):
    from_date: date | None = None
    to_date: date | None = None
    bd_ids: list[int] = []
    customer: str | None = None
    countries: list[str] = []
    domains: list[str] = []
    demo_types: list[str] = []
    statuses: list[str] = []
    qualified: list[str] = []
    contract_statuses: list[str] = []
    currencies: list[str] = []


def _apply_filters(db: Session, f: Filters):
    cfg = load_config(db)
    rates = db.query(ExchangeRate).all()
    demos = db.query(DemoRecord).filter(DemoRecord.deleted_at.is_(None)).all()
    revs = db.query(RevenueRecord).filter(RevenueRecord.deleted_at.is_(None)).all()
    cust = (f.customer or "").strip().lower()
    lower = lambda xs: {x.lower() for x in xs}  # noqa: E731

    def common(r, d: date | None):
        if f.from_date and (d is None or d < f.from_date):
            return False
        if f.to_date and (d is None or d > f.to_date):
            return False
        if f.bd_ids and r.bd_id not in f.bd_ids:
            return False
        if cust and cust not in (r.customer_name or "").lower():
            return False
        if f.countries and not ({(r.country or "").lower(), (getattr(r, "city", None) or "").lower()}
                                & lower(f.countries)):
            return False
        if f.domains and (r.domain or "").lower() not in lower(f.domains):
            return False
        return True

    fd = []
    for d in demos:
        if not common(d, d.demo_date):
            continue
        if f.demo_types and (L.demo_kind(d, cfg) or "(blank)") not in f.demo_types:
            continue
        if f.statuses and d.status not in f.statuses:
            continue
        if f.qualified and (d.qualified or "(blank)") not in f.qualified:
            continue
        fd.append(d)
    fr = []
    for r in revs:
        if not common(r, L.revenue_eligibility_date(r) or r.contract_signed_date):
            continue
        if f.contract_statuses and r.contract_status not in f.contract_statuses:
            continue
        if f.currencies and r.currency.upper() not in {c.upper() for c in f.currencies}:
            continue
        fr.append(r)
    return cfg, rates, fd, fr


@router.post("/reports/query")
def report_query(f: Filters, user: AdminUser = Admin, db: Session = Depends(get_db)):
    """FILTERED analytical view. Never feeds official standings or awards."""
    cfg, rates, fd, fr = _apply_filters(db, f)
    bds = S.bd_refs(db, include_inactive=True)
    evs = {r.id: L.evaluate_revenue(r, cfg, rates) for r in fr}
    by_bd = {b.id: {"bd_id": b.id, "bd_name": b.name, "qualified": 0, "f2f": 0, "virtual": 0, "scheduled": 0,
                    "completed": 0, "completed_unqualified": 0, "revenue_inr": 0.0, "records": 0} for b in bds}
    by_status, by_country, by_type, by_date = {}, {}, {}, {}
    for d in fd:
        row = by_bd.get(d.bd_id)
        if row is None:
            continue
        row["records"] += 1
        ach = L.is_achieved_demo(d, cfg)
        kind = L.demo_kind(d, cfg)
        if ach:
            row["qualified"] += 1
            if kind == "F2F":
                row["f2f"] += 1
            elif kind == "Virtual":
                row["virtual"] += 1
            k = d.demo_date.isoformat()
            by_date[k] = by_date.get(k, 0) + 1
        row["scheduled"] += d.status == "Scheduled"
        row["completed"] += d.status == "Completed"
        row["completed_unqualified"] += L.is_completed_unqualified(d, cfg)
        by_status[d.status] = by_status.get(d.status, 0) + 1
        place = d.country or d.city or "Unspecified"
        by_country[place] = by_country.get(place, 0) + 1
        t = kind or "(blank)"
        by_type[t] = by_type.get(t, 0) + 1
    rev_total = 0.0
    for r in fr:
        ev = evs[r.id]
        if ev["eligible"] and r.bd_id in by_bd:
            by_bd[r.bd_id]["revenue_inr"] += ev["inr_value"]
            rev_total += ev["inr_value"]
    return {
        "label": "Filtered Results",
        "notice": "Analytical view only - official league standings and awards always use complete league data.",
        "matching": {"demos": len(fd), "revenue": len(fr), "total": len(fd) + len(fr)},
        "kpis": {
            "qualified_completed": sum(1 for d in fd if L.is_achieved_demo(d, cfg)),
            "qualified_f2f": sum(1 for d in fd if L.is_achieved_demo(d, cfg) and L.demo_kind(d, cfg) == "F2F"),
            "qualified_virtual": sum(1 for d in fd if L.is_achieved_demo(d, cfg) and L.demo_kind(d, cfg) == "Virtual"),
            "scheduled": sum(1 for d in fd if d.status == "Scheduled"),
            "scheduled_f2f": sum(1 for d in fd if d.status == "Scheduled" and L.demo_kind(d, cfg) == "F2F"),
            "scheduled_virtual": sum(1 for d in fd if d.status == "Scheduled" and L.demo_kind(d, cfg) == "Virtual"),
            "completed_unqualified": sum(1 for d in fd if L.is_completed_unqualified(d, cfg)),
            "revenue_inr": round(rev_total, 2),
            "pending_conversion": sum(1 for r in fr if evs[r.id]["pending_conversion"]),
        },
        "by_bd": sorted(by_bd.values(), key=lambda x: (-x["qualified"], x["bd_name"])),
        "by_status": by_status, "by_country": by_country, "by_type": by_type,
        "by_date": dict(sorted(by_date.items())),
        "demos": [demo_out(d, cfg) for d in sorted(fd, key=lambda x: (x.demo_date or date.min), reverse=True)],
        "revenue": [revenue_out(r, evs[r.id]) for r in fr],
    }


def _xlsx(content: bytes, name: str) -> StreamingResponse:
    import io
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    return StreamingResponse(io.BytesIO(content),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}_{stamp}.xlsx"'})


@router.get("/export/{kind}")
def export(kind: str, user: AdminUser = Admin, db: Session = Depends(get_db)):
    snap = S.build(db)
    demos = db.query(DemoRecord).filter(DemoRecord.deleted_at.is_(None)).all()
    demos.sort(key=lambda d: (d.sl_no is None, d.sl_no or 0))
    revs = db.query(RevenueRecord).filter(RevenueRecord.deleted_at.is_(None)).all()
    revs.sort(key=lambda r: (r.sl_no is None, r.sl_no or 0))
    names = [b.name for b in db.query(BDMember).order_by(BDMember.display_order).all()]
    wb = X.new_wb()
    if kind == "workbook":
        X.write_demo_sheet(wb, demos, names)
        X.write_revenue_sheet(wb, revs, names)
        X.write_table(wb, "POC_Tracker", X.POC_HEADERS, X.poc_rows(demos))
        X.write_table(wb, "BD_Performance", X.PERF_HEADERS, X.performance_rows(snap))
        X.write_table(wb, "Daily_Targets", X.DAILY_HEADERS, X.daily_rows(snap))
        X.leaderboard_sheets(wb, snap)
    elif kind == "demos":
        X.write_demo_sheet(wb, demos, names)
    elif kind == "revenue":
        X.write_revenue_sheet(wb, revs, names)
    elif kind == "poc":
        X.write_table(wb, "POC_Tracker", X.POC_HEADERS, X.poc_rows(demos))
    elif kind == "performance":
        X.write_table(wb, "BD_Performance", X.PERF_HEADERS, X.performance_rows(snap))
        X.write_table(wb, "Daily_Targets", X.DAILY_HEADERS, X.daily_rows(snap))
    elif kind == "leaderboards":
        X.leaderboard_sheets(wb, snap)
    else:
        raise HTTPException(404, "Unknown export")
    R.audit(db, user.username, "export", kind, "export")
    _commit(db)
    return _xlsx(X.to_bytes(wb), {"workbook": "FireFlink_League_Workbook"}.get(kind, f"FireFlink_{kind}"))


@router.post("/export/filtered")
def export_filtered(f: Filters, user: AdminUser = Admin, db: Session = Depends(get_db)):
    cfg, rates, fd, fr = _apply_filters(db, f)
    names = [b.name for b in db.query(BDMember).order_by(BDMember.display_order).all()]
    wb = X.new_wb()
    ws = wb.active
    ws.title = "Filter_Criteria"
    ws.append(["FILTERED RESULTS - analytical view; not the official league standings"])
    for k, v in f.model_dump().items():
        if v:
            ws.append([k, ", ".join(map(str, v)) if isinstance(v, list) else str(v)])
    ws.append(["Matching demo records", len(fd)])
    ws.append(["Matching revenue records", len(fr)])
    X.write_demo_sheet(wb, fd, names)
    X.write_revenue_sheet(wb, fr, names)
    R.audit(db, user.username, "export", "filtered", "export", after=f.model_dump(mode="json"))
    _commit(db)
    return _xlsx(X.to_bytes(wb), "FireFlink_Filtered_Report")


# ----------------------------------------------------------------------------------------- import
@router.post("/import/preview")
async def import_preview(file: UploadFile = File(...), user: AdminUser = Admin, db: Session = Depends(get_db)):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(422, "Please upload an .xlsx workbook")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 25 MB)")
    try:
        hist = I.build_preview(db, content, file.filename, user.username)
    except Exception as e:  # unreadable workbook
        raise HTTPException(422, f"Could not read workbook: {e}")
    _commit(db)
    return {"id": hist.id, **hist.preview}


class ApplyIn(BaseModel):
    decisions: dict[str, dict[str, dict[str, Any]]] = {}
    add_bds: list[str] = []


@router.post("/import/{hid}/apply")
def import_apply(hid: int, body: ApplyIn, user: AdminUser = Admin, db: Session = Depends(get_db)):
    hist = db.get(ImportHistory, hid)
    if not hist:
        raise HTTPException(404, "Import not found")
    _guard_live(db)
    summary = _v(I.apply_import, db, hist, body.decisions, body.add_bds, user.username)
    _commit(db)
    return summary


@router.post("/import/{hid}/cancel")
def import_cancel(hid: int, user: AdminUser = Admin, db: Session = Depends(get_db)):
    hist = db.get(ImportHistory, hid)
    if not hist or hist.status != "preview":
        raise HTTPException(404, "No pending preview")
    hist.status = "cancelled"
    R.audit(db, user.username, "import", hid, "import_cancel", note=hist.filename)
    _commit(db)
    return {"ok": True}


@router.get("/import/history")
def import_history(user: AdminUser = Admin, db: Session = Depends(get_db)):
    return [{"id": h.id, "filename": h.filename, "status": h.status, "created_at": h.created_at.isoformat() + "Z",
             "applied_at": (h.applied_at.isoformat() + "Z") if h.applied_at else None, "summary": h.summary,
             "by": h.created_by, "demos_counts": h.preview.get("demos_counts"),
             "revenue_counts": h.preview.get("revenue_counts")}
            for h in db.query(ImportHistory).order_by(ImportHistory.id.desc()).limit(50)]


# ----------------------------------------------------------------------------------------- settings
@router.get("/countries")
def countries(user: AdminUser = Admin):
    """Country catalog for the F2F country picker (names + the spellings/cities each one matches)."""
    from ..countries import catalog
    return catalog()


@router.get("/settings")
def get_settings(user: AdminUser = Admin, db: Session = Depends(get_db)):
    raw = load_raw(db)
    out = {k: raw[k] for k in EDITABLE_KEYS if k in raw}
    out["arena_link_enabled"] = bool(raw.get("arena_token_hash"))
    return out


@router.put("/settings")
def put_settings(body: dict[str, Any], user: AdminUser = Admin, db: Session = Depends(get_db)):
    raw = load_raw(db)
    unknown = set(body) - EDITABLE_KEYS
    if unknown:
        raise HTTPException(422, f"Unknown settings: {', '.join(sorted(unknown))}")
    trial = {**raw, **body}
    try:
        cfg = to_config(trial)
        assert cfg.league_start <= cfg.league_end, "League start must be on/before league end"
        assert 0 <= cfg.week_start_day <= 6, "week_start_day must be 0-6"
        assert cfg.f2f_target > 0, "F2F target must be positive"
        assert 1 <= cfg.daily_target <= 20, "Daily target must be between 1 and 20"
        regions = trial.get("f2f_regions")
        assert isinstance(regions, dict) and all(
            isinstance(k, str) and k.strip() and isinstance(v, list) and all(isinstance(a, str) for a in v)
            for k, v in regions.items()), "F2F countries must map a name to a list of spellings"
        assert all(v for v in regions.values()), "Every F2F country needs at least one spelling to match"
        assert int(trial.get("gsheet_sync_interval_seconds") or 60) >= 30, "Sync interval must be at least 30 seconds"
        if trial.get("gsheet_sync_enabled"):
            assert G.sheet_id(trial.get("gsheet_url") or ""), "Enter a valid Google Sheets link"
        for k in ("count_requires_qualified", "f2f_from_location", "gsheet_sync_enabled"):
            assert isinstance(trial.get(k), bool), f"{k} must be true or false"
    except (AssertionError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise HTTPException(422, f"Invalid settings: {e}")
    changed = {k: v for k, v in body.items() if raw.get(k) != v}
    for k, v in changed.items():
        save_setting(db, k, v)
    if changed:
        R.audit(db, user.username, "settings", None, "update", before={k: raw.get(k) for k in changed}, after=changed)
    _commit(db)
    return {"ok": True, "changed": sorted(changed)}


@router.get("/gsheet/status")
def gsheet_status(user: AdminUser = Admin, db: Session = Depends(get_db)):
    st = load_raw(db).get(G.STATUS_KEY) or {}
    return {**sync_public(db), "summary": st.get("summary")}


@router.post("/gsheet/sync")
def gsheet_sync_now(user: AdminUser = Admin, db: Session = Depends(get_db)):
    if not load_raw(db).get("gsheet_url"):
        raise HTTPException(422, "Set the Google Sheet link first")
    R.audit(db, user.username, "gsheet", None, "sync_now")
    db.commit()
    st = G.run_once(db, force=True)
    if st.get("error"):
        raise HTTPException(502, st["error"])
    return {**sync_public(db), "summary": st.get("summary")}


class SheetCheckIn(BaseModel):
    url: str
    count_requires_qualified: bool | None = None  # check against rules not saved yet (set-up wizard)
    f2f_from_location: bool | None = None


@router.post("/gsheet/check")
def gsheet_check(body: SheetCheckIn, user: AdminUser = Admin, db: Session = Depends(get_db)):
    """Download the sheet and report tabs / columns / BD names for this team. Saves nothing."""
    if not G.sheet_id(body.url):
        raise HTTPException(422, "Enter a valid Google Sheets link")
    raw = load_raw(db)
    for k in ("count_requires_qualified", "f2f_from_location"):
        if getattr(body, k) is not None:
            raw[k] = getattr(body, k)
    try:
        content = G.fetch_xlsx(body.url)
    except Exception as e:
        raise HTTPException(502, str(e))
    return G.inspect_workbook(db, content, to_config(raw))


@router.post("/settings/arena-link")
def arena_link(user: AdminUser = Admin, db: Session = Depends(get_db)):
    token, h = auth.new_arena_token()
    save_setting(db, "arena_token_hash", h)
    R.audit(db, user.username, "settings", None, "arena_link_regenerated")
    _commit(db)
    return {"token": token}


@router.delete("/settings/arena-link")
def arena_link_revoke(user: AdminUser = Admin, db: Session = Depends(get_db)):
    save_setting(db, "arena_token_hash", None)
    R.audit(db, user.username, "settings", None, "arena_link_revoked")
    _commit(db)
    return {"ok": True}


class BDIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    active: bool = True
    display_order: int | None = None


@router.get("/bds")
def list_bds(user: AdminUser = Admin, db: Session = Depends(get_db)):
    return [{"id": b.id, "name": b.name, "active": b.active, "display_order": b.display_order}
            for b in db.query(BDMember).order_by(BDMember.display_order, BDMember.name)]


@router.post("/bds")
def add_bd(body: BDIn, user: AdminUser = Admin, db: Session = Depends(get_db)):
    name = " ".join(body.name.split())
    if db.query(BDMember).filter(BDMember.name.ilike(name)).first():
        raise HTTPException(409, "A BD with this name already exists")
    order = body.display_order if body.display_order is not None else (
        max((b.display_order for b in db.query(BDMember).all()), default=0) + 1)
    b = BDMember(name=name, active=body.active, display_order=order)
    db.add(b)
    db.flush()
    R.audit(db, user.username, "bd", b.id, "create", after={"name": name})
    _commit(db)
    return {"id": b.id}


@router.put("/bds/{bd_id}")
def edit_bd(bd_id: int, body: BDIn, user: AdminUser = Admin, db: Session = Depends(get_db)):
    b = db.get(BDMember, bd_id)
    if not b:
        raise HTTPException(404, "BD not found")
    name = " ".join(body.name.split())
    clash = db.query(BDMember).filter(BDMember.name.ilike(name), BDMember.id != bd_id).first()
    if clash:
        raise HTTPException(409, "Another BD already has this name")
    before = {"name": b.name, "active": b.active, "display_order": b.display_order}
    b.name, b.active = name, body.active
    if body.display_order is not None:
        b.display_order = body.display_order
    R.audit(db, user.username, "bd", b.id, "update", before=before,
            after={"name": b.name, "active": b.active, "display_order": b.display_order})
    _commit(db)
    return {"ok": True}


@router.delete("/bds/{bd_id}")
def delete_bd(bd_id: int, user: AdminUser = Admin, db: Session = Depends(get_db)):
    """Remove a BD added by mistake. BDs with any demo or revenue history can only be deactivated."""
    b = db.get(BDMember, bd_id)
    if not b:
        raise HTTPException(404, "BD not found")
    used = (db.query(DemoRecord).filter(DemoRecord.bd_id == bd_id).count() +
            db.query(RevenueRecord).filter(RevenueRecord.bd_id == bd_id).count())
    if used:
        raise HTTPException(409, f"{b.name} has {used} record(s) - deactivate instead of deleting")
    db.query(ActivityEvent).filter(ActivityEvent.bd_id == bd_id).delete()
    R.audit(db, user.username, "bd", b.id, "delete", before={"name": b.name})
    db.delete(b)
    _commit(db)
    return {"ok": True}


@router.get("/audit")
def audit_log(limit: int = 200, entity: str | None = None, user: AdminUser = Admin, db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    if entity:
        q = q.filter(AuditLog.entity == entity)
    return [{"id": a.id, "at": a.at.isoformat() + "Z", "actor": a.actor, "entity": a.entity, "entity_id": a.entity_id,
             "action": a.action, "before": a.before, "after": a.after, "note": a.note}
            for a in q.order_by(AuditLog.id.desc()).limit(min(limit, 2000))]


# ----------------------------------------------------------------------------------------- teams & logins
_SLUG_RE = __import__("re").compile(r"[^a-z0-9]+")
TEAM_PRIVATE_SETTINGS = {"gsheet_url", "gsheet_sync_enabled", G.STATUS_KEY, "arena_token_hash"}


def _slugify(s: str) -> str:
    return _SLUG_RE.sub("-", s.lower()).strip("-")[:60] or "team"


class TeamIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=60)
    copy_settings_from: int | None = None  # copy league settings (dates, targets, prizes...) from this team


class TeamEdit(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    active: bool | None = None


@router.get("/teams")
def list_teams(user: AdminUser = Super, db: Session = Depends(get_db)):
    from ..tenancy import unscoped
    from sqlalchemy import func
    unscoped(db)
    def counts(model, *flt):
        q = db.query(model.team_id, func.count()).filter(*flt).group_by(model.team_id)
        return dict(q.all())
    bds = counts(BDMember, BDMember.active.is_(True))
    demos = counts(DemoRecord, DemoRecord.deleted_at.is_(None))
    revs = counts(RevenueRecord, RevenueRecord.deleted_at.is_(None))
    logins = dict(db.query(AdminUser.team_id, func.count()).group_by(AdminUser.team_id).all())
    sheets = {r.team_id: r.value for r in db.query(Setting).filter(Setting.key == "gsheet_url")}
    live = {r.team_id: r.value for r in db.query(Setting).filter(Setting.key == "gsheet_sync_enabled")}
    return [{**_team_out(t), "created_at": t.created_at.isoformat() + "Z", "bds": bds.get(t.id, 0),
             "demos": demos.get(t.id, 0), "revenue": revs.get(t.id, 0), "logins": logins.get(t.id, 0),
             "sheet_url": sheets.get(t.id, DEFAULTS["gsheet_url"]) or None,
             "live_sync": bool(live.get(t.id, DEFAULTS["gsheet_sync_enabled"]))}
            for t in db.query(Team).order_by(Team.name)]


@router.post("/teams")
def create_team(body: TeamIn, user: AdminUser = Super, db: Session = Depends(get_db)):
    name = " ".join(body.name.split())
    slug = _slugify(body.slug or name)
    if db.query(Team).filter((Team.name.ilike(name)) | (Team.slug == slug)).first():
        raise HTTPException(409, "A team with this name already exists")
    src_settings = {}
    if body.copy_settings_from:
        if not db.get(Team, body.copy_settings_from):
            raise HTTPException(404, "Team to copy settings from not found")
        bind_team(db, body.copy_settings_from)
        src_settings = {k: v for k, v in load_raw(db).items() if k not in TEAM_PRIVATE_SETTINGS}
    t = Team(name=name, slug=slug)
    db.add(t)
    db.flush()
    bind_team(db, t.id)
    # Copied league settings (dates, targets, prizes...) + the new-team sheet rules.
    values = {**{k: v for k, v in src_settings.items() if k in EDITABLE_KEYS}, **NEW_TEAM_DEFAULTS}
    if not body.copy_settings_from:
        # Teams work in different countries: a fresh team picks its own F2F countries in set-up.
        values.update(f2f_regions={}, f2f_windows=[])
    for k, v in values.items():
        if DEFAULTS.get(k) != v or k in NEW_TEAM_DEFAULTS:
            db.add(Setting(key=k, value=v))
    R.audit(db, user.username, "team", t.id, "create", after={"name": name, "slug": slug,
                                                              "copied_from": body.copy_settings_from})
    _commit(db)
    return _team_out(t)


@router.put("/teams/{team_id}")
def edit_team(team_id: int, body: TeamEdit, user: AdminUser = Super, db: Session = Depends(get_db)):
    t = db.get(Team, team_id)
    if not t:
        raise HTTPException(404, "Team not found")
    before = _team_out(t)
    if body.name is not None:
        name = " ".join(body.name.split())
        if db.query(Team).filter(Team.name.ilike(name), Team.id != team_id).first():
            raise HTTPException(409, "Another team already has this name")
        t.name = name
    if body.active is not None:
        if not body.active and db.query(Team).filter(Team.active.is_(True), Team.id != team_id).count() == 0:
            raise HTTPException(422, "At least one team must stay active")
        t.active = body.active
    bind_team(db, t.id)
    R.audit(db, user.username, "team", t.id, "update", before=before, after=_team_out(t))
    _commit(db)
    return _team_out(t)


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._@-]+$")
    password: str = Field(min_length=10)
    role: str = ROLE_TEAM
    team_id: int | None = None


class UserEdit(BaseModel):
    password: str | None = Field(default=None, min_length=10)
    role: str | None = None
    team_id: int | None = None


def _user_out(u: AdminUser) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "team_id": u.team_id,
            "team_name": u.team.name if u.team else None, "created_at": u.created_at.isoformat() + "Z"}


def _check_role(db: Session, role: str, team_id: int | None):
    if role not in (ROLE_SUPER, ROLE_TEAM):
        raise HTTPException(422, "Role must be super_admin or team_admin")
    if role == ROLE_TEAM:
        if not team_id or not db.get(Team, team_id):
            raise HTTPException(422, "A team admin must belong to a team")


@router.get("/users")
def list_users(user: AdminUser = Super, db: Session = Depends(get_db)):
    return [_user_out(u) for u in db.query(AdminUser).order_by(AdminUser.role.desc(), AdminUser.username)]


@router.post("/users")
def create_user(body: UserIn, user: AdminUser = Super, db: Session = Depends(get_db)):
    _check_role(db, body.role, body.team_id)
    if db.query(AdminUser).filter(AdminUser.username.ilike(body.username)).first():
        raise HTTPException(409, "This username is already taken")
    u = AdminUser(username=body.username, password_hash=auth.hash_password(body.password), role=body.role,
                  team_id=body.team_id if body.role == ROLE_TEAM else None)
    db.add(u)
    db.flush()
    R.audit(db, user.username, "user", u.id, "create", after={"username": u.username, "role": u.role,
                                                              "team_id": u.team_id})
    _commit(db)
    db.refresh(u)
    return _user_out(u)


def _super_count(db: Session, exclude: int | None = None) -> int:
    q = db.query(AdminUser).filter(AdminUser.role == ROLE_SUPER)
    if exclude:
        q = q.filter(AdminUser.id != exclude)
    return q.count()


@router.put("/users/{user_id}")
def edit_user(user_id: int, body: UserEdit, user: AdminUser = Super, db: Session = Depends(get_db)):
    u = db.get(AdminUser, user_id)
    if not u:
        raise HTTPException(404, "Login not found")
    role = body.role or u.role
    team_id = body.team_id if body.team_id is not None else u.team_id
    _check_role(db, role, team_id)
    if u.role == ROLE_SUPER and role != ROLE_SUPER and _super_count(db, exclude=u.id) == 0:
        raise HTTPException(422, "At least one super admin must remain")
    before = {"role": u.role, "team_id": u.team_id}
    u.role, u.team_id = role, (team_id if role == ROLE_TEAM else None)
    if body.password:
        u.password_hash = auth.hash_password(body.password)
        if u.id != user.id:  # sign the user out everywhere after a reset
            db.query(AuthSession).filter(AuthSession.user_id == u.id).delete()
    R.audit(db, user.username, "user", u.id, "update", before=before,
            after={"role": u.role, "team_id": u.team_id, "password_reset": bool(body.password)})
    _commit(db)
    db.refresh(u)
    return _user_out(u)


@router.delete("/users/{user_id}")
def delete_user(user_id: int, user: AdminUser = Super, db: Session = Depends(get_db)):
    u = db.get(AdminUser, user_id)
    if not u:
        raise HTTPException(404, "Login not found")
    if u.id == user.id:
        raise HTTPException(422, "You cannot delete your own login")
    if u.role == ROLE_SUPER and _super_count(db, exclude=u.id) == 0:
        raise HTTPException(422, "At least one super admin must remain")
    db.query(AuthSession).filter(AuthSession.user_id == u.id).delete()
    R.audit(db, user.username, "user", u.id, "delete", before={"username": u.username, "role": u.role,
                                                               "team_id": u.team_id})
    db.delete(u)
    _commit(db)
    return {"ok": True}
