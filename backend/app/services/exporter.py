"""Excel export. Operational sheets keep the finalised worksheet names, column order and dropdowns."""
from __future__ import annotations

import io
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from ..constants import (CONTRACT_STATUSES, CURRENCY_OPTIONS, DEMO_HEADERS, DEMO_ON_OPTIONS, DEMO_SHEET,
                         DEMO_STATUSES, DEMO_TYPES, POC_STATUSES, REVENUE_HEADERS, REVENUE_SHEET)

HEAD_FILL = PatternFill("solid", fgColor="0B1A3A")
HEAD_FONT = Font(bold=True, color="F5C542")


def _header(ws, headers):
    ws.append(headers)
    for c in ws[1]:
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, min(40, len(str(h)) + 6))


def _dv(ws, col_idx: int, values: list[str], n: int):
    if not values:
        return
    formula = '"' + ",".join(values) + '"'
    if len(formula) > 255:
        return  # Excel limit for inline lists
    dv = DataValidation(type="list", formula1=formula, allow_blank=True)
    col = get_column_letter(col_idx)
    dv.add(f"{col}2:{col}{max(n + 1, 200)}")
    ws.add_data_validation(dv)


def _date_fmt(ws, col_idx: int, fmt="yyyy-mm-dd"):
    for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
        for c in row:
            c.number_format = fmt


def write_demo_sheet(wb: Workbook, demos: list, bd_names: list[str], title: str = DEMO_SHEET):
    ws = wb.create_sheet(title)
    _header(ws, DEMO_HEADERS)
    for i, d in enumerate(demos, start=2):
        ws.append([
            d.sl_no, d.bd.name, d.customer_name, d.domain, d.country, d.demo_type, d.demo_on, d.demo_date,
            d.demo_time, d.time_zone,
            # Same live formula the workbook uses (Demo Date = H, Demo Time = I).
            f'=IF(H{i}="","",IF(H{i}+I{i}<=NOW(),"0 Hrs 0 Min",INT((H{i}+I{i}-NOW())*24) & " Hrs " & '
            f'MOD(INT((H{i}+I{i}-NOW())*1440),60) & " Min"))',
            d.status, d.qualified,
        ])
    _date_fmt(ws, 8)
    _date_fmt(ws, 9, "hh:mm")
    n = len(demos)
    _dv(ws, 2, bd_names, n)
    _dv(ws, 6, DEMO_TYPES, n)
    _dv(ws, 7, DEMO_ON_OPTIONS, n)
    _dv(ws, 12, DEMO_STATUSES, n)
    _dv(ws, 13, ["Yes", "No"], n)
    return ws


def write_revenue_sheet(wb: Workbook, revs: list, bd_names: list[str], title: str = REVENUE_SHEET):
    ws = wb.create_sheet(title)
    _header(ws, REVENUE_HEADERS)
    for r in revs:
        ws.append([r.sl_no, r.bd.name, r.customer_name, r.country, r.domain, r.opportunity_name, r.contract_status,
                   r.currency, float(r.contract_value), r.contract_signed_date, r.amount_credited_date,
                   r.customer_onboarding_date, r.remarks])
    for c in (10, 11, 12):
        _date_fmt(ws, c)
    n = len(revs)
    _dv(ws, 2, sorted(bd_names), n)
    _dv(ws, 7, CONTRACT_STATUSES, n)
    _dv(ws, 8, sorted(set(CURRENCY_OPTIONS) | {r.currency for r in revs}), n)
    return ws


def write_table(wb: Workbook, title: str, headers: list[str], rows: list[list]):
    ws = wb.create_sheet(title[:31])
    _header(ws, headers)
    for r in rows:
        ws.append(r)
    return ws


def poc_rows(demos: list) -> list[list]:
    return [[d.bd.name, d.customer_name, f"{d.demo_on or 'Demo'} on {d.demo_date.isoformat() if d.demo_date else '—'}",
             d.status, d.poc_started_on, d.poc_status_updated_at or d.updated_at, d.poc_remarks]
            for d in demos if d.status in POC_STATUSES]


POC_HEADERS = ["BD", "Customer Name", "Related Demo", "POC Status", "POC Start Date", "Last Updated", "Remarks"]


def performance_rows(snap: dict) -> list[list]:
    rows = []
    rev = {r["bd_id"]: r for r in snap["revenue"]["per_bd"]}
    for r in snap["overall"]:
        dd = snap["daily"]["per_bd"].get(r["bd_id"], {})
        rv = rev.get(r["bd_id"], {})
        rows.append([r["rank"], r["bd_name"], r["total"], r["f2f"], r["virtual"], r["untyped"], r["scheduled"],
                     dd.get("targets_assigned"), dd.get("targets_achieved"), dd.get("targets_missed"),
                     dd.get("achievement_rate"), dd.get("current_pending"), dd.get("best_streak"),
                     rv.get("total_inr"), "Yes" if rv.get("award_eligible") else "No"])
    return rows


PERF_HEADERS = ["Rank", "BD", "Qualified Completed Demos", "Qualified F2F", "Qualified Virtual",
                "Qualified (Type blank)", "Scheduled Demos", "Targets Assigned", "Targets Achieved", "Targets Missed",
                "Achievement Rate %", "Pending Carry-Forward", "Best Streak", "Confirmed Revenue (INR)",
                "₹10L Eligible"]


def daily_rows(snap: dict) -> list[list]:
    rows = []
    for bd in snap["daily"]["per_bd"].values():
        for d in bd["days"]:
            rows.append([d["date"], bd["bd_name"], d["required"], d["done"], d["pending_before"],
                         d.get("pending_after") if d["closed"] else d.get("projected_pending"),
                         d["status"], "Final" if d["closed"] else "Open (provisional)"])
    rows.sort(key=lambda x: (x[0], x[1]))
    return rows


DAILY_HEADERS = ["Date", "BD", "Required Target", "Qualified Done", "Pending Before", "Pending After",
                 "Status", "Day State"]


def leaderboard_sheets(wb: Workbook, snap: dict):
    gen = f"Official League Standings (full league data) · generated {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws = write_table(wb, "Official_Leaderboard", ["Rank", "BD", "Total Qualified", "F2F", "Virtual",
                                                  "Daily Target Achievement %", "Confirmed Revenue (INR)"],
                     [[r["rank"], r["bd_name"], r["total"], r["f2f"], r["virtual"], r["achievement_rate"],
                       r["revenue_inr"]] for r in snap["overall"]])
    ws.insert_rows(1)
    ws["A1"] = gen
    write_table(wb, "F2F_Leaderboard", ["Rank", "BD", "Qualified Completed F2F (challenge regions)",
                                        "Scheduled F2F"],
                [[r["rank"], r["bd_name"], r["f2f"], r["scheduled_f2f"]] for r in snap["f2f"]["leaderboard"]])
    write_table(wb, "Revenue_Leaderboard", ["Rank", "BD", "Confirmed League Revenue (INR)", "₹10L Eligible",
                                            "Gap to Leader (INR)", "Pending Conversion Records"],
                [[r["rank"], r["bd_name"], r["total_inr"], "Yes" if r["award_eligible"] else "No",
                  r["gap_to_leader"], r["pending_conversion"]] for r in snap["revenue"]["per_bd"]])
    rows = []
    for w in snap["weeks"]:
        for s in w["standings"]:
            rows.append([w["label"], w["start"], w["end"], w["state"], s["rank"], s["bd_name"], s["total"]])
    write_table(wb, "Weekly_Standings", ["Week", "From", "To", "State", "Rank", "BD", "Qualified Demos"], rows)


def to_bytes(wb: Workbook) -> bytes:
    if "Sheet" in wb.sheetnames and len(wb.sheetnames) > 1:
        del wb["Sheet"]
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def new_wb() -> Workbook:
    return Workbook()


def _fmt(v):
    return v.isoformat() if isinstance(v, (date, datetime)) else v
