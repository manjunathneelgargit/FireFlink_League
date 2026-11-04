"""Admin CLI.

  python manage.py create-admin <username>                    (super admin; prompts for password)
  python manage.py import-workbook <file.xlsx> [team-slug]    (preview + apply all new rows, add BDs from
                                                               workbook; default team: the first team)
"""
import getpass
import sys
from pathlib import Path

from app import models, tenancy  # noqa: F401
from app.auth import hash_password
from app.db import SessionLocal, engine
from app.migrate import ensure_schema
from app.models import ROLE_SUPER, AdminUser, Team
from app.services import importer as I


def create_admin(username: str):
    pw = getpass.getpass("Password (min 10 chars): ")
    if len(pw) < 10 or pw != getpass.getpass("Repeat: "):
        sys.exit("Passwords must match and be at least 10 characters.")
    with SessionLocal() as db:
        u = db.query(AdminUser).filter_by(username=username).first()
        if u:
            u.password_hash = hash_password(pw)
            print(f"Password reset for {username}")
        else:
            db.add(AdminUser(username=username, password_hash=hash_password(pw), role=ROLE_SUPER))
            print(f"Super admin {username} created")
        db.commit()


def import_workbook(path: str, team_slug: str | None = None):
    content = Path(path).read_bytes()
    with SessionLocal() as db:
        q = db.query(Team)
        team = q.filter(Team.slug == team_slug).first() if team_slug else q.order_by(Team.id).first()
        if team is None:
            sys.exit(f"Team '{team_slug}' not found")
        tenancy.bind_team(db, team.id)
        print(f"Importing into team: {team.name}")
        hist = I.build_preview(db, content, Path(path).name, "cli")
        p = hist.preview
        for issue in p["sheet_issues"]:
            print(f"[{issue['level']}] {issue['sheet']}: {issue['message']}")
        print("BDs to add:", p["bd_proposals"])
        print("Demos:", p["demos_counts"], "Revenue:", p["revenue_counts"])
        for kind in ("demos", "revenue"):
            for r in p[kind]:
                if r["action"] in ("rejected", "review", "duplicate"):
                    print(f"  {kind} row {r['row']} {r['action']}: {r['label']} - {r['errors'] + r['warnings']}")
        summary = I.apply_import(db, hist, {}, p["bd_proposals"], "cli")
        db.commit()
        print("Applied:", summary)


if __name__ == "__main__":
    ensure_schema(engine)
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    {"create-admin": create_admin, "import-workbook": import_workbook}.get(cmd, lambda *_: sys.exit(__doc__))(*args)
