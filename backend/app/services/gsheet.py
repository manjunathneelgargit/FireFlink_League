"""Live Google Sheet sync - the sheet is the source of truth for the 13 demo / 13 revenue fields.

Every few seconds (configurable) the worker downloads the sheet as .xlsx and mirrors it:
  * new rows -> created, changed rows -> updated (sheet wins), rows gone from the sheet -> soft-deleted.
  * Row identity = Sl No + Customer Name (so a rescheduled Demo Date is an UPDATE, not a new demo);
    rows without Sl No fall back to BD + Customer + Demo Date (demos) / Opportunity (revenue).
  * Invalid rows are reported and leave the stored record untouched (and never deleted).
  * Safety valve: if one sync would delete > 25% of records, no deletions happen and an alert is raised.
App-only fields (POC start date / remarks, FX overrides) are never touched by the sync.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
import threading
import time as _time
import urllib.error
import urllib.request
import warnings
from datetime import datetime, timezone

import openpyxl
from sqlalchemy.orm import Session

from ..config import load_config, load_raw, save_setting
from ..constants import DEMO_IGNORED_HEADERS, DEMO_SHEET, REVENUE_HEADERS, REVENUE_SHEET
from ..models import BDMember, DemoRecord, RevenueRecord, utcnow
from . import importer as I
from . import league as L
from . import records as R

log = logging.getLogger("gsheet")
ACTOR = "Google Sheet"
STATUS_KEY = "gsheet_sync_status"
MAX_DELETE_SHARE = 0.25
_lock = threading.Lock()


def sheet_id(url_or_id: str) -> str | None:
    m = re.search(r"/d/([A-Za-z0-9_-]{20,})", url_or_id or "")
    if m:
        return m.group(1)
    return url_or_id.strip() if re.fullmatch(r"[A-Za-z0-9_-]{20,}", (url_or_id or "").strip()) else None


def _title_from_disposition(header: str | None) -> str | None:
    """Parse the spreadsheet name from Content-Disposition (prefer UTF-8 filename*)."""
    if not header:
        return None
    m = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", header, re.I)
    if m:
        from urllib.parse import unquote
        name = unquote(m.group(1).strip().strip('"'))
    else:
        m = re.search(r'filename\s*=\s*"([^"]+)"|filename\s*=\s*([^;]+)', header, re.I)
        if not m:
            return None
        name = (m.group(1) or m.group(2) or "").strip().strip('"')
    if name.lower().endswith(".xlsx"):
        name = name[:-5]
    name = name.strip()
    return name or None


def _open_google(req: urllib.request.Request, timeout: int):
    """Download without env HTTP(S)_PROXY — Cursor/sandbox proxies return Tunnel 403 to Google."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(req, timeout=timeout)


def fetch_xlsx(url_or_id: str, timeout: int = 45) -> tuple[bytes, str | None]:
    """Return (xlsx bytes, spreadsheet title or None)."""
    sid = sheet_id(url_or_id)
    if not sid:
        raise ValueError("Not a valid Google Sheets link")
    req = urllib.request.Request(
        f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx",
        headers={"User-Agent": "FireFlink-League-Tracker/1.0"},
    )
    try:
        with _open_google(req, timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            title = _title_from_disposition(resp.headers.get("Content-Disposition"))
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise ValueError(f"Google returned {e.code}: the sheet is not shared as 'Anyone with the link can view'") from e
        raise ValueError(f"Google returned HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise ValueError(f"Could not reach Google Sheets: {e.reason}") from e
    if "spreadsheetml" not in ctype and not data.startswith(b"PK"):
        raise ValueError("Google did not return a spreadsheet - check the sheet's sharing settings")
    return data, title


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------------------------------------- check
def inspect_workbook(db: Session, content: bytes, cfg) -> dict:
    """Dry run for the team set-up wizard: which tabs / columns are present for this team's rules,
    how many rows each tab has, and which BD names the sheet uses that the team doesn't have yet.
    Nothing is written."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    known = {b.name.lower() for b in db.query(BDMember).all()}
    out = {"ok": True, "sheets": [], "sheet_names": wb.sheetnames, "bd_names": [], "unknown_bds": []}
    names: dict[str, str] = {}
    for sheet, headers, mapping, ignored in (
            (DEMO_SHEET, I.DEMO_READ_HEADERS, I.DEMO_MAP, DEMO_IGNORED_HEADERS),
            (REVENUE_SHEET, REVENUE_HEADERS, I.REV_MAP, [])):
        if sheet not in wb.sheetnames:
            out["ok"] = False
            out["sheets"].append({"sheet": sheet, "found": False, "missing": [], "rows": 0, "headers": []})
            continue
        sh = I.read_sheet(wb[sheet], headers, mapping, ignored)
        missing = I.demo_missing_required(sh, cfg) if sheet == DEMO_SHEET else sh["missing"]
        out["ok"] = out["ok"] and not missing
        for _, raw in sh["rows"]:
            n = I.p_str(raw.get("bd"))
            if n:
                names.setdefault(n.lower(), n)
        out["sheets"].append({"sheet": sheet, "found": True, "missing": missing, "rows": len(sh["rows"]),
                              "headers": sh["headers"]})
    out["bd_names"] = sorted(names.values(), key=str.lower)
    out["unknown_bds"] = [n for n in out["bd_names"] if n.lower() not in known]
    return out


# ----------------------------------------------------------------------------------------- core
def sync(db: Session, content: bytes) -> dict:
    """Mirror the workbook into the database. Caller commits."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    cfg = load_config(db)
    today = L.now_local(cfg).date()
    bds = {b.name.lower(): b for b in db.query(BDMember).all()}

    def resolve_bd(name):
        if not name:
            return None, "BD is blank"
        b = bds.get(name.lower())
        if not b:
            return None, f"Unknown BD '{name}' - add it under Reports & Settings → BD members"
        return {"bd_id": b.id, "bd_name": b.name}, None

    before_sig = R.ranks_signature(db)
    out = {"alerts": [], "demos": None, "revenue": None}
    for sheet, headers, mapping, ignored, fn in (
            (DEMO_SHEET, I.DEMO_READ_HEADERS, I.DEMO_MAP, DEMO_IGNORED_HEADERS, _sync_demos),
            (REVENUE_SHEET, REVENUE_HEADERS, I.REV_MAP, [], _sync_revenue)):
        if sheet not in wb.sheetnames:
            out["alerts"].append(f"Worksheet '{sheet}' not found in the Google Sheet - nothing synced for it")
            continue
        sh = I.read_sheet(wb[sheet], headers, mapping, ignored)
        missing = I.demo_missing_required(sh, cfg) if sheet == DEMO_SHEET else sh["missing"]
        if missing:
            out["alerts"].append(f"{sheet}: missing column(s) {', '.join(missing)} - nothing synced for it")
            continue
        key = "demos" if sheet == DEMO_SHEET else "revenue"
        out[key] = fn(db, sh["rows"], resolve_bd, today, cfg, out["alerts"], sh["fields_present"])
    db.flush()
    R.emit_rank_events(db, before_sig, ACTOR)
    return out


def _index(records, key_fn):
    idx: dict = {}
    for r in records:
        k = key_fn(r)
        if k:
            idx.setdefault(k, []).append(r)
    return idx


def _pick(cands, claimed, prefer=None):
    free = [c for c in cands if c.id not in claimed]
    if prefer:
        pref = [c for c in free if prefer(c)]
        if pref:
            return pref[0]
    return free[0] if free else None


def _sync_demos(db, rows, resolve_bd, today, cfg, alerts, present=None) -> dict:
    allrecs = db.query(DemoRecord).all()
    live = [r for r in allrecs if r.deleted_at is None]
    by_sl = _index(allrecs, lambda r: (r.sl_no, R.norm(r.customer_name)) if r.sl_no is not None else None)
    by_nat = _index(allrecs, lambda r: (r.bd_id, R.norm(r.customer_name), r.demo_date))
    claimed: set[str] = set()
    res = {"added": 0, "updated": 0, "deleted": 0, "restored": 0, "unchanged": 0, "rejected": [], "duplicates": 0}
    changes = []
    seen = set()
    for r_idx, raw in rows:
        item, d, bd = I.parse_demo_row(r_idx, raw, resolve_bd, today, cfg)
        cust = R.norm(d.get("customer_name"))
        rowkey = (d.get("sl_no"), cust) if d.get("sl_no") is not None else ("nat", bd and bd["bd_id"], cust, d.get("demo_date"))
        if rowkey in seen:
            res["duplicates"] += 1
            res["rejected"].append({"row": r_idx, "label": item["label"], "errors": ["Duplicate Sl No + Customer in the sheet - row ignored"]})
            continue
        seen.add(rowkey)
        prefer_live = lambda c: c.deleted_at is None  # noqa: E731
        rec = None
        if d.get("sl_no") is not None:
            rec = _pick(by_sl.get((d["sl_no"], cust), []), claimed, prefer_live)
        if rec is None and bd:
            rec = _pick(by_nat.get((bd["bd_id"], cust, d.get("demo_date")), []), claimed, prefer_live)
        if rec is not None:
            claimed.add(rec.id)  # claimed even if the row is invalid -> never deleted because of a typo
        if item["errors"]:
            res["rejected"].append({"row": r_idx, "label": item["label"], "errors": item["errors"]})
            continue
        payload = {k: v for k, v in d.items()}
        payload["bd_id"] = bd["bd_id"]
        payload["demo_date"] = d["demo_date"].isoformat() if d.get("demo_date") else None
        payload["demo_time"] = d["demo_time"].isoformat() if d.get("demo_time") else None
        try:
            with db.begin_nested():
                if rec is None:
                    new = R.create_demo(db, payload, ACTOR, source="gsheet", emit=False)
                    claimed.add(new.id)
                    changes.append((None, new))
                    res["added"] += 1
                else:
                    restored = rec.deleted_at is not None
                    if restored:
                        rec.deleted_at = None
                        R.audit(db, ACTOR, "demo", rec.id, "restore", note="row reappeared in Google Sheet")
                    before = R.snapshot_of(rec, R.DEMO_FIELDS)
                    before["_achieved"] = L.is_achieved_demo(rec, cfg)
                    # A column the sheet doesn't have never overwrites what the record already holds.
                    upd = {k: v for k, v in payload.items() if k == "bd_id" or present is None or k in present}
                    R.update_demo(db, rec, upd, ACTOR, source="gsheet", emit=False)
                    after = R.snapshot_of(rec, R.DEMO_FIELDS)
                    if any(before.get(k) != after.get(k) for k in R.DEMO_FIELDS):
                        changes.append((before, rec))
                        res["updated"] += 1
                    elif restored:
                        res["restored"] += 1
                    else:
                        res["unchanged"] += 1
        except R.ValidationError as ex:
            res["rejected"].append({"row": r_idx, "label": item["label"], "errors": ex.errors})
    gone = [r for r in live if r.id not in claimed and r.source != "manual"]
    res["deleted"] = _delete_missing(db, gone, len(live), "demo", alerts)
    _feed(db, changes, "demo")
    return res


def _sync_revenue(db, rows, resolve_bd, today, cfg, alerts, present=None) -> dict:
    allrecs = db.query(RevenueRecord).all()
    live = [r for r in allrecs if r.deleted_at is None]
    by_sl = _index(allrecs, lambda r: (r.sl_no, R.norm(r.customer_name)) if r.sl_no is not None else None)
    by_nat = _index(allrecs, lambda r: (r.bd_id, R.norm(r.customer_name), R.norm(r.opportunity_name)))
    claimed: set[str] = set()
    res = {"added": 0, "updated": 0, "deleted": 0, "restored": 0, "unchanged": 0, "rejected": [], "duplicates": 0}
    changes = []
    seen = set()
    for r_idx, raw in rows:
        item, d, bd = I.parse_revenue_row(r_idx, raw, resolve_bd)
        cust = R.norm(d.get("customer_name"))
        rowkey = (d.get("sl_no"), cust) if d.get("sl_no") is not None else ("nat", bd and bd["bd_id"], cust, R.norm(d.get("opportunity_name")))
        if rowkey in seen:
            res["duplicates"] += 1
            res["rejected"].append({"row": r_idx, "label": item["label"], "errors": ["Duplicate row in the sheet - counted once, row ignored"]})
            continue
        seen.add(rowkey)
        prefer_live = lambda c: c.deleted_at is None  # noqa: E731
        rec = None
        if d.get("sl_no") is not None:
            rec = _pick(by_sl.get((d["sl_no"], cust), []), claimed, prefer_live)
        if rec is None and bd:
            rec = _pick(by_nat.get((bd["bd_id"], cust, R.norm(d.get("opportunity_name"))), []), claimed, prefer_live)
        if rec is not None:
            claimed.add(rec.id)
        if item["errors"]:
            res["rejected"].append({"row": r_idx, "label": item["label"], "errors": item["errors"]})
            continue
        payload = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in d.items()}
        payload["bd_id"] = bd["bd_id"]
        try:
            with db.begin_nested():
                if rec is None:
                    new = R.create_revenue(db, payload, ACTOR, source="gsheet", emit=False)
                    claimed.add(new.id)
                    changes.append((None, new))
                    res["added"] += 1
                else:
                    restored = rec.deleted_at is not None
                    if restored:
                        rec.deleted_at = None
                        R.audit(db, ACTOR, "revenue", rec.id, "restore", note="row reappeared in Google Sheet")
                    before = R.snapshot_of(rec, R.REVENUE_FIELDS)
                    R.update_revenue(db, rec, payload, ACTOR, source="gsheet", emit=False)
                    after = R.snapshot_of(rec, R.REVENUE_FIELDS)
                    if any(before.get(k) != after.get(k) for k in R.REVENUE_FIELDS):
                        changes.append((before, rec))
                        res["updated"] += 1
                    elif restored:
                        res["restored"] += 1
                    else:
                        res["unchanged"] += 1
        except R.ValidationError as ex:
            res["rejected"].append({"row": r_idx, "label": item["label"], "errors": ex.errors})
    gone = [r for r in live if r.id not in claimed and r.source != "manual"]
    res["deleted"] = _delete_missing(db, gone, len(live), "revenue", alerts)
    _feed(db, changes, "revenue")
    return res


def _delete_missing(db, gone, live_count, entity, alerts) -> int:
    if not gone:
        return 0
    if len(gone) > max(3, MAX_DELETE_SHARE * live_count):
        alerts.append(f"{len(gone)} {entity} record(s) are no longer in the sheet - more than 25% of all records, "
                      f"so NOTHING was deleted (safety check). If this is intended, remove them in smaller batches.")
        return 0
    for r in gone:
        r.deleted_at = utcnow()
        R.audit(db, ACTOR, entity, r.id, "delete", before={"customer_name": r.customer_name},
                note="row removed from Google Sheet")
        R.activity(db, f"{entity}_deleted", f"{r.customer_name} removed from the Google Sheet", r.bd_id, ACTOR)
    return len(gone)


def _feed(db, changes, entity):
    """Activity feed: per-record messages for normal edits, one summary line for bulk changes."""
    if not changes:
        return
    if len(changes) > 25:
        R.activity(db, "import", f"Google Sheet sync: {len(changes)} {entity} records added/updated", None, ACTOR)
        return
    for before, rec in changes:
        db.refresh(rec)
        if entity == "demo":
            R._demo_activity(db, before, rec, ACTOR)
        else:
            if before is None:
                R.activity(db, "revenue_updated", f"{rec.bd.name}: {rec.customer_name} – {rec.opportunity_name} "
                           f"{rec.contract_status} ({rec.currency} {float(rec.contract_value):,.0f})", rec.bd_id, ACTOR)
            elif before.get("contract_status") != rec.contract_status:
                R.activity(db, "revenue_updated", f"{rec.bd.name}: {rec.customer_name} – {before['contract_status']} → "
                           f"{rec.contract_status}", rec.bd_id, ACTOR)
            else:
                R.activity(db, "revenue_updated", f"{rec.bd.name}: {rec.customer_name} – {rec.opportunity_name} updated",
                           rec.bd_id, ACTOR)


# ----------------------------------------------------------------------------------------- runner
def run_once(db: Session, force: bool = False) -> dict:
    """Fetch + sync, record status in settings. Never raises (errors land in the status)."""
    if not _lock.acquire(blocking=False):
        return load_raw(db).get(STATUS_KEY) or {}
    try:
        raw = load_raw(db)
        status = dict(raw.get(STATUS_KEY) or {})
        status["last_attempt"] = _now_iso()
        try:
            content, title = fetch_xlsx(raw.get("gsheet_url") or "")
            if title:
                status["sheet_title"] = title
            sha = hashlib.sha256(content).hexdigest()
            if sha == status.get("sha") and not force and not status.get("error"):
                status["last_success"] = _now_iso()
            else:
                summary = sync(db, content)
                status.update(sha=sha, last_success=_now_iso(), summary=summary, error=None)
                d, rv = summary.get("demos") or {}, summary.get("revenue") or {}
                if any((x or {}).get(k) for x in (d, rv) for k in ("added", "updated", "deleted", "restored")):
                    status["last_change"] = _now_iso()
            status["error"] = None
        except Exception as e:  # network / parsing - keep last good data
            db.rollback()
            log.warning("Google Sheet sync failed: %s", e)
            status["error"] = str(e)
        save_setting(db, STATUS_KEY, status)
        db.commit()
        return status
    finally:
        _lock.release()


def start_worker(session_factory):
    """One background thread syncs every active team's sheet, each on its own interval."""
    from ..models import Team
    from ..tenancy import bind_team, unscoped

    def loop():
        last: dict[int, float] = {}
        while True:
            try:
                with session_factory() as db:
                    team_ids = [t.id for t in unscoped(db).query(Team).filter(Team.active.is_(True)).all()]
                for tid in team_ids:
                    with session_factory() as db:
                        bind_team(db, tid)
                        raw = load_raw(db)
                        every = max(30, int(raw.get("gsheet_sync_interval_seconds") or 60))
                        if raw.get("gsheet_sync_enabled") and raw.get("gsheet_url") and \
                                _time.time() - last.get(tid, 0.0) >= every:
                            last[tid] = _time.time()
                            run_once(db)
            except Exception:  # pragma: no cover - never let the worker die
                log.exception("sync worker error")
            _time.sleep(5)

    t = threading.Thread(target=loop, name="gsheet-sync", daemon=True)
    t.start()
    return t
