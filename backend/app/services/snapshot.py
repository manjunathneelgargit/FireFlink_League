"""Builds the OFFICIAL league snapshot from the database. It always uses complete league data;
report filters never pass through here."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..config import LeagueConfig, load_config
from ..models import AwardFinalization, BDMember, DayClosure, DemoRecord, ExchangeRate, RevenueRecord
from . import league as L


def bd_refs(db: Session, include_inactive: bool = False) -> list[L.BDRef]:
    q = db.query(BDMember)
    if not include_inactive:
        q = q.filter(BDMember.active.is_(True))
    return [L.BDRef(b.id, b.name) for b in q.order_by(BDMember.display_order, BDMember.name).all()]


def finalized_map(db: Session) -> dict:
    return {(f.award_key, f.period_key): {"id": f.id, "result": f.result, "notes": f.notes,
                                         "finalized_at": f.finalized_at.isoformat() + "Z",
                                         "finalized_by": f.finalized_by}
            for f in db.query(AwardFinalization).all()}


def load_inputs(db: Session):
    cfg = load_config(db)
    bds = bd_refs(db)
    demos = db.query(DemoRecord).filter(DemoRecord.deleted_at.is_(None)).all()
    revenues = db.query(RevenueRecord).filter(RevenueRecord.deleted_at.is_(None)).all()
    rates = db.query(ExchangeRate).all()
    closures = {c.day for c in db.query(DayClosure).all()}
    return cfg, bds, demos, revenues, rates, closures


def build(db: Session, now: datetime | None = None, cfg: LeagueConfig | None = None) -> dict:
    cfg_db, bds, demos, revenues, rates, closures = load_inputs(db)
    cfg = cfg or cfg_db
    prize = float((cfg.raw.get("awards", {}).get("revenue", {}) or {}).get("prize_amount_inr") or 100000)
    now_l = L.now_local(cfg, now)
    daily = L.compute_daily_targets(cfg, bds, demos, closures, now_l)
    revenue = L.revenue_summary(cfg, bds, revenues, rates, prize)
    overall = L.overall_leaderboard(cfg, bds, demos, daily, revenue, now_l)
    f2f = L.f2f_challenge(cfg, bds, demos)
    fin = finalized_map(db)
    weeks = L.weekly_results(cfg, bds, demos, fin, now_l, daily=daily, revenues=revenues,
                             rates=rates, prize_amount=prize)
    awards = L.award_overview(cfg, bds, demos, revenue, f2f, weeks, fin, now_l)

    per_bd = daily["per_bd"]
    assigned = sum(v["targets_assigned"] for v in per_bd.values())
    achieved = sum(v["targets_achieved"] for v in per_bd.values())
    on_target_today = sum(1 for v in per_bd.values() if v["today"] and v["today"]["status"] == "Target Achieved")
    league_live = [d for d in demos if L.in_league(d.demo_date, cfg)]
    kpis = {
        "qualified_completed": sum(r["total"] for r in overall),
        "qualified_f2f": sum(r["f2f"] for r in overall),
        "qualified_virtual": sum(r["virtual"] for r in overall),
        "scheduled": sum(1 for d in demos if d.status == "Scheduled"),
        "scheduled_f2f": sum(1 for d in demos if d.status == "Scheduled" and L.demo_kind(d, cfg) == "F2F"),
        "scheduled_virtual": sum(1 for d in demos if d.status == "Scheduled" and L.demo_kind(d, cfg) == "Virtual"),
        "completed_unqualified": sum(1 for d in league_live if L.is_completed_unqualified(d, cfg)),
        "targets_assigned": assigned,
        "targets_achieved": achieved,
        "targets_missed": sum(v["targets_missed"] for v in per_bd.values()),
        "target_achievement_rate": round(100 * achieved / assigned, 1) if assigned else None,
        "outstanding_carry_forward": sum(v["current_pending"] for v in per_bd.values()),
        "on_target_today": on_target_today,
        "f2f_progress": f2f["percent"],
        "total_revenue_inr": revenue["total_inr"],
        "bd_count": len(bds),
    }
    days_left = max(0, (cfg.league_end - now_l.date()).days)
    league = {
        "name": cfg.league_name,
        "start": cfg.league_start.isoformat(),
        "end": cfg.league_end.isoformat(),
        "end_at": datetime.combine(cfg.league_end, cfg.day_cutoff_time, tzinfo=now_l.tzinfo).isoformat(),
        "now": now_l.isoformat(),
        "days_left": days_left,
        "working_days_total": len(L.working_days(cfg.league_start, cfg.league_end)),
        "working_days_left": len([d for d in L.working_days(cfg.league_start, cfg.league_end) if d >= now_l.date()]),
        "phase": "before" if now_l.date() < cfg.league_start else ("after" if now_l.date() > cfg.league_end else "live"),
        "f2f_target": cfg.f2f_target,
        "timezone": cfg.timezone,
        "cutoff": cfg.day_cutoff_time.strftime("%H:%M"),
        "office_login": cfg.office_login_time.strftime("%H:%M"),
        "standup": cfg.raw.get("standup_time"),
        "motivational_messages": cfg.raw.get("motivational_messages", []),
        "arena_refresh_seconds": cfg.raw.get("arena_refresh_seconds", 30),
        "require_qualified": cfg.require_qualified,
        "f2f_from_location": cfg.f2f_from_location,
    }
    rev_public = {k: v for k, v in revenue.items() if k != "evaluated"}
    return {"league": league, "kpis": kpis, "daily": daily, "overall": overall, "f2f": f2f,
            "revenue": rev_public, "weeks": weeks, "awards": awards}


def ranks_signature(db: Session) -> dict:
    """Small state used to emit 'moved up / new leader / revenue champion' activity events."""
    snap = build(db)
    return {
        "ranks": {r["bd_id"]: r["rank"] for r in snap["overall"]},
        "leaders": sorted(r["bd_id"] for r in snap["overall"] if r["is_leader"]),
        "rev_champs": sorted(c["bd_id"] for c in snap["revenue"]["champions"]),
        "f2f_achieved": snap["f2f"]["achieved"],
        "names": {r["bd_id"]: r["bd_name"] for r in snap["overall"]},
        "milestones": [m["value"] for m in snap["f2f"]["milestones"] if m["reached"]],
    }
