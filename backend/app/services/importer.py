"""Excel import: parse -> validate -> match -> preview -> (admin confirms) -> apply.

Matching never relies on row numbers / Sl No. Demo identity = (BD, customer, demo date); revenue
identity = (BD, customer, opportunity). Anything ambiguous is flagged for admin review. Blank cells
in the file never erase values already in the database. Updates are applied only when ticked.
"""
from __future__ import annotations

import hashlib
import io
import re
import warnings
from datetime import date, datetime, time

import openpyxl
from sqlalchemy.orm import Session

from ..config import load_config
from ..constants import (CONTRACT_STATUSES, DEMO_HEADERS, DEMO_IGNORED_HEADERS, DEMO_SHEET, DEMO_STATUSES,
                         DEMO_TYPES, POC_STATUSES, REVENUE_HEADERS, REVENUE_SHEET)
from ..models import BDMember, DemoRecord, ImportHistory, RevenueRecord, utcnow
from . import league as L
from . import records as R

DEMO_MAP = {"Sl No": "sl_no", "BD": "bd", "Customer Name": "customer_name", "Domain": "domain",
            "Country": "country", "Demo Type": "demo_type", "Demo On": "demo_on", "Demo Date": "demo_date",
            "Demo Time": "demo_time", "Time Zone": "time_zone", "Status": "status", "Qualified Demo": "qualified"}
REV_MAP = {"Sl No": "sl_no", "BD": "bd", "Customer Name": "customer_name", "Country": "country", "Domain": "domain",
           "Opportunity Name": "opportunity_name", "Contract Status": "contract_status", "Currency": "currency",
           "Contract Value": "contract_value", "Contract Signed Date": "contract_signed_date",
           "Amount Credited Date": "amount_credited_date", "Customer Onboarding Date": "customer_onboarding_date",
           "Remarks": "remarks"}
DEMO_COMPARE = ["sl_no", "domain", "country", "demo_type", "demo_on", "demo_date", "demo_time", "time_zone",
                "status", "qualified"]
REV_COMPARE = ["sl_no", "country", "domain", "contract_status", "currency", "contract_value",
               "contract_signed_date", "amount_credited_date", "customer_onboarding_date", "remarks"]
KNOWN_OTHER_SHEETS = {"Post_Demos", "Stats", "Dashboard", "Different_Strategies", "Different Strategies", "League_Demo"}


# ------------------------------------------------------------------------------------- cell parsing
def _hkey(h) -> str:
    return " ".join(str(h or "").replace("\n", " ").split()).lower()


def p_str(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = " ".join(str(v).split())
    return s or None


_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y",
                 "%B %d, %Y", "%d.%m.%Y", "%Y/%m/%d"]


def p_date(v) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:  # Excel serial
        return openpyxl.utils.datetime.from_excel(v).date()
    s = str(v).strip()
    for f in _DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    raise ValueError(f"Unrecognised date '{s}'")


def p_time(v) -> time | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.time().replace(second=0, microsecond=0)
    if isinstance(v, time):
        return v.replace(second=0, microsecond=0)
    if isinstance(v, (int, float)) and 0 <= v < 1:
        mins = round(v * 1440)
        return time(mins // 60 % 24, mins % 60)
    s = str(v).strip().upper().replace(".", ":")
    for f in ("%H:%M", "%I:%M %p", "%I:%M%p", "%I %p", "%H:%M:%S"):
        try:
            return datetime.strptime(s, f).time()
        except ValueError:
            pass
    raise ValueError(f"Unrecognised time '{v}'")


def p_int(v) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def canon(v: str | None, allowed: list[str]) -> tuple[str | None, bool]:
    """Return (canonical value, was_recased). Unknown -> (original, False) flagged by caller."""
    if v is None:
        return None, False
    for a in allowed:
        if a == v:
            return a, False
    for a in allowed:
        if a.lower() == v.lower():
            return a, True
    return v, False


def _jsonable(d: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, (date, time, datetime)) else
                (float(v) if hasattr(v, "as_tuple") else v)) for k, v in d.items()}


# ------------------------------------------------------------------------------------- sheet reading
def read_sheet(ws, expected: list[str], mapping: dict, ignored: list[str]) -> dict:
    header_cells = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    by_key = {}
    for idx, h in enumerate(header_cells):
        if h not in (None, ""):
            by_key.setdefault(_hkey(h), idx)
    missing = [h for h in expected if _hkey(h) not in by_key]
    present = [str(h).strip() for h in header_cells if h not in (None, "")]
    expected_keys = {_hkey(h) for h in expected}
    unexpected = [h for h in present if _hkey(h) not in expected_keys]
    ignored_known = [h for h in unexpected if _hkey(h) in {_hkey(x) for x in ignored}]
    unexpected = [h for h in unexpected if h not in ignored_known]
    order_ok = [h for h in present if _hkey(h) in expected_keys] == [h for h in expected if _hkey(h) in by_key]
    rows = []
    for r_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        rec = {}
        for header, field in mapping.items():
            i = by_key.get(_hkey(header))
            rec[field] = row[i] if i is not None and i < len(row) else None
        if all(rec.get(f) in (None, "") for f in mapping.values() if f != "sl_no"):
            continue
        rows.append((r_idx, rec))
    return {"missing": missing, "unexpected": unexpected, "ignored": ignored_known, "order_ok": order_ok,
            "headers": present, "rows": rows}


def dropdown_values(ws, col_letter: str) -> list[str]:
    for dv in ws.data_validations.dataValidation:
        if dv.type == "list" and any(str(rng).startswith(col_letter) for rng in str(dv.sqref).split()):
            f = (dv.formula1 or "").strip('"')
            return [x.strip() for x in re.sub(r'"\s*&\s*"', "", f).split(",") if x.strip()]
    return []


# ------------------------------------------------------------------------------------- build preview
def build_preview(db: Session, content: bytes, filename: str, actor: str) -> ImportHistory:
    sha = hashlib.sha256(content).hexdigest()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    cfg = load_config(db)
    today = L.now_local(cfg).date()
    bd_by_name = {b.name.lower(): b for b in db.query(BDMember).all()}
    sheet_names = wb.sheetnames
    report = {"sheets_found": sheet_names, "sheet_issues": [], "bd_proposals": [], "demos": [], "revenue": [],
              "ignored_sheets": [s for s in sheet_names if s not in (DEMO_SHEET, REVENUE_SHEET)],
              "previously_imported": None}
    prev = (db.query(ImportHistory).filter(ImportHistory.file_sha256 == sha, ImportHistory.status == "applied")
            .order_by(ImportHistory.id.desc()).first())
    if prev:
        report["previously_imported"] = {"id": prev.id, "at": prev.applied_at.isoformat() + "Z", "filename": prev.filename}

    # BD names proposed from the workbook (dropdown lists + data) that are not yet configured.
    proposed: dict[str, str] = {}

    def resolve_bd(name):
        if not name:
            return None, "BD is blank"
        b = bd_by_name.get(name.lower())
        if b:
            return {"bd_id": b.id, "bd_name": b.name}, None
        proposed.setdefault(name.lower(), name)
        return {"bd_id": None, "bd_name": name}, None

    for sheet, expected in ((DEMO_SHEET, DEMO_HEADERS), (REVENUE_SHEET, REVENUE_HEADERS)):
        if sheet not in sheet_names:
            alt = next((s for s in sheet_names if s.lower().replace(" ", "_") == sheet.lower()), None)
            report["sheet_issues"].append({"sheet": sheet, "level": "error",
                                           "message": f"Worksheet '{sheet}' not found" +
                                           (f" (found similar '{alt}' - rename it to '{sheet}')" if alt else "")})
    if DEMO_SHEET in sheet_names:
        ws = wb[DEMO_SHEET]
        for n in dropdown_values(ws, "B"):
            if n.lower() not in bd_by_name:
                proposed.setdefault(n.lower(), n)
        sh = read_sheet(ws, DEMO_HEADERS, DEMO_MAP, DEMO_IGNORED_HEADERS)
        _sheet_header_issues(report, DEMO_SHEET, sh, ["Time Remaining"])
        if not [m for m in sh["missing"] if m != "Time Remaining"]:
            report["demos"] = _preview_demos(db, sh["rows"], resolve_bd, today, cfg)
    if REVENUE_SHEET in sheet_names:
        ws = wb[REVENUE_SHEET]
        for n in dropdown_values(ws, "B"):
            if n.lower() not in bd_by_name:
                proposed.setdefault(n.lower(), n)
        sh = read_sheet(ws, REVENUE_HEADERS, REV_MAP, [])
        _sheet_header_issues(report, REVENUE_SHEET, sh, [])
        if not sh["missing"]:
            report["revenue"] = _preview_revenue(db, sh["rows"], resolve_bd)
    report["bd_proposals"] = sorted(proposed.values(), key=str.lower)
    for kind in ("demos", "revenue"):
        rows = report[kind]
        report[f"{kind}_counts"] = {a: sum(1 for r in rows if r["action"] == a)
                                    for a in ("add", "update", "unchanged", "review", "duplicate", "rejected")}
    hist = ImportHistory(filename=filename, file_sha256=sha, status="preview", preview=report, created_by=actor)
    db.add(hist)
    db.flush()
    return hist


def _sheet_header_issues(report, sheet, sh, optional):
    miss = [m for m in sh["missing"] if m not in optional]
    if miss:
        report["sheet_issues"].append({"sheet": sheet, "level": "error",
                                       "message": f"Missing required column(s): {', '.join(miss)} - sheet not imported"})
    if sh["ignored"]:
        report["sheet_issues"].append({"sheet": sheet, "level": "info",
                                       "message": f"Columns not tracked by the app (ignored): {', '.join(sh['ignored'])}"})
    if sh["unexpected"]:
        report["sheet_issues"].append({"sheet": sheet, "level": "warning",
                                       "message": f"Unexpected column(s) ignored: {', '.join(sh['unexpected'])}"})
    if not sh["order_ok"]:
        report["sheet_issues"].append({"sheet": sheet, "level": "warning",
                                       "message": "Column order differs from the expected structure (mapped by header name)"})


def _row_base(r_idx):
    return {"row": r_idx, "errors": [], "warnings": [], "data": {}, "diff": {}, "kept": {}, "match_id": None,
            "candidates": [], "selected": False}


def parse_demo_row(r_idx, raw, resolve_bd, today: date, cfg):
    """Validate one Demos_and_Pipelines row. Returns (item, cleaned_values, bd_ref)."""
    item = _row_base(r_idx)
    e, w = item["errors"], item["warnings"]
    d = {}
    d["sl_no"] = p_int(raw["sl_no"])
    bd, err = resolve_bd(p_str(raw["bd"]))
    if err:
        e.append(err)
    d["customer_name"] = p_str(raw["customer_name"])
    if not d["customer_name"]:
        e.append("Customer Name is blank")
    for f in ("domain", "country", "demo_on", "time_zone"):
        d[f] = p_str(raw[f])
    dt, recased = canon(p_str(raw["demo_type"]), DEMO_TYPES)
    if dt is not None and dt not in DEMO_TYPES:
        e.append(f"Invalid Demo Type '{dt}' (allowed: F2F, Virtual)")
    elif recased:
        w.append(f"Demo Type normalised to '{dt}'")
    d["demo_type"] = dt
    st, recased = canon(p_str(raw["status"]), DEMO_STATUSES)
    if st is None:
        e.append("Status is blank")
    elif st not in DEMO_STATUSES:
        e.append(f"Invalid Status '{st}'")
    elif recased:
        w.append(f"Status normalised to '{st}'")
    d["status"] = st
    q, recased = canon(p_str(raw["qualified"]), ["Yes", "No"])
    if q is not None and q not in ("Yes", "No"):
        e.append(f"Invalid Qualified Demo '{q}' (allowed: Yes, No)")
    d["qualified"] = q
    try:
        d["demo_date"] = p_date(raw["demo_date"])
    except ValueError as ex:
        e.append(str(ex))
        d["demo_date"] = None
    try:
        d["demo_time"] = p_time(raw["demo_time"])
    except ValueError as ex:
        e.append(str(ex))
        d["demo_time"] = None
    if q == "Yes" and st not in (["Completed"] + POC_STATUSES):
        e.append("Qualified Demo = Yes but Status is not Completed")
    if st == "Completed" and d["demo_date"] and d["demo_date"] > today:
        e.append("Completed demo has a future Demo Date")
    if st == "Completed" and not d["demo_date"]:
        w.append("Completed without Demo Date - cannot count toward any target")
    if st == "Completed" and q is None:
        w.append("Completed but Qualified Demo is blank - will not count until marked Yes")
    if dt is None:
        w.append("Demo Type is blank - excluded from F2F reports until set")
    if d["demo_date"] and not L.in_league(d["demo_date"], cfg):
        w.append("Demo Date is outside the league period - visible but not counted")
    item["data"] = {**_jsonable(d), **(bd or {"bd_id": None, "bd_name": None})}
    item["label"] = f"{(bd or {}).get('bd_name') or '?'} · {d['customer_name'] or '?'}"
    return item, d, bd


def _preview_demos(db: Session, rows, resolve_bd, today: date, cfg) -> list[dict]:
    existing = db.query(DemoRecord).filter(DemoRecord.deleted_at.is_(None)).all()
    seen_keys: dict[tuple, int] = {}
    out = []
    for r_idx, raw in rows:
        item, d, bd = parse_demo_row(r_idx, raw, resolve_bd, today, cfg)
        e, w = item["errors"], item["warnings"]
        if e:
            item["action"] = "rejected"
            out.append(item)
            continue
        key = ((bd["bd_name"] or "").lower(), R.norm(d["customer_name"]), d["demo_date"])
        if key in seen_keys:
            item["action"] = "duplicate"
            w.append(f"Duplicate of row {seen_keys[key]} in this file - skipped")
            out.append(item)
            continue
        seen_keys[key] = r_idx
        exact = [x for x in existing if x.bd.name.lower() == key[0] and R.norm(x.customer_name) == key[1]
                 and x.demo_date == d["demo_date"]]
        same_cust = [x for x in existing if R.norm(x.customer_name) == key[1] and x not in exact]
        if len(exact) == 1:
            _diff(item, exact[0], d, DEMO_COMPARE)
        elif len(exact) > 1 or same_cust:
            item["action"] = "review"
            item["candidates"] = [{"id": x.id, "bd_name": x.bd.name, "customer_name": x.customer_name,
                                   "demo_date": x.demo_date.isoformat() if x.demo_date else None,
                                   "status": x.status, "updated_at": x.updated_at.isoformat()}
                                  for x in (exact or same_cust)]
            w.append("Possible match with an existing record - choose: add as new, update a match, or skip")
        else:
            item["action"] = "add"
            item["selected"] = True
        out.append(item)
    return out


def _cmp(v):
    if isinstance(v, (date, time, datetime)):
        return v.isoformat()
    if hasattr(v, "as_tuple"):
        return float(v)
    return v


def _diff(item, rec, d: dict, fields: list[str]):
    item["match_id"] = rec.id
    item["match_updated_at"] = rec.updated_at.isoformat()
    for f in fields:
        new, old = _cmp(d.get(f)), _cmp(getattr(rec, f))
        if new in (None, ""):
            if old not in (None, ""):
                item["kept"][f] = old  # blank in file never erases existing data
            continue
        if isinstance(new, float) or isinstance(old, float):
            same = old is not None and abs(float(new) - float(old)) < 0.005
        else:
            same = new == old
        if not same:
            item["diff"][f] = {"from": old, "to": new}
    item["action"] = "update" if item["diff"] else "unchanged"
    item["selected"] = False  # updates require an explicit tick


def parse_revenue_row(r_idx, raw, resolve_bd):
    """Validate one League_Revenue row. Returns (item, cleaned_values, bd_ref)."""
    item = _row_base(r_idx)
    e, w = item["errors"], item["warnings"]
    d = {"sl_no": p_int(raw["sl_no"])}
    bd, err = resolve_bd(p_str(raw["bd"]))
    if err:
        e.append(err)
    for f in ("customer_name", "country", "domain", "opportunity_name", "remarks"):
        d[f] = p_str(raw[f])
    if not d["customer_name"]:
        e.append("Customer Name is blank")
    if not d["opportunity_name"]:
        e.append("Opportunity Name is blank")
    cs, _ = canon(p_str(raw["contract_status"]), CONTRACT_STATUSES)
    if cs not in CONTRACT_STATUSES:
        e.append(f"Invalid Contract Status '{cs}' (allowed: Signed, Amount Credited)")
    d["contract_status"] = cs
    cur = p_str(raw["currency"])
    if not cur:
        e.append("Currency is blank")
    d["currency"] = cur.upper() if cur else None
    try:
        v = raw["contract_value"]
        d["contract_value"] = float(str(v).replace(",", "")) if v not in (None, "") else None
        if d["contract_value"] is None:
            e.append("Contract Value is blank")
    except ValueError:
        e.append(f"Contract Value '{raw['contract_value']}' is not a number")
        d["contract_value"] = None
    for f in ("contract_signed_date", "amount_credited_date", "customer_onboarding_date"):
        try:
            d[f] = p_date(raw[f])
        except ValueError as ex:
            e.append(f"{f}: {ex}")
            d[f] = None
    if cs == "Signed" and not d["contract_signed_date"]:
        e.append("Signed but Contract Signed Date is blank")
    if cs == "Amount Credited" and not d["amount_credited_date"]:
        e.append("Amount Credited but Amount Credited Date is blank")
    if d["currency"] and d["currency"] != "INR":
        w.append(f"{d['currency']} value - needs a configured exchange rate before it counts in INR totals")
    item["data"] = {**_jsonable(d), **(bd or {"bd_id": None, "bd_name": None})}
    item["label"] = f"{(bd or {}).get('bd_name') or '?'} · {d['customer_name'] or '?'} · {d['opportunity_name'] or '?'}"
    return item, d, bd


def _preview_revenue(db: Session, rows, resolve_bd) -> list[dict]:
    existing = db.query(RevenueRecord).filter(RevenueRecord.deleted_at.is_(None)).all()
    seen: dict[tuple, int] = {}
    out = []
    for r_idx, raw in rows:
        item, d, bd = parse_revenue_row(r_idx, raw, resolve_bd)
        e, w = item["errors"], item["warnings"]
        if e:
            item["action"] = "rejected"
            out.append(item)
            continue
        key = (bd["bd_name"].lower(), R.norm(d["customer_name"]), R.norm(d["opportunity_name"]))
        if key in seen:
            item["action"] = "duplicate"
            w.append(f"Duplicate of row {seen[key]} in this file - same opportunity counted once; skipped")
            out.append(item)
            continue
        seen[key] = r_idx
        exact = [x for x in existing if x.bd.name.lower() == key[0] and R.norm(x.customer_name) == key[1]
                 and R.norm(x.opportunity_name) == key[2]]
        if len(exact) > 1 and d["contract_signed_date"]:
            narrowed = [x for x in exact if x.contract_signed_date == d["contract_signed_date"]]
            exact = narrowed or exact
        other_bd = [x for x in existing if x.bd.name.lower() != key[0] and R.norm(x.customer_name) == key[1]
                    and R.norm(x.opportunity_name) == key[2]]
        if len(exact) == 1 and not other_bd:
            _diff(item, exact[0], d, REV_COMPARE)
        elif exact or other_bd:
            item["action"] = "review"
            item["candidates"] = [{"id": x.id, "bd_name": x.bd.name, "customer_name": x.customer_name,
                                   "opportunity_name": x.opportunity_name, "contract_status": x.contract_status,
                                   "updated_at": x.updated_at.isoformat()} for x in exact + other_bd]
            w.append("Same customer + opportunity already exists - review to avoid double-counting revenue")
        else:
            item["action"] = "add"
            item["selected"] = True
        out.append(item)
    return out


# ------------------------------------------------------------------------------------- apply
def apply_import(db: Session, hist: ImportHistory, decisions: dict, add_bds: list[str], actor: str) -> dict:
    """decisions: {"demos": {row: {"do": "add"|"update"|"skip", "target_id": optional}}, "revenue": {...}}"""
    if hist.status != "preview":
        raise R.ValidationError([f"Import #{hist.id} is already {hist.status}"])
    before_sig = R.ranks_signature(db)
    summary = {"bds_added": [], "demos": {"added": 0, "updated": 0, "skipped": 0, "rejected": 0, "conflicts": 0,
                                         "errors": []},
               "revenue": {"added": 0, "updated": 0, "skipped": 0, "rejected": 0, "conflicts": 0, "errors": []}}
    existing_names = {b.name.lower(): b for b in db.query(BDMember).all()}
    max_order = max((b.display_order for b in existing_names.values()), default=0)
    for name in add_bds:
        if name.lower() not in existing_names and name in hist.preview.get("bd_proposals", []):
            max_order += 1
            b = BDMember(name=name, display_order=max_order)
            db.add(b)
            db.flush()
            existing_names[name.lower()] = b
            summary["bds_added"].append(name)
            R.audit(db, actor, "bd", b.id, "create", after={"name": name}, note=f"import #{hist.id}")
    for kind, create, update, model in (("demos", R.create_demo, R.update_demo, DemoRecord),
                                        ("revenue", R.create_revenue, R.update_revenue, RevenueRecord)):
        dec = decisions.get(kind, {}) or {}
        s = summary[kind]
        for item in hist.preview.get(kind, []):
            if item["action"] in ("rejected",):
                s["rejected"] += 1
                continue
            choice = dec.get(str(item["row"])) or {}
            do = choice.get("do") or ("add" if item["action"] == "add" and item.get("selected") else "skip")
            if do == "skip" or item["action"] in ("duplicate", "unchanged") and do != "add":
                s["skipped"] += 1
                continue
            data = dict(item["data"])
            bd = existing_names.get((data.pop("bd_name") or "").lower())
            data.pop("bd_id", None)
            if bd is None:
                s["errors"].append(f"Row {item['row']}: BD not configured (not added)")
                s["rejected"] += 1
                continue
            data["bd_id"] = bd.id
            data = {k: v for k, v in data.items() if v is not None or do == "add"}
            try:
                with db.begin_nested():
                    if do == "add":
                        create(db, data, actor, source="import", emit=False)
                        s["added"] += 1
                    elif do == "update":
                        target_id = choice.get("target_id") or item.get("match_id")
                        rec = db.get(model, target_id) if target_id else None
                        if rec is None or rec.deleted_at is not None:
                            raise R.ValidationError(["matched record no longer exists"])
                        if item.get("match_id") == target_id and item.get("match_updated_at") and \
                                rec.updated_at.isoformat() != item["match_updated_at"]:
                            s["conflicts"] += 1
                            raise R.ValidationError(["record was edited after the preview - re-run the import"])
                        upd = {k: v for k, v in data.items() if v is not None and k not in ("bd_id",)}
                        if choice.get("target_id") and choice.get("target_id") != item.get("match_id"):
                            upd["bd_id"] = bd.id
                        update(db, rec, upd, actor, source="import", emit=False)
                        s["updated"] += 1
                    else:
                        s["skipped"] += 1
            except R.ValidationError as ex:
                s["errors"].append(f"Row {item['row']}: {'; '.join(ex.errors)}")
                s["rejected"] += 1
    hist.status = "applied"
    hist.applied_at = utcnow()
    hist.summary = summary
    R.audit(db, actor, "import", hist.id, "import_apply", after=summary, note=hist.filename)
    d, rv = summary["demos"], summary["revenue"]
    R.activity(db, "import", f"Workbook imported: {d['added']} demos added, {d['updated']} updated; "
               f"{rv['added']} revenue records added, {rv['updated']} updated", None, actor)
    R.emit_rank_events(db, before_sig, actor)
    return summary
