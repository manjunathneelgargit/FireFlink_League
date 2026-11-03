"""Record operations with validation, audit trail and activity feed. Used by the API and importer."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from ..config import load_config
from ..constants import (CONTRACT_STATUSES, DEMO_STATUSES, DEMO_TYPES, POC_STATUSES, QUALIFIED_VALUES)
from ..models import ActivityEvent, AuditLog, BDMember, DemoRecord, RevenueRecord, utcnow
from . import league as L
from .snapshot import ranks_signature

DEMO_FIELDS = ["sl_no", "bd_id", "customer_name", "domain", "country", "demo_type", "demo_on", "demo_date",
               "demo_time", "time_zone", "status", "qualified", "poc_started_on", "poc_remarks"]
REVENUE_FIELDS = ["sl_no", "bd_id", "customer_name", "country", "domain", "opportunity_name", "contract_status",
                  "currency", "contract_value", "contract_signed_date", "amount_credited_date",
                  "customer_onboarding_date", "remarks", "fx_rate_override", "fx_rate_override_date"]


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _ser(v):
    if isinstance(v, (date, datetime, time)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def snapshot_of(obj, fields) -> dict:
    return {f: _ser(getattr(obj, f)) for f in fields}


def audit(db: Session, actor: str, entity: str, entity_id, action: str, before=None, after=None, note=None):
    db.add(AuditLog(actor=actor, entity=entity, entity_id=str(entity_id) if entity_id is not None else None,
                    action=action, before=before, after=after, note=note))


def activity(db: Session, kind: str, message: str, bd_id=None, actor=None, meta=None):
    db.add(ActivityEvent(kind=kind, message=message, bd_id=bd_id, actor=actor, meta=meta))


def _src(source: str) -> str:
    return "sheet" if source == "gsheet" else "import"


def norm(s: str | None) -> str:
    return " ".join((s or "").lower().replace(".", " ").split())


# ------------------------------------------------------------------------------------- validation
def clean_demo(data: dict, db: Session, today: date, strict_date: bool = True) -> dict:
    errors = []
    out = {k: data.get(k) for k in DEMO_FIELDS if k in data}
    for k in ("customer_name", "domain", "country", "demo_on", "time_zone", "poc_remarks"):
        if k in out and isinstance(out[k], str):
            out[k] = out[k].strip() or None
    if not out.get("customer_name"):
        errors.append("Customer Name is required")
    bd = db.get(BDMember, out.get("bd_id")) if out.get("bd_id") is not None else None
    if bd is None:
        errors.append("BD must be one of the configured BD members")
    if out.get("demo_type") in ("", None):
        out["demo_type"] = None
    elif out["demo_type"] not in DEMO_TYPES:
        errors.append(f"Invalid Demo Type '{out['demo_type']}'. Allowed: F2F, Virtual")
    if out.get("status") not in DEMO_STATUSES:
        errors.append(f"Invalid Status '{out.get('status')}'")
    if out.get("qualified") in ("", None):
        out["qualified"] = None
    elif out["qualified"] not in QUALIFIED_VALUES:
        errors.append("Qualified Demo must be Yes or No")
    for k in ("demo_date", "poc_started_on"):
        if isinstance(out.get(k), str):
            try:
                out[k] = date.fromisoformat(out[k]) if out[k] else None
            except ValueError:
                errors.append(f"Invalid date for {k}")
    if isinstance(out.get("demo_time"), str):
        try:
            out["demo_time"] = time.fromisoformat(out["demo_time"]) if out["demo_time"] else None
        except ValueError:
            errors.append("Invalid Demo Time")
    st = out.get("status")
    if st == "Completed":
        if not out.get("demo_date"):
            if strict_date:
                errors.append("A Completed demo needs a Demo Date (the Demo Date is the completion date)")
        elif out["demo_date"] > today:
            errors.append("A demo dated in the future cannot be Completed")
    if out.get("qualified") == "Yes" and st not in (["Completed"] + POC_STATUSES):
        errors.append("Only a Completed demo can be marked Qualified = Yes")
    if errors:
        raise ValidationError(errors)
    return out


def clean_revenue(data: dict, db: Session) -> dict:
    errors = []
    out = {k: data.get(k) for k in REVENUE_FIELDS if k in data}
    for k in ("customer_name", "country", "domain", "opportunity_name", "remarks", "currency"):
        if k in out and isinstance(out[k], str):
            out[k] = out[k].strip() or None
    if not out.get("customer_name"):
        errors.append("Customer Name is required")
    if not out.get("opportunity_name"):
        errors.append("Opportunity Name is required")
    if out.get("bd_id") is None or db.get(BDMember, out.get("bd_id")) is None:
        errors.append("BD must be one of the configured BD members")
    if out.get("contract_status") not in CONTRACT_STATUSES:
        errors.append("Contract Status must be Signed or Amount Credited")
    if not out.get("currency"):
        errors.append("Currency is required")
    else:
        out["currency"] = out["currency"].upper()
    try:
        v = Decimal(str(out.get("contract_value")))
        if v < 0:
            errors.append("Contract Value cannot be negative")
        out["contract_value"] = v
    except (InvalidOperation, TypeError):
        errors.append("Contract Value must be a number")
    for k in ("contract_signed_date", "amount_credited_date", "customer_onboarding_date", "fx_rate_override_date"):
        if isinstance(out.get(k), str):
            try:
                out[k] = date.fromisoformat(out[k]) if out[k] else None
            except ValueError:
                errors.append(f"Invalid date for {k}")
    if out.get("contract_status") == "Signed" and not out.get("contract_signed_date"):
        errors.append("Signed contracts need a Contract Signed Date")
    if out.get("contract_status") == "Amount Credited" and not out.get("amount_credited_date"):
        errors.append("Amount Credited needs an Amount Credited Date")
    if out.get("fx_rate_override") in ("", None):
        out["fx_rate_override"] = None
    else:
        try:
            out["fx_rate_override"] = Decimal(str(out["fx_rate_override"]))
            if out["fx_rate_override"] <= 0:
                errors.append("Exchange rate must be positive")
        except InvalidOperation:
            errors.append("Exchange rate must be a number")
    if errors:
        raise ValidationError(errors)
    return out


def possible_revenue_duplicates(db: Session, data: dict, exclude_id: str | None = None) -> list[RevenueRecord]:
    q = db.query(RevenueRecord).filter(RevenueRecord.deleted_at.is_(None))
    return [r for r in q.all() if r.id != exclude_id and norm(r.customer_name) == norm(data.get("customer_name"))
            and norm(r.opportunity_name) == norm(data.get("opportunity_name"))]


# ------------------------------------------------------------------------------------- side effects
def emit_rank_events(db: Session, before: dict, actor: str):
    db.flush()
    after = ranks_signature(db)
    names = after["names"]
    if after["leaders"] and after["leaders"] != before["leaders"]:
        who = ", ".join(names[i] for i in after["leaders"])
        activity(db, "new_leader", f"NEW LEADER! {who} now lead{'s' if len(after['leaders']) == 1 else ''} the league",
                 after["leaders"][0], actor)
    for bd_id, rank in after["ranks"].items():
        old = before["ranks"].get(bd_id)
        if old and rank != old:
            verb = "moved up" if rank < old else "moved down"
            activity(db, "rank_change", f"{names[bd_id]} {verb} to #{rank} (was #{old})", bd_id, actor,
                     {"from": old, "to": rank})
    if after["rev_champs"] and after["rev_champs"] != before["rev_champs"]:
        who = ", ".join(names[i] for i in after["rev_champs"])
        activity(db, "revenue_champion", f"Revenue Champion: {who}", after["rev_champs"][0], actor)
    for m in after["milestones"]:
        if m not in before["milestones"]:
            activity(db, "f2f_milestone", f"F2F challenge milestone reached: {m} qualified F2F demos!", None, actor,
                     {"milestone": m})


def _demo_activity(db: Session, before: dict | None, rec: DemoRecord, actor: str):
    name = rec.bd.name if rec.bd else ""
    tag = f"{rec.customer_name}" + (f" ({rec.demo_type})" if rec.demo_type else "")
    if before is None:
        if rec.status == "Scheduled":
            activity(db, "demo_scheduled", f"{name} scheduled a demo with {tag}", rec.bd_id, actor)
        else:
            activity(db, "demo_added", f"{name}: {tag} added as {rec.status}", rec.bd_id, actor)
    else:
        if before["status"] != rec.status:
            kind = {"Completed": "demo_completed", "POC Initiated": "poc_initiated",
                    "POC Completed": "poc_completed"}.get(rec.status, "demo_status")
            activity(db, kind, f"{name}: {tag} {before['status']} → {rec.status}", rec.bd_id, actor)
    was = before is not None and before.get("_achieved")
    if L.is_achieved_demo(rec) and not was:
        activity(db, "qualified_demo", f"Qualified demo recorded for {name} — {tag}", rec.bd_id, actor)


# ------------------------------------------------------------------------------------- demo CRUD
def create_demo(db: Session, data: dict, actor: str, source: str = "manual", emit: bool = True) -> DemoRecord:
    cfg = load_config(db)
    clean = clean_demo(data, db, L.now_local(cfg).date(), strict_date=(source == "manual"))
    before_sig = ranks_signature(db) if emit else None
    rec = DemoRecord(**clean, source=source)
    _apply_poc_rules_cfg(rec, None, cfg)
    db.add(rec)
    db.flush()
    db.refresh(rec)
    audit(db, actor, "demo", rec.id, "create" if source == "manual" else f"{_src(source)}_create",
          after=snapshot_of(rec, DEMO_FIELDS))
    if emit:
        _demo_activity(db, None, rec, actor)
        emit_rank_events(db, before_sig, actor)
    return rec


def _apply_poc_rules_cfg(rec: DemoRecord, prev_status: str | None, cfg):
    if rec.status == "Completed":
        rec.demo_completed = True
    elif rec.status in POC_STATUSES:
        if rec.qualified == "Yes":
            rec.demo_completed = True
        if prev_status not in POC_STATUSES:
            rec.poc_started_on = rec.poc_started_on or L.now_local(cfg).date()
            rec.poc_status_updated_at = utcnow()
        elif prev_status != rec.status:
            rec.poc_status_updated_at = utcnow()
    else:
        rec.demo_completed = False


def update_demo(db: Session, rec: DemoRecord, data: dict, actor: str, source: str = "manual",
                emit: bool = True) -> DemoRecord:
    cfg = load_config(db)
    merged = snapshot_of(rec, DEMO_FIELDS)
    merged.update({k: v for k, v in data.items() if k in DEMO_FIELDS})
    # Legacy records (imported Completed without a date) may still be edited; a date is required
    # only when the admin is the one marking the demo Completed.
    strict = source == "manual" and (rec.status != "Completed" or rec.demo_date is not None)
    clean = clean_demo(merged, db, L.now_local(cfg).date(), strict_date=strict)
    before = snapshot_of(rec, DEMO_FIELDS)
    before["_achieved"] = L.is_achieved_demo(rec)
    before_sig = ranks_signature(db) if emit else None
    prev_status = rec.status
    for k, v in clean.items():
        setattr(rec, k, v)
    _apply_poc_rules_cfg(rec, prev_status, cfg)
    db.flush()
    after = snapshot_of(rec, DEMO_FIELDS)
    changed = {k for k in DEMO_FIELDS if before.get(k) != after.get(k)}
    if not changed:
        return rec
    action = "update"
    if "status" in changed:
        action = "status_change"
    elif "qualified" in changed:
        action = "qualification_change"
    audit(db, actor, "demo", rec.id, action if source == "manual" else f"{_src(source)}_{action}",
          before={k: before[k] for k in changed}, after={k: after[k] for k in changed})
    if emit:
        db.refresh(rec)
        _demo_activity(db, before, rec, actor)
        emit_rank_events(db, before_sig, actor)
    return rec


def soft_delete(db: Session, rec, entity: str, actor: str):
    before_sig = ranks_signature(db)
    rec.deleted_at = utcnow()
    audit(db, actor, entity, rec.id, "delete", before={"customer_name": rec.customer_name})
    activity(db, f"{entity}_deleted", f"{entity.title()} record for {rec.customer_name} moved to trash",
             rec.bd_id, actor)
    emit_rank_events(db, before_sig, actor)


def restore(db: Session, rec, entity: str, actor: str):
    before_sig = ranks_signature(db)
    rec.deleted_at = None
    audit(db, actor, entity, rec.id, "restore", after={"customer_name": rec.customer_name})
    activity(db, f"{entity}_restored", f"{entity.title()} record for {rec.customer_name} restored", rec.bd_id, actor)
    emit_rank_events(db, before_sig, actor)


# ------------------------------------------------------------------------------------- revenue CRUD
def _fmt_money(cur: str, v) -> str:
    return f"{cur} {float(v):,.0f}"


def create_revenue(db: Session, data: dict, actor: str, source: str = "manual", emit: bool = True) -> RevenueRecord:
    clean = clean_revenue(data, db)
    before_sig = ranks_signature(db) if emit else None
    rec = RevenueRecord(**clean, source=source)
    db.add(rec)
    db.flush()
    db.refresh(rec)
    audit(db, actor, "revenue", rec.id, "create" if source == "manual" else f"{_src(source)}_create",
          after=snapshot_of(rec, REVENUE_FIELDS))
    if emit:
        activity(db, "revenue_updated", f"{rec.bd.name}: {rec.customer_name} – {rec.opportunity_name} "
                 f"{rec.contract_status} ({_fmt_money(rec.currency, rec.contract_value)})", rec.bd_id, actor)
        emit_rank_events(db, before_sig, actor)
    return rec


def update_revenue(db: Session, rec: RevenueRecord, data: dict, actor: str, source: str = "manual",
                   emit: bool = True) -> RevenueRecord:
    merged = snapshot_of(rec, REVENUE_FIELDS)
    merged.update({k: v for k, v in data.items() if k in REVENUE_FIELDS})
    clean = clean_revenue(merged, db)
    before = snapshot_of(rec, REVENUE_FIELDS)
    before_sig = ranks_signature(db) if emit else None
    for k, v in clean.items():
        setattr(rec, k, v)
    db.flush()
    after = snapshot_of(rec, REVENUE_FIELDS)
    changed = {k for k in REVENUE_FIELDS if before.get(k) != after.get(k)}
    if not changed:
        return rec
    audit(db, actor, "revenue", rec.id, "update" if source == "manual" else f"{_src(source)}_update",
          before={k: before[k] for k in changed}, after={k: after[k] for k in changed})
    if emit:
        db.refresh(rec)
        msg = f"{rec.bd.name}: {rec.customer_name} – {rec.opportunity_name} updated"
        if "contract_status" in changed:
            msg = f"{rec.bd.name}: {rec.customer_name} – {before['contract_status']} → {rec.contract_status}"
        activity(db, "revenue_updated", msg, rec.bd_id, actor)
        emit_rank_events(db, before_sig, actor)
    return rec
