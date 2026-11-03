"""THE single business-logic layer. Every screen, report, export and award reads from here.

All functions are pure: they take raw records (ORM rows or any object with the same attributes),
the league config and `now`, and return derived values. Nothing derived is ever persisted as an
editable figure.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Iterable, Protocol
from zoneinfo import ZoneInfo

from ..config import LeagueConfig
from ..constants import POC_STATUSES


# --------------------------------------------------------------------------------------- inputs
class DemoLike(Protocol):
    id: str
    bd_id: int
    customer_name: str
    country: str | None
    domain: str | None
    demo_type: str | None
    demo_date: date | None
    status: str
    qualified: str | None
    demo_completed: bool
    deleted_at: datetime | None


@dataclass
class BDRef:
    id: int
    name: str


# --------------------------------------------------------------------------------------- time
def now_local(cfg: LeagueConfig, now: datetime | None = None) -> datetime:
    tz = ZoneInfo(cfg.timezone)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def is_working_day(d: date) -> bool:
    """Monday-Saturday are working days. Sunday is the weekly holiday."""
    return d.weekday() != 6


def working_days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if is_working_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def next_working_day(d: date) -> date:
    d += timedelta(days=1)
    while not is_working_day(d):
        d += timedelta(days=1)
    return d


def day_is_closed(d: date, cfg: LeagueConfig, now: datetime, manual_closures: set[date]) -> bool:
    """A day is final once the admin closes it, or once its cutoff time has passed."""
    if d in manual_closures:
        return True
    tz = ZoneInfo(cfg.timezone)
    cutoff = datetime.combine(d, cfg.day_cutoff_time, tzinfo=tz)
    return now_local(cfg, now) >= cutoff


# --------------------------------------------------------------------------------------- regions
_SPLIT = re.compile(r"[,/&;()|]+|\band\b")


def region_of(country: str | None, cfg: LeagueConfig) -> str | None:
    """Map the free-text Country field to an F2F challenge region (or None)."""
    if not country:
        return None
    whole = country.strip().lower()
    tokens = {t.strip(" .") for t in _SPLIT.split(whole) if t.strip(" .")}
    tokens.add(whole)
    for region, aliases in cfg.f2f_regions.items():
        for a in aliases:
            if a in tokens:
                return region
    return None


# --------------------------------------------------------------------------------------- demo rules
def is_achieved_demo(d: DemoLike) -> bool:
    """Qualified completed demo. A completed+qualified demo keeps counting when it moves into POC."""
    if getattr(d, "deleted_at", None) is not None or d.demo_date is None:
        return False
    if d.qualified != "Yes":
        return False
    if d.status == "Completed":
        return True
    return d.status in POC_STATUSES and bool(d.demo_completed)


def in_league(d: date | None, cfg: LeagueConfig) -> bool:
    return d is not None and cfg.league_start <= d <= cfg.league_end


def counts_for_league(d: DemoLike, cfg: LeagueConfig, upto: date | None = None) -> bool:
    if not is_achieved_demo(d) or not in_league(d.demo_date, cfg):
        return False
    return upto is None or d.demo_date <= upto


def counts_for_f2f(d: DemoLike, cfg: LeagueConfig) -> bool:
    return counts_for_league(d, cfg) and d.demo_type == "F2F" and region_of(d.country, cfg) is not None


def live(demos: Iterable[DemoLike]) -> list[DemoLike]:
    return [d for d in demos if getattr(d, "deleted_at", None) is None]


# --------------------------------------------------------------------------------------- ranking
def competition_rank(items: list[dict], key: str) -> list[dict]:
    """Standard competition ranking (1,2,2,4). Ties share a rank; display order is by name."""
    ordered = sorted(items, key=lambda x: (-float(x[key]), x["bd_name"].lower()))
    for it in ordered:
        it["rank"] = 1 + sum(1 for o in ordered if float(o[key]) > float(it[key]))
    return ordered


# --------------------------------------------------------------------------------------- daily targets
def compute_daily_targets(cfg: LeagueConfig, bds: list[BDRef], demos: Iterable[DemoLike],
                          manual_closures: set[date], now: datetime | None = None) -> dict:
    """Carry-forward engine, independent per BD.

    Required(d)  = daily_target + pending_before(d)
    pending_after(d) = max(0, pending_before(d) + daily_target - qualified_done(d))  [closed days only]
    Sundays never create a target; pending survives Sunday unchanged. The open (current) day is
    never marked missed; it is finalised only by cutoff or manual closure.
    """
    now_l = now_local(cfg, now)
    today = now_l.date()
    base = cfg.daily_target

    per_day: dict[int, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for d in live(demos):
        if counts_for_league(d, cfg):
            per_day[d.bd_id][d.demo_date] += 1

    league_days = working_days(cfg.league_start, cfg.league_end)
    league_over = all(day_is_closed(x, cfg, now_l, manual_closures) for x in league_days) if league_days else True
    result = {}
    for bd in bds:
        pending = 0
        days, achieved, missed, streak, best_streak = [], 0, 0, 0, 0
        today_entry = None
        for d in league_days:
            if d > today:
                break
            required = base + pending
            done = per_day[bd.id].get(d, 0)
            closed = day_is_closed(d, cfg, now_l, manual_closures)
            entry = {"date": d.isoformat(), "required": required, "done": done, "pending_before": pending,
                     "closed": closed}
            if closed:
                new_pending = max(0, pending + base - done)
                ok = done >= required
                entry.update(status="Target Achieved" if ok else "Target Missed", pending_after=new_pending)
                if ok:
                    achieved += 1
                    streak += 1
                    best_streak = max(best_streak, streak)
                else:
                    missed += 1
                    streak = 0
                pending = new_pending
            else:
                # Open day (today, before cutoff/closure). Never declare it missed.
                if done >= required:
                    st = "Target Achieved"
                elif done > 0:
                    st = "In Progress"
                elif now_l.time() < cfg.office_login_time:
                    st = "Not Started"
                elif pending > 0:
                    st = "Carry-Forward Pending"
                else:
                    st = "Target Pending Today"
                entry.update(status=st, pending_after=None,
                             projected_pending=max(0, pending + base - done))
            days.append(entry)
            if d == today:
                today_entry = entry

        closed_days = [e for e in days if e["closed"]]
        live_streak = streak + (1 if today_entry and not today_entry["closed"]
                                and today_entry["status"] == "Target Achieved" else 0)
        # What the BD must do on the next working day (none after the league ends).
        if today_entry and not today_entry["closed"]:
            next_day, next_required = today, today_entry["required"]
        else:
            nd = next_working_day(today) if today >= cfg.league_start else (
                cfg.league_start if is_working_day(cfg.league_start) else next_working_day(cfg.league_start))
            if nd > cfg.league_end:
                next_day, next_required = None, None
            else:
                next_day, next_required = nd, base + pending
        result[bd.id] = {
            "bd_id": bd.id,
            "bd_name": bd.name,
            "days": days,
            "today": today_entry,
            "current_pending": pending,
            "next_target_date": next_day.isoformat() if next_day else None,
            "next_required": next_required,
            "targets_assigned": len(closed_days),
            "targets_achieved": achieved,
            "targets_missed": missed,
            "achievement_rate": round(100 * achieved / len(closed_days), 1) if closed_days else None,
            "current_streak": live_streak,
            "best_streak": max(best_streak, live_streak),
            "outstanding_carry_forward": pending if league_over else None,
        }
    return {
        "today": today.isoformat(),
        "is_working_day": is_working_day(today),
        "within_league": cfg.league_start <= today <= cfg.league_end,
        "league_over": league_over,
        "today_closed": day_is_closed(today, cfg, now_l, manual_closures) if is_working_day(today) else None,
        "manually_closed_today": today in manual_closures,
        "cutoff": cfg.day_cutoff_time.strftime("%H:%M"),
        "per_bd": result,
    }


# --------------------------------------------------------------------------------------- weeks
def league_weeks(cfg: LeagueConfig) -> list[dict]:
    """Weekly periods using the configured week start day. A leading/trailing fragment with no
    working days (e.g. Sunday 1 Nov 2026) is merged into the adjacent week so no week is empty."""
    periods, start = [], cfg.league_start
    while start <= cfg.league_end:
        end = start
        while end + timedelta(days=1) <= cfg.league_end and (end + timedelta(days=1)).weekday() != cfg.week_start_day:
            end += timedelta(days=1)
        periods.append([start, end])
        start = end + timedelta(days=1)
    merged: list[list[date]] = []
    for p in periods:
        if merged and not working_days(merged[-1][0], merged[-1][1]):
            merged[-1][1] = p[1]
        else:
            merged.append(p)
    if len(merged) > 1 and not working_days(merged[-1][0], merged[-1][1]):
        merged[-2][1] = merged[-1][1]
        merged.pop()
    out = []
    for i, (s, e) in enumerate(merged, 1):
        announce = e + timedelta(days=1)
        while announce.weekday() != 0:
            announce += timedelta(days=1)
        out.append({"week_no": i, "key": s.isoformat(), "start": s.isoformat(), "end": e.isoformat(),
                    "announce_on": announce.isoformat(),
                    "label": f"Week {i} · {s.strftime('%d %b')} – {e.strftime('%d %b %Y')}"})
    return out


def week_for(d: date, cfg: LeagueConfig) -> dict | None:
    for w in league_weeks(cfg):
        if w["start"] <= d.isoformat() <= w["end"]:
            return w
    return None


# --------------------------------------------------------------------------------------- leaderboards
def demo_leaderboard(cfg: LeagueConfig, bds: list[BDRef], demos: Iterable[DemoLike],
                     start: date | None = None, end: date | None = None, f2f_only: bool = False) -> list[dict]:
    rows = {b.id: {"bd_id": b.id, "bd_name": b.name, "total": 0, "f2f": 0, "virtual": 0, "untyped": 0}
            for b in bds}
    for d in live(demos):
        if d.bd_id not in rows or not counts_for_league(d, cfg):
            continue
        if start and d.demo_date < start or end and d.demo_date > end:
            continue
        if f2f_only and not counts_for_f2f(d, cfg):
            continue
        r = rows[d.bd_id]
        r["total"] += 1
        if d.demo_type == "F2F":
            r["f2f"] += 1
        elif d.demo_type == "Virtual":
            r["virtual"] += 1
        else:
            r["untyped"] += 1
    return competition_rank(list(rows.values()), "total")


def leaders(ranked: list[dict], key: str = "total") -> list[dict]:
    if not ranked or float(ranked[0][key]) <= 0:
        return []
    top = float(ranked[0][key])
    return [r for r in ranked if float(r[key]) == top]


def overall_leaderboard(cfg: LeagueConfig, bds: list[BDRef], demos: list[DemoLike], daily: dict,
                        revenue: dict, now: datetime | None = None) -> list[dict]:
    """Official full-league standings (F2F + Virtual), with movement vs. end of the previous day."""
    today = now_local(cfg, now).date()
    board = demo_leaderboard(cfg, bds, demos)
    prev = {r["bd_id"]: r["rank"] for r in demo_leaderboard(cfg, bds, demos, end=today - timedelta(days=1))}
    scheduled = defaultdict(int)
    for d in live(demos):
        if d.status == "Scheduled":
            scheduled[d.bd_id] += 1
    rev = {r["bd_id"]: r for r in revenue["per_bd"]}
    worst = max((r["rank"] for r in board), default=None)
    for r in board:
        dbd = daily["per_bd"].get(r["bd_id"], {})
        r["previous_rank"] = prev.get(r["bd_id"])
        r["movement"] = (prev.get(r["bd_id"]) or r["rank"]) - r["rank"]  # +ve = moved up
        r["achievement_rate"] = dbd.get("achievement_rate")
        r["current_pending"] = dbd.get("current_pending", 0)
        r["revenue_inr"] = rev.get(r["bd_id"], {}).get("total_inr", 0.0)
        r["scheduled"] = scheduled[r["bd_id"]]
        r["is_leader"] = r["rank"] == 1 and r["total"] > 0
        r["is_lowest"] = worst is not None and r["rank"] == worst and worst > 1
    return board


# --------------------------------------------------------------------------------------- F2F challenge
def f2f_challenge(cfg: LeagueConfig, bds: list[BDRef], demos: list[DemoLike]) -> dict:
    achieved, per_bd, per_region = 0, defaultdict(int), defaultdict(int)
    sched_total, sched_regions, sched_bd = 0, defaultdict(int), defaultdict(int)
    completed_unqualified = 0
    f2f_outside_regions = 0
    for d in live(demos):
        if d.demo_type != "F2F":
            continue
        region = region_of(d.country, cfg)
        if counts_for_f2f(d, cfg):
            achieved += 1
            per_bd[d.bd_id] += 1
            per_region[region] += 1
        elif counts_for_league(d, cfg) and region is None:
            f2f_outside_regions += 1
        elif d.status == "Completed" and d.qualified != "Yes" and in_league(d.demo_date, cfg) and region:
            completed_unqualified += 1
        if d.status == "Scheduled":
            sched_total += 1
            sched_bd[d.bd_id] += 1
            sched_regions[region or "Other"] += 1
    target = cfg.f2f_target
    board = competition_rank([{"bd_id": b.id, "bd_name": b.name, "f2f": per_bd[b.id],
                               "scheduled_f2f": sched_bd[b.id]} for b in bds], "f2f")
    return {
        "target": target,
        "achieved": achieved,
        "remaining": max(0, target - achieved),
        "percent": round(min(100.0, 100.0 * achieved / target), 1) if target else 0.0,
        "milestones": [{"value": m, "reached": achieved >= m} for m in sorted(cfg.f2f_milestones)],
        "per_region": {r: per_region.get(r, 0) for r in cfg.f2f_regions},
        "leaderboard": board,
        "leaders": leaders(board, "f2f"),
        "scheduled_pipeline": {"total": sched_total, "by_region": dict(sched_regions)},
        "completed_unqualified_in_regions": completed_unqualified,
        "qualified_f2f_outside_regions": f2f_outside_regions,
        "windows": cfg.raw.get("f2f_windows", []),
    }


# --------------------------------------------------------------------------------------- revenue
def revenue_eligibility_date(r) -> date | None:
    if r.contract_status == "Signed":
        return r.contract_signed_date
    if r.contract_status == "Amount Credited":
        return r.amount_credited_date
    return None


def find_rate(currency: str, on: date | None, rates: list) -> object | None:
    cands = [x for x in rates if x.currency.upper() == currency.upper() and (on is None or x.effective_date <= on)]
    return max(cands, key=lambda x: x.effective_date) if cands else None


def evaluate_revenue(r, cfg: LeagueConfig, rates: list) -> dict:
    """Per-record eligibility and INR conversion. Each record = one opportunity, counted once."""
    out = {"eligible": False, "reason": None, "inr_value": None, "rate_used": None, "rate_date": None,
           "rate_basis": None, "pending_conversion": False, "eligibility_date": None}
    if getattr(r, "deleted_at", None) is not None:
        out["reason"] = "Deleted"
        return out
    if r.contract_status not in ("Signed", "Amount Credited"):
        out["reason"] = "Contract status not confirmed"
        return out
    ed = revenue_eligibility_date(r)
    out["eligibility_date"] = ed.isoformat() if ed else None
    if ed is None:
        out["reason"] = ("Missing Contract Signed Date" if r.contract_status == "Signed"
                         else "Missing Amount Credited Date")
        return out
    if not in_league(ed, cfg):
        out["reason"] = "Date outside league period"
        return out
    value = Decimal(str(r.contract_value or 0))
    if r.currency.upper() == "INR":
        out.update(inr_value=float(value), rate_used=1.0, rate_date=ed.isoformat(), rate_basis="INR")
    elif getattr(r, "fx_rate_override", None):
        out.update(inr_value=float(value * Decimal(str(r.fx_rate_override))),
                   rate_used=float(r.fx_rate_override),
                   rate_date=(r.fx_rate_override_date or ed).isoformat(), rate_basis="Record-specific rate")
    else:
        rate = find_rate(r.currency, ed, rates)
        if rate is None:
            out.update(pending_conversion=True,
                       reason=f"Pending conversion: no {r.currency} rate effective on/before {ed.isoformat()}")
            return out
        out.update(inr_value=float(value * Decimal(str(rate.rate_to_inr))), rate_used=float(rate.rate_to_inr),
                   rate_date=rate.effective_date.isoformat(), rate_basis=rate.basis or "Configured rate")
    out["inr_value"] = round(out["inr_value"], 2)
    out["eligible"] = True
    return out


def revenue_summary(cfg: LeagueConfig, bds: list[BDRef], revenues: list, rates: list,
                    prize_amount: float = 100000) -> dict:
    per_bd = {b.id: {"bd_id": b.id, "bd_name": b.name, "total_inr": 0.0, "signed_inr": 0.0,
                     "credited_inr": 0.0, "records": 0, "pending_conversion": 0} for b in bds}
    by_country, by_domain, by_status, by_currency = (defaultdict(float) for _ in range(4))
    evaluated = {}
    total = 0.0
    for r in revenues:
        ev = evaluate_revenue(r, cfg, rates)
        evaluated[r.id] = ev
        row = per_bd.get(r.bd_id)
        if row is None or getattr(r, "deleted_at", None) is not None:
            continue
        if ev["pending_conversion"]:
            row["pending_conversion"] += 1
        if not ev["eligible"]:
            continue
        v = ev["inr_value"]
        total += v
        row["total_inr"] += v
        row["records"] += 1
        row["signed_inr" if r.contract_status == "Signed" else "credited_inr"] += v
        by_country[(r.country or "Unspecified").strip()] += v
        by_domain[(r.domain or "Unspecified").strip()] += v
        by_status[r.contract_status] += v
        by_currency[r.currency.upper()] += v
    board = competition_rank(list(per_bd.values()), "total_inr")
    top = board[0]["total_inr"] if board else 0.0
    for b in board:
        b["total_inr"] = round(b["total_inr"], 2)
        b["award_eligible"] = b["total_inr"] >= cfg.revenue_threshold_inr
        b["gap_to_leader"] = round(top - b["total_inr"], 2)
        b["gap_to_threshold"] = round(max(0.0, cfg.revenue_threshold_inr - b["total_inr"]), 2)
    eligible = [b for b in board if b["award_eligible"]]
    champions = []
    if eligible:
        best = max(b["total_inr"] for b in eligible)
        champs = [b for b in eligible if b["total_inr"] == best]
        share = round(prize_amount / len(champs), 2)
        champions = [{"bd_id": c["bd_id"], "bd_name": c["bd_name"], "total_inr": c["total_inr"],
                      "prize_share_inr": share} for c in champs]
    return {
        "total_inr": round(total, 2),
        "threshold_inr": cfg.revenue_threshold_inr,
        "per_bd": board,
        "champions": champions,
        "tie": len(champions) > 1,
        "by_country": dict(sorted(by_country.items(), key=lambda x: -x[1])),
        "by_domain": dict(sorted(by_domain.items(), key=lambda x: -x[1])),
        "by_status": dict(by_status),
        "by_currency": dict(by_currency),
        "pending_conversion_count": sum(1 for e in evaluated.values() if e["pending_conversion"]),
        "evaluated": evaluated,
    }


# --------------------------------------------------------------------------------------- awards
def weekly_results(cfg: LeagueConfig, bds: list[BDRef], demos: list[DemoLike], finalized: dict,
                   now: datetime | None = None) -> list[dict]:
    today = now_local(cfg, now).date()
    out = []
    for w in league_weeks(cfg):
        s, e = date.fromisoformat(w["start"]), date.fromisoformat(w["end"])
        board = demo_leaderboard(cfg, bds, demos, start=s, end=e)
        lead = leaders(board)
        fin = finalized.get(("weekly_demo", w["key"]))
        state = "upcoming" if s > today else ("in_progress" if e >= today else "awaiting_finalization")
        if fin:
            state = "finalized"
        out.append({**w, "state": state, "standings": board,
                    "leaders": [{"bd_id": x["bd_id"], "bd_name": x["bd_name"], "total": x["total"]} for x in lead],
                    "tie": len(lead) > 1, "finalized": fin})
    return out


def award_overview(cfg: LeagueConfig, bds: list[BDRef], demos: list[DemoLike], revenue: dict, f2f: dict,
                   weeks: list[dict], finalized: dict, now: datetime | None = None) -> dict:
    today = now_local(cfg, now).date()
    awards_cfg = cfg.raw.get("awards", {})
    current = next((w for w in weeks if w["state"] == "in_progress"), None)
    previous = [w for w in weeks if w["state"] in ("awaiting_finalization", "finalized")]
    previous = previous[-1] if previous else None
    overall = demo_leaderboard(cfg, bds, demos)
    ov_leaders = leaders(overall)
    league_done = today > cfg.league_end
    return {
        "weekly_demo": {
            **awards_cfg.get("weekly_demo", {}),
            "current_week": current and {k: current[k] for k in ("key", "label", "start", "end", "announce_on")},
            "provisional_leaders": current["leaders"] if current else [],
            "current_tie": bool(current and current["tie"]),
            "previous_week": previous and {k: previous[k] for k in
                                           ("key", "label", "start", "end", "announce_on", "state", "leaders",
                                            "tie", "finalized")},
        },
        "league_champion": {
            **awards_cfg.get("league_champion", {}),
            "leaders": [{"bd_id": x["bd_id"], "bd_name": x["bd_name"], "total": x["total"]} for x in ov_leaders],
            "tie": len(ov_leaders) > 1,
            "state": "finalized" if finalized.get(("league_champion", "league")) else (
                "awaiting_finalization" if league_done else "provisional"),
            "finalized": finalized.get(("league_champion", "league")),
        },
        "revenue": {
            **awards_cfg.get("revenue", {}),
            "champions": revenue["champions"],
            "tie": revenue["tie"],
            "threshold_inr": revenue["threshold_inr"],
            "eligible_count": sum(1 for b in revenue["per_bd"] if b["award_eligible"]),
            "state": "finalized" if finalized.get(("revenue", "league")) else (
                "awaiting_finalization" if league_done else "provisional"),
            "finalized": finalized.get(("revenue", "league")),
        },
        "f2f": {
            **awards_cfg.get("f2f", {}),
            "leaders": [{"bd_id": x["bd_id"], "bd_name": x["bd_name"], "f2f": x["f2f"]} for x in f2f["leaders"]],
            "tie": len(f2f["leaders"]) > 1,
            "tie_note": "Tie flagged for administrator review - no automatic split or tie-breaker."
            if len(f2f["leaders"]) > 1 else None,
            "state": "finalized" if finalized.get(("f2f", "league")) else (
                "awaiting_finalization" if league_done else "provisional"),
            "finalized": finalized.get(("f2f", "league")),
        },
    }


BADGE_DEMO_MILESTONES = [10, 25, 50]
STREAK_BADGES = [3, 5, 10]


def badges_for(total: int, f2f: int, best_streak: int) -> list[dict]:
    out = [{"key": f"demos_{m}", "label": f"{m} Qualified Demos", "earned": total >= m} for m in BADGE_DEMO_MILESTONES]
    out += [{"key": f"streak_{s}", "label": f"{s}-Day Target Streak", "earned": best_streak >= s} for s in STREAK_BADGES]
    out += [{"key": f"f2f_{m}", "label": f"{m} F2F Demo{'s' if m > 1 else ''}", "earned": f2f >= m} for m in (1, 5, 10)]
    return out


def time_remaining(demo_date: date | None, demo_time: time | None, tz_label: str | None,
                   cfg: LeagueConfig, now: datetime | None = None) -> dict:
    """Dynamic Time Remaining (replaces the workbook's NOW() formula)."""
    if demo_date is None:
        return {"seconds": None, "label": "", "demo_at": None}
    tz = ZoneInfo(TZ_ALIASES.get((tz_label or "").strip().upper(), cfg.timezone))
    at = datetime.combine(demo_date, demo_time or time(0, 0), tzinfo=tz)
    secs = int((at - now_local(cfg, now)).total_seconds())
    if secs <= 0:
        label = "0 Hrs 0 Min"
    else:
        label = f"{secs // 3600} Hrs {(secs % 3600) // 60} Min"
    return {"seconds": max(0, secs), "label": label, "demo_at": at.isoformat()}


TZ_ALIASES = {
    "IST": "Asia/Kolkata", "SGT": "Asia/Singapore", "MYT": "Asia/Kuala_Lumpur", "GST": "Asia/Dubai",
    "AST": "Asia/Riyadh", "AEST": "Australia/Sydney", "AEDT": "Australia/Sydney", "AWST": "Australia/Perth",
    "NZST": "Pacific/Auckland", "NZDT": "Pacific/Auckland", "GMT": "Europe/London", "BST": "Europe/London",
    "UTC": "UTC", "CET": "Europe/Paris", "CEST": "Europe/Paris", "EST": "America/New_York",
    "EDT": "America/New_York", "CST": "America/Chicago", "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles", "ICT": "Asia/Bangkok", "WIB": "Asia/Jakarta", "PHT": "Asia/Manila",
}
