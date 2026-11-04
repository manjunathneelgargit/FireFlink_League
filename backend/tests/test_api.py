"""API / import / export acceptance tests (Section 22)."""
import io
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.constants import DEMO_HEADERS, REVENUE_HEADERS
from app.db import SessionLocal  # noqa: F401
from app.tenancy import team_session
from app.main import app
from app.models import AdminUser, AuditLog

WORKBOOK = Path(__file__).resolve().parents[2] / "data" / "source_workbook_2026-11-03.xlsx"
H = {"X-Requested-With": "ffl"}


@pytest.fixture()
def client(fresh_db):
    with team_session() as db:
        db.add(AdminUser(username="admin", password_hash=hash_password("correct-horse-1"), role="super_admin"))
        db.commit()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "correct-horse-1"})
    assert r.status_code == 200
    return c


def _bds(c, names=("Alpha", "Bravo")):
    for n in names:
        c.post("/api/bds", json={"name": n}, headers=H)
    return {b["name"]: b["id"] for b in c.get("/api/bds").json()}


def _demo(c, bd, **kw):
    body = {"bd_id": bd, "customer_name": kw.pop("customer_name", "Acme"), "status": "Scheduled",
            "demo_date": "2026-11-02", "demo_type": "Virtual", **kw}
    return c.post("/api/demos", json=body, headers=H)


# ----------------------------------------------------------------------------- security
def test_auth_required_everywhere(fresh_db):
    c = TestClient(app)
    for path in ("/api/dashboard", "/api/demos", "/api/revenue", "/api/settings", "/api/audit", "/api/arena",
                 "/api/export/workbook"):
        assert c.get(path).status_code == 401, path
    assert c.post("/api/auth/login", json={"username": "x", "password": "y"}).status_code == 401


def test_csrf_header_required(client):
    bd = _bds(client)["Alpha"]
    r = client.post("/api/demos", json={"bd_id": bd, "customer_name": "X", "status": "Scheduled"})
    assert r.status_code == 403


def test_arena_token(client):
    tok = client.post("/api/settings/arena-link", headers=H).json()["token"]
    anon = TestClient(app)
    assert anon.get(f"/api/arena?token={tok}").status_code == 200
    assert anon.get("/api/arena?token=wrong").status_code == 401
    assert anon.get(f"/api/dashboard?token={tok}").status_code == 401  # token is arena-only


# ----------------------------------------------------------------------------- demos
def test_scheduled_to_completed_counts_once_and_validation(client):
    bd = _bds(client)["Alpha"]
    d = _demo(client, bd).json()
    assert client.get("/api/dashboard").json()["kpis"]["qualified_completed"] == 0
    upd = {**d, "status": "Completed", "qualified": "Yes"}
    assert client.put(f"/api/demos/{d['id']}", json=upd, headers=H).status_code == 200
    assert client.put(f"/api/demos/{d['id']}", json={**upd, "demo_type": "F2F"}, headers=H).status_code == 200
    k = client.get("/api/dashboard").json()["kpis"]
    assert k["qualified_completed"] == 1
    # POC keeps the achievement, no extra count
    client.put(f"/api/demos/{d['id']}", json={**upd, "status": "POC Initiated"}, headers=H)
    assert client.get("/api/dashboard").json()["kpis"]["qualified_completed"] == 1
    poc = [x for x in client.get("/api/demos").json() if x["status"] == "POC Initiated"][0]
    assert poc["poc_started_on"] is not None
    # Qualified only when completed; invalid demo type rejected
    r = _demo(client, bd, customer_name="B", qualified="Yes")
    assert r.status_code == 422 and "Completed" in str(r.json())
    r = _demo(client, bd, customer_name="C", demo_type="In-person")
    assert r.status_code == 422 and "Demo Type" in str(r.json())
    r = _demo(client, bd, customer_name="D", status="Completed", demo_date="2027-01-05")
    assert r.status_code == 422


def test_soft_delete_restore_and_audit(client):
    bd = _bds(client)["Alpha"]
    d = _demo(client, bd, status="Completed", qualified="Yes").json()
    assert client.delete(f"/api/demos/{d['id']}", headers=H).status_code == 200
    assert client.get("/api/dashboard").json()["kpis"]["qualified_completed"] == 0
    assert len(client.get("/api/demos?deleted=true").json()) == 1
    client.post(f"/api/demos/{d['id']}/restore", headers=H)
    assert client.get("/api/dashboard").json()["kpis"]["qualified_completed"] == 1
    actions = {a["action"] for a in client.get("/api/audit").json()}
    assert {"create", "delete", "restore", "login"} <= actions
    acts = [a["kind"] for a in client.get("/api/activity").json()]
    assert "new_leader" in acts and "qualified_demo" in acts


# ----------------------------------------------------------------------------- revenue
def test_revenue_duplicate_blocked_and_status_change(client):
    bd = _bds(client)["Alpha"]
    body = {"bd_id": bd, "customer_name": "Acme", "opportunity_name": "FireFlink License",
            "contract_status": "Signed", "currency": "INR", "contract_value": 1500000,
            "contract_signed_date": "2026-11-02"}
    r = client.post("/api/revenue", json=body, headers=H).json()
    assert client.post("/api/revenue", json=body, headers=H).status_code == 409
    client.put(f"/api/revenue/{r['id']}", json={**body, "contract_status": "Amount Credited",
                                                "amount_credited_date": "2026-11-03"}, headers=H)
    d = client.get("/api/dashboard").json()
    assert d["revenue"]["total_inr"] == 1500000
    assert d["revenue"]["champions"][0]["bd_name"] == "Alpha"
    usd = {**body, "opportunity_name": "Resources", "currency": "USD", "contract_value": 10000}
    client.post("/api/revenue", json=usd, headers=H)
    assert client.get("/api/dashboard").json()["revenue"]["pending_conversion_count"] == 1
    assert client.post("/api/rates", json={"currency": "USD", "rate_to_inr": 88, "effective_date": "2026-11-01",
                                           "basis": "Admin-entered test rate"}, headers=H).status_code == 200
    assert client.get("/api/dashboard").json()["revenue"]["total_inr"] == 1500000 + 880000


# ----------------------------------------------------------------------------- filters vs official
def test_filtered_report_never_changes_official(client):
    ids = _bds(client)
    _demo(client, ids["Alpha"], status="Completed", qualified="Yes")
    _demo(client, ids["Alpha"], customer_name="Z", status="Completed", qualified="Yes", demo_date="2026-11-01")
    _demo(client, ids["Bravo"], customer_name="Y", status="Completed", qualified="Yes", demo_type="F2F",
          country="Singapore")
    before = client.get("/api/dashboard").json()["overall"]
    f = client.post("/api/reports/query", json={"bd_ids": [ids["Bravo"]], "demo_types": ["F2F"]},
                    headers=H).json()
    assert f["label"] == "Filtered Results" and f["kpis"]["qualified_completed"] == 1 and f["matching"]["demos"] == 1
    f2 = client.post("/api/reports/query", json={"from_date": "2026-11-02", "to_date": "2026-11-02"},
                     headers=H).json()
    assert f2["matching"]["demos"] == 2  # inclusive boundaries
    after = client.get("/api/dashboard").json()["overall"]
    assert before == after and after[0]["bd_name"] == "Alpha"
    x = client.post("/api/export/filtered", json={"bd_ids": [ids["Bravo"]]}, headers=H)
    assert x.status_code == 200


# ----------------------------------------------------------------------------- import / export
def _preview(c, content: bytes, name="wb.xlsx"):
    r = c.post("/api/import/preview", files={"file": (name, content)}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.skipif(not WORKBOOK.exists(), reason="source workbook not present")
def test_real_workbook_import_reimport_incremental_and_export(client):
    content = WORKBOOK.read_bytes()
    p = _preview(client, content)
    assert p["bd_proposals"] == ["Abhirami", "Harsh", "Jitendra", "Nandini", "Nikhita", "Pratha", "Samiksha"]
    assert p["demos_counts"]["add"] == 43 and p["demos_counts"]["rejected"] == 0
    s = client.post(f"/api/import/{p['id']}/apply", json={"add_bds": p["bd_proposals"]}, headers=H).json()
    assert s["demos"]["added"] == 43
    # Re-import identical file: nothing added
    p2 = _preview(client, content)
    assert p2["previously_imported"] and p2["demos_counts"]["unchanged"] == 43 and p2["demos_counts"]["add"] == 0
    client.post(f"/api/import/{p2['id']}/apply", json={}, headers=H)
    assert len(client.get("/api/demos").json()) == 43

    # Incremental: change a status, blank a cell, add a row, add an invalid row
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb["Demos_and_Pipelines"]
    hdr = [c.value for c in ws[1]]
    col = {h: i + 1 for i, h in enumerate(hdr)}
    target_row = next(r for r in range(2, ws.max_row + 1) if ws.cell(r, col["Customer Name"]).value == "Finsure")
    ws.cell(target_row, col["Status"]).value = "Rescheduled"
    ws.cell(target_row, col["Domain"]).value = None  # blank must NOT erase existing value
    nr = ws.max_row + 1
    for h, v in {"Sl No": 99, "BD": "Harsh", "Customer Name": "NewCo", "Status": "Scheduled", "Demo Type": "F2F",
                 "Country": "Malaysia"}.items():
        ws.cell(nr, col[h]).value = v
    for h, v in {"Sl No": 100, "BD": "Harsh", "Customer Name": "BadCo", "Status": "Scheduled",
                 "Demo Type": "Online"}.items():
        ws.cell(nr + 1, col[h]).value = v
    buf = io.BytesIO()
    wb.save(buf)
    p3 = _preview(client, buf.getvalue())
    c3 = p3["demos_counts"]
    assert c3["add"] == 1 and c3["update"] == 1 and c3["rejected"] == 1
    upd = next(r for r in p3["demos"] if r["action"] == "update")
    assert upd["selected"] is False and "domain" in upd["kept"] and upd["diff"]["status"]["to"] == "Rescheduled"
    # Apply WITHOUT ticking the update: existing record must not be overwritten
    client.post(f"/api/import/{p3['id']}/apply", json={}, headers=H)
    fin = next(d for d in client.get("/api/demos").json() if d["customer_name"] == "Finsure")
    assert fin["status"] == "Scheduled" and fin["domain"] == "Financial Services"
    assert len(client.get("/api/demos").json()) == 44
    # Same file again, this time explicitly confirming the update
    p4 = _preview(client, buf.getvalue())
    upd = next(r for r in p4["demos"] if r["action"] == "update")
    client.post(f"/api/import/{p4['id']}/apply", json={"decisions": {"demos": {str(upd["row"]): {"do": "update"}}}},
                headers=H)
    fin = next(d for d in client.get("/api/demos").json() if d["customer_name"] == "Finsure")
    assert fin["status"] == "Rescheduled" and fin["domain"] == "Financial Services"
    assert len(client.get("/api/demos").json()) == 44
    assert len(client.get("/api/import/history").json()) == 4

    # Export preserves structure
    x = client.get("/api/export/workbook")
    assert x.status_code == 200
    out = openpyxl.load_workbook(io.BytesIO(x.content))
    assert [c.value for c in out["Demos_and_Pipelines"][1]] == DEMO_HEADERS
    assert [c.value for c in out["League_Revenue"][1]] == REVENUE_HEADERS
    assert out["Demos_and_Pipelines"].max_row == 45
    # Exported workbook re-imports cleanly with no duplicates
    p5 = _preview(client, x.content)
    assert p5["demos_counts"]["add"] == 0 and p5["demos_counts"]["rejected"] == 0


def test_import_rejects_missing_headers(client):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Demos_and_Pipelines"
    ws.append(["Sl No", "BD", "Customer Name"])
    buf = io.BytesIO()
    wb.save(buf)
    p = _preview(client, buf.getvalue())
    levels = {(i["sheet"], i["level"]) for i in p["sheet_issues"]}
    assert ("Demos_and_Pipelines", "error") in levels and ("League_Revenue", "error") in levels


def test_day_close_and_award_finalize_rules(client):
    _bds(client)
    assert client.post("/api/days/2026-11-08/close", headers=H).status_code == 422  # Sunday
    assert client.post("/api/days/2027-01-04/close", headers=H).status_code == 422  # future / outside league
    r = client.post("/api/awards/finalize", json={"award_key": "league_champion", "period_key": "league"}, headers=H)
    assert r.status_code == 422  # league not over


def test_settings_validation_and_audit(client):
    assert client.put("/api/settings", json={"day_cutoff_time": "19:30"}, headers=H).status_code == 200
    assert client.put("/api/settings", json={"league_end": "2026-10-01"}, headers=H).status_code == 422
    assert client.put("/api/settings", json={"hack": 1}, headers=H).status_code == 422
    with team_session() as db:
        assert db.query(AuditLog).filter_by(entity="settings").count() == 1
