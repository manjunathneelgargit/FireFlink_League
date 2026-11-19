"""Multi-team: isolation, roles, per-team settings / arena links, simpler sheet format, legacy upgrade."""
import io
import shutil
import sqlite3
from datetime import date
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.auth import hash_password
from app.main import app
from app.models import AdminUser, BDMember, DemoRecord, Team
from app.services import gsheet as G
from app.tenancy import TeamScopeError, team_session

H = {"X-Requested-With": "ffl"}
PW = "correct-horse-1"


def _login(username):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": username, "password": PW}).status_code == 200
    return c


@pytest.fixture()
def two_teams(fresh_db):
    """Team 1 = APAC (default), team 2 = EMEA created by the super admin; one team admin each."""
    with team_session() as db:
        db.add(AdminUser(username="root", password_hash=hash_password(PW), role="super_admin"))
        db.commit()
    su = _login("root")
    emea = su.post("/api/teams", json={"name": "EMEA"}, headers=H).json()
    assert emea["slug"] == "emea"
    for name, tid in (("apac.admin", 1), ("emea.admin", emea["id"])):
        r = su.post("/api/users", json={"username": name, "password": PW, "role": "team_admin", "team_id": tid},
                    headers=H)
        assert r.status_code == 200, r.text
    return su, emea["id"]


def _as_team(c, tid):
    return {**H, "X-Team-Id": str(tid)}


def test_team_data_is_isolated(two_teams):
    su, emea = two_teams
    apac_admin, emea_admin = _login("apac.admin"), _login("emea.admin")
    a = apac_admin.post("/api/bds", json={"name": "Alpha"}, headers=H).json()["id"]
    apac_admin.post("/api/demos", json={"bd_id": a, "customer_name": "Acme", "status": "Completed",
                                         "qualified": "Yes", "demo_date": "2026-11-02"}, headers=H)
    # Same BD name is allowed in another team.
    e = emea_admin.post("/api/bds", json={"name": "Alpha"}, headers=H).json()["id"]
    assert e != a

    assert [d["customer_name"] for d in apac_admin.get("/api/demos").json()] == ["Acme"]
    assert emea_admin.get("/api/demos").json() == []
    assert emea_admin.get("/api/dashboard").json()["kpis"]["qualified_completed"] == 0
    assert [b["id"] for b in emea_admin.get("/api/bds").json()] == [e]
    # A team admin cannot reach another team's records, even by id or by sending the team header.
    demo_id = apac_admin.get("/api/demos").json()[0]["id"]
    assert emea_admin.delete(f"/api/demos/{demo_id}", headers=H).status_code == 404
    assert emea_admin.get(f"/api/bd/{a}").status_code == 404
    assert emea_admin.get("/api/demos", headers={"X-Team-Id": "1"}).json() == []
    # Cannot attach a demo to another team's BD.
    r = emea_admin.post("/api/demos", json={"bd_id": a, "customer_name": "X", "status": "Scheduled"}, headers=H)
    assert r.status_code == 422
    # Super admin switches teams with the header.
    assert len(su.get("/api/demos", headers=_as_team(su, 1)).json()) == 1
    assert su.get("/api/demos", headers=_as_team(su, emea)).json() == []


def test_roles_and_me(two_teams):
    su, emea = two_teams
    me = su.get("/api/auth/me", headers={"X-Team-Id": str(emea)}).json()
    assert me["is_super"] and me["team"]["id"] == emea and {t["name"] for t in me["teams"]} == {"APAC", "EMEA"}
    ta = _login("emea.admin")
    me = ta.get("/api/auth/me").json()
    assert not me["is_super"] and [t["id"] for t in me["teams"]] == [emea]
    for path in ("/api/teams", "/api/users"):
        assert ta.get(path).status_code == 403
    assert ta.post("/api/teams", json={"name": "Hack"}, headers=H).status_code == 403
    # Deactivated team: its admin is locked out.
    su.put(f"/api/teams/{emea}", json={"active": False}, headers=H)
    assert ta.get("/api/dashboard").status_code == 403
    assert TestClient(app).post("/api/auth/login", json={"username": "emea.admin", "password": PW}).status_code == 403
    # The last super admin cannot be removed.
    root_id = next(u["id"] for u in su.get("/api/users").json() if u["username"] == "root")
    assert su.delete(f"/api/users/{root_id}", headers=H).status_code == 422


def test_settings_and_arena_links_are_per_team(two_teams):
    su, emea = two_teams
    su.put("/api/settings", json={"league_start": "2027-01-04", "league_end": "2027-02-27"}, headers=_as_team(su, emea))
    assert su.get("/api/settings", headers=_as_team(su, 1)).json()["league_start"] == "2026-11-01"
    s = su.get("/api/settings", headers=_as_team(su, emea)).json()
    assert s["league_start"] == "2027-01-04"
    assert s["count_requires_qualified"] is False and s["f2f_from_location"] is True  # new-team defaults
    assert su.get("/api/settings", headers=_as_team(su, 1)).json()["count_requires_qualified"] is True

    tok = su.post("/api/settings/arena-link", headers=_as_team(su, emea)).json()["token"]
    arena = TestClient(app).get(f"/api/arena?token={tok}").json()
    assert arena["league"]["start"] == "2027-01-04"


def _basic_sheet(rows):
    """The simpler demo format other teams use (no Country / Demo Type / Qualified / time columns)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Demos_and_Pipelines"
    ws.append(["Sl No", "BD", "Customer Name", "Domain", "City", "Demo On", "Demo Date", "Status"])
    for r in rows:
        ws.append(r)
    rv = wb.create_sheet("League_Revenue")
    rv.append(["Sl No", "BD", "Customer Name", "Country", "Domain", "Opportunity Name", "Contract Status",
               "Currency", "Contract Value", "Contract Signed Date", "Amount Credited Date",
               "Customer Onboarding Date", "Remarks"])
    rv.append([1, "Zed", "Gulf Bank", "UAE", "BFSI", "FireFlink License", "Signed", "INR", 1200000,
               date(2026, 11, 3), None, None, None])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_basic_sheet_format_counts_completed_and_infers_f2f(two_teams):
    su, emea = two_teams
    with team_session(emea) as db:
        db.add(BDMember(name="Zed"))
        db.commit()
    from app.countries import COUNTRIES
    su.put("/api/settings", json={"f2f_regions": {c: COUNTRIES[c] for c in
                                                  ("United Arab Emirates", "Malaysia", "Singapore")}},
           headers=_as_team(su, emea))
    content = _basic_sheet([
        [1, "Zed", "Gulf Bank", "BFSI", "Dubai", "Product Demo", date(2026, 11, 2), "Completed"],
        [2, "Zed", "KL Retail", "Retail", "Kuala Lumpur", "Product Demo", date(2026, 11, 3), "Completed"],
        [3, "Zed", "Pune Pharma", "Pharma", "Pune", "Product Demo", date(2026, 11, 3), "Completed"],
        [4, "Zed", "Later Co", "IT", "Singapore", "Product Demo", date(2026, 12, 1), "Scheduled"],
    ])
    with team_session(emea) as db:
        out = G.sync(db, content)
        db.commit()
    assert out["alerts"] == [] and out["demos"]["added"] == 4 and out["demos"]["rejected"] == []
    assert out["revenue"]["added"] == 1

    snap = su.get("/api/dashboard", headers=_as_team(su, emea)).json()
    assert snap["kpis"]["qualified_completed"] == 3          # every Completed demo counts
    assert snap["f2f"]["achieved"] == 2                      # Dubai + Kuala Lumpur via City
    assert snap["f2f"]["per_region"]["United Arab Emirates"] == 1
    assert snap["revenue"]["per_bd"][0]["total_inr"] == 1200000
    demos = {d["customer_name"]: d for d in su.get("/api/demos", headers=_as_team(su, emea)).json()}
    assert demos["Gulf Bank"]["city"] == "Dubai" and demos["Gulf Bank"]["effective_type"] == "F2F"
    assert demos["Pune Pharma"]["effective_type"] is None
    # APAC is untouched.
    assert su.get("/api/dashboard", headers=_as_team(su, 1)).json()["kpis"]["qualified_completed"] == 0

    # Re-sync: columns the sheet doesn't have never wipe app values.
    with team_session(emea) as db:
        rec = db.query(DemoRecord).filter(DemoRecord.customer_name == "Pune Pharma").one()
        rec.demo_type = "Virtual"
        db.commit()
    with team_session(emea) as db:
        G.sync(db, content)
        db.commit()
        assert db.query(DemoRecord).filter(DemoRecord.customer_name == "Pune Pharma").one().demo_type == "Virtual"


def test_strict_team_still_requires_its_columns(two_teams):
    """APAC keeps its rules: the simpler sheet is rejected rather than silently counting."""
    with team_session(1) as db:
        out = G.sync(db, _basic_sheet([]))
        db.commit()
    assert any("Demos_and_Pipelines: missing column(s)" in a and "Qualified Demo" in a for a in out["alerts"])


def test_unbound_session_fails_closed(fresh_db):
    from app.db import SessionLocal
    with team_session(1) as db:
        db.add(BDMember(name="Alpha"))
        db.commit()
    with SessionLocal() as db:
        assert db.query(BDMember).count() == 0
        db.add(BDMember(name="Beta"))
        with pytest.raises(TeamScopeError):
            db.flush()


LEGACY = sorted((Path(__file__).resolve().parents[1] / "backups").glob("league-pre-teams-*.db"))


@pytest.mark.skipif(not LEGACY, reason="no pre-teams database backup available")
def test_legacy_database_upgrade(tmp_path):
    from app.migrate import ensure_schema
    db_file = tmp_path / "legacy.db"
    shutil.copy(LEGACY[0], db_file)
    before = sqlite3.connect(db_file)
    n_demos = before.execute("select count(*) from demo_records").fetchone()[0]
    n_bds = before.execute("select count(*) from bd_members").fetchone()[0]
    n_settings = before.execute("select count(*) from settings").fetchone()[0]
    before.close()

    eng = create_engine(f"sqlite:///{db_file}")
    ensure_schema(eng)
    ensure_schema(eng)  # idempotent
    insp = inspect(eng)
    for t in ("demo_records", "bd_members", "settings", "day_closures", "exchange_rates", "activity_events"):
        assert "team_id" in {c["name"] for c in insp.get_columns(t)}, t
    assert insp.get_pk_constraint("settings")["constrained_columns"] == ["team_id", "key"]
    con = sqlite3.connect(db_file)
    assert con.execute("select name, slug from teams").fetchall() == [("APAC", "apac")]
    assert con.execute("select count(*) from demo_records where team_id = 1").fetchone()[0] == n_demos
    assert con.execute("select count(*) from bd_members where team_id = 1").fetchone()[0] == n_bds
    assert con.execute("select count(*) from settings where team_id = 1").fetchone()[0] == n_settings
    assert {r[0] for r in con.execute("select role from admin_users")} <= {"super_admin"}
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()
    assert list((tmp_path / "backups").glob("legacy-pre-teams-*.db"))
    eng.dispose()


def test_setup_wizard_backend(two_teams, monkeypatch):
    """Wizard flow: settings for a team other than the one being viewed, sheet check, BD delete."""
    su, emea = two_teams
    T = _as_team(su, emea)
    r = su.put("/api/settings", json={"daily_target": 2, "league_start": "2027-01-04", "league_end": "2027-02-27"},
               headers=T)
    assert r.status_code == 200, r.text
    assert su.put("/api/settings", json={"daily_target": 0}, headers=T).status_code == 422
    assert su.get("/api/settings", headers=_as_team(su, 1)).json()["daily_target"] == 1

    zed = su.post("/api/bds", json={"name": "Zed"}, headers=T).json()["id"]
    typo = su.post("/api/bds", json={"name": "Zedd"}, headers=T).json()["id"]
    assert su.delete(f"/api/bds/{typo}", headers=T).status_code == 200
    su.post("/api/demos", json={"bd_id": zed, "customer_name": "A", "status": "Scheduled"}, headers=T)
    assert su.delete(f"/api/bds/{zed}", headers=T).status_code == 409  # has history

    content = _basic_sheet([[1, "Zed", "Gulf Bank", "BFSI", "Dubai", "Product Demo", date(2026, 11, 2), "Completed"],
                            [2, "Yara", "KL Retail", "Retail", "Kuala Lumpur", "Product Demo", date(2026, 11, 3), "Completed"]])
    monkeypatch.setattr(G, "fetch_xlsx", lambda url, timeout=45: (content, "Test Sheet"))
    url = "https://docs.google.com/spreadsheets/d/16DbYr551dULe0g3tsFME4ezg3-L2LDhBFXIh9j5Kxzg/"
    chk = su.post("/api/gsheet/check", json={"url": url}, headers=T).json()
    assert chk["ok"] and chk["unknown_bds"] == ["Yara"] and chk["bd_names"] == ["Yara", "Zed"]
    assert {s["sheet"]: s["rows"] for s in chk["sheets"]} == {"Demos_and_Pipelines": 2, "League_Revenue": 1}
    # Same sheet checked against the strict (APAC-style) rules -> missing columns reported.
    strict = su.post("/api/gsheet/check", json={"url": url, "count_requires_qualified": True,
                                                 "f2f_from_location": False}, headers=T).json()
    assert not strict["ok"] and "Qualified Demo" in strict["sheets"][0]["missing"]
    assert su.post("/api/gsheet/check", json={"url": "not a link"}, headers=T).status_code == 422


def test_f2f_countries_are_configurable_per_team(two_teams):
    su, emea = two_teams
    T = _as_team(su, emea)
    cat = {c["name"]: c["aliases"] for c in su.get("/api/countries", headers=T).json()}
    assert "Kenya" in cat and "nairobi" in cat["Kenya"] and len(cat) > 90
    # New team starts with no F2F countries; APAC keeps its regions.
    assert su.get("/api/settings", headers=T).json()["f2f_regions"] == {}
    assert set(su.get("/api/settings", headers=_as_team(su, 1)).json()["f2f_regions"]) == {"Malaysia", "Singapore", "Middle East"}

    assert su.put("/api/settings", json={"f2f_regions": {"Kenya": cat["Kenya"], "United Kingdom": cat["United Kingdom"]}},
                  headers=T).status_code == 200
    bd = su.post("/api/bds", json={"name": "Zed"}, headers=T).json()["id"]
    for cust, city in (("Safari Bank", "Nairobi"), ("Thames Ltd", "London"), ("KL Co", "Kuala Lumpur")):
        r = su.post("/api/demos", json={"bd_id": bd, "customer_name": cust, "city": city, "status": "Completed",
                                        "demo_date": "2026-11-03"}, headers=T)
        assert r.status_code == 200, r.text
    f2f = su.get("/api/dashboard", headers=T).json()["f2f"]
    assert f2f["per_region"] == {"Kenya": 1, "United Kingdom": 1}  # Malaysia is not one of this team's countries
    assert f2f["achieved"] == 2
    # Invalid shapes are rejected.
    assert su.put("/api/settings", json={"f2f_regions": {"Kenya": []}}, headers=T).status_code == 422
    assert su.put("/api/settings", json={"f2f_regions": ["Kenya"]}, headers=T).status_code == 422
