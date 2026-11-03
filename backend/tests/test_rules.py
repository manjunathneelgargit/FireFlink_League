"""Section 22 acceptance tests for the business-logic layer (pure functions)."""
from datetime import date, datetime, time
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest

from app.config import DEFAULTS, to_config
from app.services import league as L

IST = ZoneInfo("Asia/Kolkata")
CFG = to_config(dict(DEFAULTS))
A, B = L.BDRef(1, "Alpha"), L.BDRef(2, "Bravo")
_id = iter(range(1, 10_000))


def demo(bd=1, d=date(2026, 11, 2), status="Completed", q="Yes", typ="Virtual", country="India", completed=None):
    return NS(id=str(next(_id)), bd_id=bd, customer_name="C", country=country, domain="IT", demo_type=typ,
              demo_date=d, status=status, qualified=q,
              demo_completed=(status == "Completed") if completed is None else completed, deleted_at=None)


def at(y, m, d, hh=10, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


# ----------------------------------------------------------------------------- demo counting
@pytest.mark.parametrize("status,q,counts", [
    ("Completed", "Yes", True), ("Completed", "No", False), ("Completed", None, False),
    ("Scheduled", "No", False), ("No Show", "No", False), ("Rescheduled", "No", False),
    ("Cancelled", "No", False), ("Awaiting Demo Date", None, False), ("Pipeline", None, False),
])
def test_demo_counting_rules(status, q, counts):
    assert L.counts_for_league(demo(status=status, q=q), CFG) is counts


def test_poc_does_not_add_and_does_not_erase():
    d = demo()
    assert L.counts_for_league(d, CFG)
    d.status = "POC Initiated"  # opportunity moves to POC; demo_completed stays True (sticky)
    assert L.counts_for_league(d, CFG)
    board = L.demo_leaderboard(CFG, [A], [d])
    assert board[0]["total"] == 1  # still exactly one, no extra count
    never_completed = demo(status="POC Initiated", q="No", completed=False)
    assert not L.counts_for_league(never_completed, CFG)


def test_status_update_counts_once():
    d = demo(status="Scheduled", q=None)
    assert L.demo_leaderboard(CFG, [A], [d])[0]["total"] == 0
    d.status, d.qualified, d.demo_completed = "Completed", "Yes", True
    assert L.demo_leaderboard(CFG, [A], [d])[0]["total"] == 1
    d.demo_type = "F2F"  # editing an already-completed record does not duplicate
    assert L.demo_leaderboard(CFG, [A], [d])[0]["total"] == 1


def test_outside_league_not_counted():
    assert not L.counts_for_league(demo(d=date(2026, 10, 30)), CFG)
    assert not L.counts_for_league(demo(d=date(2026, 12, 21)), CFG)
    assert L.counts_for_league(demo(d=date(2026, 12, 19)), CFG)


# ----------------------------------------------------------------------------- demo type
def test_both_types_count_overall_only_f2f_counts_challenge():
    ds = [demo(typ="F2F", country="Malaysia"), demo(typ="Virtual", country="Singapore"),
          demo(typ="F2F", country="Dubai", bd=2)]
    board = {r["bd_name"]: r for r in L.demo_leaderboard(CFG, [A, B], ds)}
    assert board["Alpha"]["total"] == 2 and board["Alpha"]["f2f"] == 1 and board["Alpha"]["virtual"] == 1
    ch = L.f2f_challenge(CFG, [A, B], ds)
    assert ch["achieved"] == 2  # Virtual never increases F2F progress


def test_scheduled_f2f_separate_from_completed():
    ds = [demo(typ="F2F", status="Scheduled", q=None, country="Singapore", d=date(2026, 11, 20)),
          demo(typ="F2F", country="Singapore")]
    ch = L.f2f_challenge(CFG, [A], ds)
    assert ch["achieved"] == 1 and ch["scheduled_pipeline"]["total"] == 1


# ----------------------------------------------------------------------------- F2F challenge
def test_f2f_challenge_rules():
    assert L.f2f_challenge(CFG, [A], [])["achieved"] == 0
    ds = [demo(typ="F2F", status="Scheduled", q=None, country="Malaysia"),
          demo(typ="F2F", q="No", country="Malaysia"),
          demo(typ="Virtual", country="Malaysia")]
    assert L.f2f_challenge(CFG, [A], ds)["achieved"] == 0
    ds.append(demo(typ="F2F", country="Malasia"))  # workbook spelling
    ch = L.f2f_challenge(CFG, [A], ds)
    assert ch["achieved"] == 1 and ch["remaining"] == 44 and ch["percent"] == pytest.approx(2.2)


def test_f2f_any_league_date_counts_and_regions():
    # Admin decision: an F2F demo in Malaysia on Nov 10 (outside the travel window) still counts.
    assert L.counts_for_f2f(demo(typ="F2F", country="Malaysia", d=date(2026, 11, 10)), CFG)
    for c in ("Dubai", "Abu Dhabi", "Aabu Dhabi", "Soudi", "Saudi Arabia", "Qatar", "Oman", "Bahrain", "Kuwait",
              "UAE", "Singapore, USA"):
        assert L.region_of(c, CFG) is not None, c
    for c in ("India", "Australia", "UK (London)", "Sweden", None, ""):
        assert L.region_of(c, CFG) is None, c
    assert not L.counts_for_f2f(demo(typ="F2F", country="India"), CFG)


def test_f2f_progress_not_fabricated():
    ds = [demo(typ="F2F", country="Singapore") for _ in range(3)]
    ch = L.f2f_challenge(CFG, [A], ds)
    assert ch["achieved"] == 3 and ch["remaining"] == 42
    assert not any(m["reached"] for m in ch["milestones"])


def test_f2f_tie_flagged():
    ds = [demo(typ="F2F", country="Singapore", bd=1), demo(typ="F2F", country="Kuwait", bd=2)]
    ch = L.f2f_challenge(CFG, [A, B], ds)
    assert len(ch["leaders"]) == 2


# ----------------------------------------------------------------------------- carry-forward
SPEC_WEEK = {date(2026, 11, 2): 0, date(2026, 11, 3): 1, date(2026, 11, 4): 3, date(2026, 11, 5): 1,
             date(2026, 11, 6): 0, date(2026, 11, 7): 2}


def _week_demos(spec):
    return [demo(d=d) for d, n in spec.items() for _ in range(n)]


def test_spec_carry_forward_example():
    res = L.compute_daily_targets(CFG, [A], _week_demos(SPEC_WEEK), set(), at(2026, 11, 9, 10))["per_bd"][1]
    days = {d["date"]: d for d in res["days"]}
    expected = [("2026-11-02", 1, 0, 1), ("2026-11-03", 2, 1, 1), ("2026-11-04", 2, 3, 0),
                ("2026-11-05", 1, 1, 0), ("2026-11-06", 1, 0, 1), ("2026-11-07", 2, 2, 0)]
    for ds, req, done, pend in expected:
        assert (days[ds]["required"], days[ds]["done"], days[ds]["pending_after"]) == (req, done, pend), ds
    assert "2026-11-08" not in days  # Sunday creates no target
    assert days["2026-11-09"]["required"] == 1
    # Official count = 7 actual demos, never inflated by missed targets
    assert L.demo_leaderboard(CFG, [A], _week_demos(SPEC_WEEK))[0]["total"] == 7
    assert res["targets_achieved"] == 3 and res["targets_missed"] == 3  # Mon, Tue, Fri missed


def test_pending_survives_sunday_and_saturday_has_target():
    spec = dict(SPEC_WEEK)
    spec[date(2026, 11, 7)] = 1  # Saturday short by one
    res = L.compute_daily_targets(CFG, [A], _week_demos(spec), set(), at(2026, 11, 9, 10))["per_bd"][1]
    days = {d["date"]: d for d in res["days"]}
    assert days["2026-11-07"]["required"] == 2 and days["2026-11-07"]["status"] == "Target Missed"
    assert days["2026-11-09"]["required"] == 2  # carried over Sunday


def test_carry_forward_is_independent_per_bd():
    ds = _week_demos(SPEC_WEEK) + [demo(bd=2, d=d) for d in SPEC_WEEK]
    res = L.compute_daily_targets(CFG, [A, B], ds, set(), at(2026, 11, 9, 10))["per_bd"]
    assert res[2]["targets_achieved"] == 6 and res[2]["current_pending"] == 0
    assert res[1]["targets_achieved"] == 3


def test_over_achievement_creates_no_future_target():
    ds = [demo(d=date(2026, 11, 2)) for _ in range(5)]
    res = L.compute_daily_targets(CFG, [A], ds, set(), at(2026, 11, 3, 10))["per_bd"][1]
    assert res["days"][0]["pending_after"] == 0
    assert res["today"]["required"] == 1  # no negative carry / credit banked


def test_in_progress_day_not_marked_missed_and_closure_finalises():
    now = at(2026, 11, 2, 15)
    res = L.compute_daily_targets(CFG, [A], [], set(), now)["per_bd"][1]
    assert res["today"]["status"] == "Target Pending Today" and not res["today"]["closed"]
    assert res["targets_missed"] == 0
    early = L.compute_daily_targets(CFG, [A], [], set(), at(2026, 11, 2, 8, 0))["per_bd"][1]
    assert early["today"]["status"] == "Not Started"
    closed = L.compute_daily_targets(CFG, [A], [], {date(2026, 11, 2)}, now)["per_bd"][1]
    assert closed["today"]["status"] == "Target Missed" and closed["current_pending"] == 1
    after_cutoff = L.compute_daily_targets(CFG, [A], [], set(), at(2026, 11, 2, 23, 59))["per_bd"][1]
    assert after_cutoff["today"]["status"] == "Target Missed"


def test_in_progress_and_carry_forward_pending_states():
    ds = [demo(d=date(2026, 11, 3))]
    res = L.compute_daily_targets(CFG, [A], ds, set(), at(2026, 11, 3, 12))["per_bd"][1]
    assert res["today"]["required"] == 2 and res["today"]["status"] == "In Progress"
    res2 = L.compute_daily_targets(CFG, [A], [], set(), at(2026, 11, 3, 12))["per_bd"][1]
    assert res2["today"]["status"] == "Carry-Forward Pending"


def test_final_league_day_has_no_next_target():
    res = L.compute_daily_targets(CFG, [A], [], set(), at(2026, 12, 21, 10))
    a = res["per_bd"][1]
    assert res["league_over"] and a["next_required"] is None and a["next_target_date"] is None
    assert a["targets_assigned"] == len(L.working_days(date(2026, 11, 1), date(2026, 12, 20))) == 42
    assert a["outstanding_carry_forward"] == a["current_pending"]
    sat = L.compute_daily_targets(CFG, [A], [], set(), at(2026, 12, 19, 23, 59))["per_bd"][1]
    assert sat["next_required"] is None  # 20 Dec is Sunday - no imaginary next league day


def test_sunday_shows_next_working_day_target():
    res = L.compute_daily_targets(CFG, [A], [], set(), at(2026, 11, 8, 12))
    assert not res["is_working_day"]
    assert res["per_bd"][1]["next_target_date"] == "2026-11-09"
    assert res["per_bd"][1]["next_required"] == 7  # 6 missed days + today's 1


# ----------------------------------------------------------------------------- weeks / awards
def test_weeks_have_exact_ranges_and_cover_league():
    ws = L.league_weeks(CFG)
    assert ws[0]["start"] == "2026-11-01" and ws[0]["end"] == "2026-11-08"  # Sunday 1 Nov merged
    assert ws[-1]["end"] == "2026-12-20" and len(ws) == 7
    assert ws[0]["announce_on"] == "2026-11-09"


def test_weekly_uses_both_types():
    ds = [demo(typ="F2F", country="Singapore", d=date(2026, 11, 3)), demo(typ="Virtual", d=date(2026, 11, 4)),
          demo(bd=2, d=date(2026, 11, 4))]
    wk = L.weekly_results(CFG, [A, B], ds, {}, at(2026, 11, 10))[0]
    assert wk["leaders"][0]["bd_name"] == "Alpha" and wk["leaders"][0]["total"] == 2
    assert wk["state"] == "awaiting_finalization"


# ----------------------------------------------------------------------------- revenue
def rev(bd=1, status="Signed", value=1_500_000, cur="INR", signed=date(2026, 11, 5), credited=None, rid=None):
    return NS(id=rid or str(next(_id)), bd_id=bd, contract_status=status, currency=cur, contract_value=value,
              contract_signed_date=signed, amount_credited_date=credited, country="India", domain="IT",
              fx_rate_override=None, fx_rate_override_date=None, deleted_at=None)


def test_revenue_dates_and_example_total():
    rs = [rev(value=1_500_000), rev(status="Amount Credited", value=2_000_000, signed=date(2026, 10, 20),
                                    credited=date(2026, 11, 10)), rev(value=800_000)]
    s = L.revenue_summary(CFG, [A], rs, [])
    assert s["per_bd"][0]["total_inr"] == 4_300_000  # ₹43 lakh
    # Signed uses signed date; credited uses credited date
    assert not L.evaluate_revenue(rev(signed=date(2026, 10, 31)), CFG, [])["eligible"]
    assert not L.evaluate_revenue(rev(status="Amount Credited", signed=date(2026, 11, 5),
                                      credited=date(2026, 12, 21)), CFG, [])["eligible"]


def test_signed_to_credited_not_double_counted():
    r = rev(value=1_000_000)
    assert L.revenue_summary(CFG, [A], [r], [])["total_inr"] == 1_000_000
    r.contract_status, r.amount_credited_date = "Amount Credited", date(2026, 11, 20)
    assert L.revenue_summary(CFG, [A], [r], [])["total_inr"] == 1_000_000


def test_threshold_and_visibility():
    s = L.revenue_summary(CFG, [A, B], [rev(value=800_000), rev(bd=2, value=1_000_000)], [])
    rows = {r["bd_name"]: r for r in s["per_bd"]}
    assert s["total_inr"] == 1_800_000  # below-threshold revenue still visible in totals
    assert not rows["Alpha"]["award_eligible"] and rows["Bravo"]["award_eligible"]
    assert [c["bd_name"] for c in s["champions"]] == ["Bravo"]
    assert rows["Alpha"]["gap_to_leader"] == 200_000


def test_revenue_tie_splits_prize():
    s = L.revenue_summary(CFG, [A, B], [rev(value=1_200_000), rev(bd=2, value=1_200_000)], [], 100000)
    assert s["tie"] and all(c["prize_share_inr"] == 50000 for c in s["champions"])


def test_currency_needs_configured_rate():
    r = rev(cur="USD", value=20_000)
    ev = L.evaluate_revenue(r, CFG, [])
    assert not ev["eligible"] and ev["pending_conversion"]
    rate = NS(currency="USD", rate_to_inr=88.5, effective_date=date(2026, 11, 1), basis="RBI ref")
    ev = L.evaluate_revenue(r, CFG, [rate])
    assert ev["eligible"] and ev["inr_value"] == 1_770_000 and ev["rate_date"] == "2026-11-01"
    later = NS(currency="USD", rate_to_inr=90, effective_date=date(2026, 11, 6), basis="x")
    assert not L.evaluate_revenue(r, CFG, [later])["eligible"]  # no rate effective on/before signing
    s = L.revenue_summary(CFG, [A], [r], [])
    assert s["per_bd"][0]["pending_conversion"] == 1 and s["champions"] == []


# ----------------------------------------------------------------------------- leaderboard
def test_competition_rank_and_lowest():
    ds = [demo(bd=1), demo(bd=1), demo(bd=2)]
    C = L.BDRef(3, "Charlie")
    daily = L.compute_daily_targets(CFG, [A, B, C], ds, set(), at(2026, 11, 3))
    board = L.overall_leaderboard(CFG, [A, B, C], ds, daily, L.revenue_summary(CFG, [A, B, C], [], []),
                                  at(2026, 11, 3))
    ranks = {r["bd_name"]: r for r in board}
    assert ranks["Alpha"]["rank"] == 1 and ranks["Alpha"]["is_leader"]
    assert ranks["Charlie"]["is_lowest"] and ranks["Charlie"]["rank"] == 3
