from __future__ import annotations

from ..config import LeagueConfig
from ..models import DemoRecord, RevenueRecord
from ..services import league as L


def demo_out(d: DemoRecord, cfg: LeagueConfig, now=None) -> dict:
    tr = L.time_remaining(d.demo_date, d.demo_time, d.time_zone, cfg, now)
    return {
        "id": d.id, "sl_no": d.sl_no, "bd_id": d.bd_id, "bd_name": d.bd.name if d.bd else None,
        "customer_name": d.customer_name, "domain": d.domain, "country": d.country, "demo_type": d.demo_type,
        "demo_on": d.demo_on, "demo_date": d.demo_date.isoformat() if d.demo_date else None,
        "demo_time": d.demo_time.strftime("%H:%M") if d.demo_time else None, "time_zone": d.time_zone,
        "time_remaining": tr["label"], "time_remaining_seconds": tr["seconds"], "demo_at": tr["demo_at"],
        "status": d.status, "qualified": d.qualified,
        "counts": L.counts_for_league(d, cfg), "counts_f2f": L.counts_for_f2f(d, cfg),
        "achieved": L.is_achieved_demo(d), "in_league": L.in_league(d.demo_date, cfg),
        "region": L.region_of(d.country, cfg),
        "poc_started_on": d.poc_started_on.isoformat() if d.poc_started_on else None,
        "poc_status_updated_at": (d.poc_status_updated_at.isoformat() + "Z") if d.poc_status_updated_at else None,
        "poc_remarks": d.poc_remarks, "source": d.source,
        "created_at": d.created_at.isoformat() + "Z", "updated_at": d.updated_at.isoformat() + "Z",
        "deleted_at": (d.deleted_at.isoformat() + "Z") if d.deleted_at else None,
    }


def revenue_out(r: RevenueRecord, ev: dict) -> dict:
    iso = lambda x: x.isoformat() if x else None  # noqa: E731
    return {
        "id": r.id, "sl_no": r.sl_no, "bd_id": r.bd_id, "bd_name": r.bd.name if r.bd else None,
        "customer_name": r.customer_name, "country": r.country, "domain": r.domain,
        "opportunity_name": r.opportunity_name, "contract_status": r.contract_status, "currency": r.currency,
        "contract_value": float(r.contract_value), "contract_signed_date": iso(r.contract_signed_date),
        "amount_credited_date": iso(r.amount_credited_date), "customer_onboarding_date": iso(r.customer_onboarding_date),
        "remarks": r.remarks, "fx_rate_override": float(r.fx_rate_override) if r.fx_rate_override else None,
        "fx_rate_override_date": iso(r.fx_rate_override_date), "evaluation": ev, "source": r.source,
        "created_at": r.created_at.isoformat() + "Z", "updated_at": r.updated_at.isoformat() + "Z",
        "deleted_at": (r.deleted_at.isoformat() + "Z") if r.deleted_at else None,
    }
