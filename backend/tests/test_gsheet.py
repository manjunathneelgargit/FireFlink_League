"""Live Google Sheet mirror (no network: the sync engine is fed workbook bytes)."""
import io
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal  # noqa: F401
from app.tenancy import team_session
from app.models import BDMember, DemoRecord
from app.services import gsheet as G

WORKBOOK = Path(__file__).resolve().parents[2] / "data" / "source_workbook_2026-11-03.xlsx"
NAMES = ["Abhirami", "Harsh", "Jitendra", "Nandini", "Nikhita", "Pratha", "Samiksha"]
pytestmark = pytest.mark.skipif(not WORKBOOK.exists(), reason="source workbook not present")


def _bytes(wb):
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _sync(content):
    with team_session() as db:
        out = G.sync(db, content)
        db.commit()
        return out


def _demos():
    with team_session() as db:
        return {d.customer_name: d for d in db.query(DemoRecord).filter(DemoRecord.deleted_at.is_(None))}


@pytest.fixture()
def seeded(fresh_db):
    with team_session() as db:
        for i, n in enumerate(NAMES):
            db.add(BDMember(name=n, display_order=i))
        db.commit()
    out = _sync(WORKBOOK.read_bytes())
    assert out["demos"]["added"] == 43 and out["demos"]["rejected"] == []
    return openpyxl.load_workbook(WORKBOOK)


def test_resync_is_idempotent(seeded):
    out = _sync(WORKBOOK.read_bytes())
    d = out["demos"]
    assert (d["added"], d["updated"], d["deleted"], d["unchanged"]) == (0, 0, 0, 43)


def test_sheet_changes_mirror_into_app(seeded):
    ws = seeded["Demos_and_Pipelines"]
    col = {c.value: i + 1 for i, c in enumerate(ws[1])}
    rows = {ws.cell(r, col["Customer Name"]).value: r for r in range(2, ws.max_row + 1)}
    # 1) reschedule + qualify Finsure (date change must UPDATE, not add)
    r = rows["Finsure"]
    ws.cell(r, col["Demo Date"]).value = ws.cell(rows["Savvyloans"], col["Demo Date"]).value  # 2 Nov
    ws.cell(r, col["Status"]).value = "Completed"
    ws.cell(r, col["Qualified Demo"]).value = "Yes"
    ws.cell(r, col["Demo Type"]).value = "F2F"
    # 2) invalid value on an existing row -> reported, record kept, not deleted
    ws.cell(rows["Verifile"], col["Demo Type"]).value = "Online"
    # 3) row removed from the sheet -> soft-deleted
    ws.delete_rows(rows["Qintess"])
    # 4) new row
    nr = ws.max_row + 1
    for h, v in {"Sl No": 99, "BD": "Harsh", "Customer Name": "New Co", "Status": "Scheduled", "Demo Type": "Virtual"}.items():
        ws.cell(nr, col[h]).value = v
    out = _sync(_bytes(seeded))["demos"]
    assert out["added"] == 1 and out["updated"] == 1 and out["deleted"] == 1
    assert [x["label"] for x in out["rejected"]] == ["Nikhita · Verifile"]
    d = _demos()
    assert "Qintess" not in d and "New Co" in d and "Verifile" in d
    fin = d["Finsure"]
    assert str(fin.demo_date) == "2026-11-02" and fin.status == "Completed" and fin.qualified == "Yes"
    assert d["Verifile"].demo_type is None  # untouched by the invalid row
    # Qualified blanked in the sheet -> mirrored (sheet is the source of truth)
    r = next(i for i in range(2, ws.max_row + 1) if ws.cell(i, col["Customer Name"]).value == "Finsure")
    ws.cell(r, col["Qualified Demo"]).value = None
    _sync(_bytes(seeded))
    assert _demos()["Finsure"].qualified is None


def test_mass_delete_safety_valve(seeded):
    ws = seeded["Demos_and_Pipelines"]
    ws.delete_rows(2, ws.max_row)  # sheet emptied by mistake
    out = _sync(_bytes(seeded))
    assert out["demos"]["deleted"] == 0 and any("safety" in a for a in out["alerts"])
    assert len(_demos()) == 43


def test_unknown_bd_is_rejected_not_created(seeded):
    ws = seeded["Demos_and_Pipelines"]
    ws.cell(ws.max_row + 1, 2).value = "Stranger"
    ws.cell(ws.max_row, 3).value = "X Co"
    ws.cell(ws.max_row, 12).value = "Scheduled"
    out = _sync(_bytes(seeded))
    assert any("Unknown BD" in e for x in out["demos"]["rejected"] for e in x["errors"])


def test_live_mode_locks_sheet_fields_but_allows_app_only_fields(seeded):
    from app.auth import hash_password
    from app.models import AdminUser
    with team_session() as db:
        db.add(AdminUser(username="admin", password_hash=hash_password("correct-horse-1"), role="super_admin"))
        db.commit()
    from app.main import app
    H = {"X-Requested-With": "ffl"}
    c = TestClient(app)
    c.post("/api/auth/login", json={"username": "admin", "password": "correct-horse-1"})
    assert c.put("/api/settings", json={"gsheet_sync_enabled": True}, headers=H).status_code == 200
    assert c.get("/api/meta").json()["live_mode"] is True
    demo = next(x for x in c.get("/api/demos").json() if x["customer_name"] == "Finsure")
    assert c.post("/api/demos", json={**demo, "customer_name": "Z"}, headers=H).status_code == 409
    assert c.put(f"/api/demos/{demo['id']}", json={**demo, "status": "Completed"}, headers=H).status_code == 409
    assert c.delete(f"/api/demos/{demo['id']}", headers=H).status_code == 409
    ok = c.put(f"/api/demos/{demo['id']}", json={**demo, "poc_remarks": "app-only note"}, headers=H)
    assert ok.status_code == 200, ok.text
    assert c.put("/api/settings", json={"gsheet_sync_interval_seconds": 5}, headers=H).status_code == 422
