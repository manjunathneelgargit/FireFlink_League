"""Schema setup + one-time upgrade of a single-team database to the multi-team schema.

`ensure_schema(engine)` is safe to call on every start:
  * fresh database      -> creates all tables and a default team;
  * pre-teams database  -> adds `team_id` everywhere, moves all existing data into the "APAC" team,
                           makes every existing login a super admin, then creates any new tables.
SQLite tables whose primary key / unique constraints change are rebuilt (SQLite cannot alter
constraints); PostgreSQL is altered in place. Take a backup first - the app does this for SQLite.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import MetaData, inspect, text

from . import models  # noqa: F401 - register tables
from .db import Base
from .models import ROLE_SUPER, Team, utcnow

log = logging.getLogger("ffl.migrate")

LEGACY_TEAM_NAME = "APAC"
LEGACY_TEAM_SLUG = "apac"

# Tables that only gain a team_id column.
ADD_TEAM_COLUMN = ["demo_records", "revenue_records", "import_history", "audit_logs", "activity_events"]
# Tables whose primary key or unique constraints now include team_id.
REBUILD = {
    "bd_members": {"pk": None, "uniques": [("team_id", "name")]},
    "exchange_rates": {"pk": None, "uniques": [("team_id", "currency", "effective_date")]},
    "day_closures": {"pk": ("team_id", "day"), "uniques": []},
    "settings": {"pk": ("team_id", "key"), "uniques": []},
    "award_finalizations": {"pk": None, "uniques": [("team_id", "award_key", "period_key")]},
}


def _cols(insp, table) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def is_legacy(engine) -> bool:
    insp = inspect(engine)
    return insp.has_table("bd_members") and "team_id" not in _cols(insp, "bd_members")


def _backup_sqlite(engine) -> str | None:
    db_path = engine.url.database
    if not db_path or db_path == ":memory:" or not Path(db_path).exists():
        return None
    out = Path(db_path).parent / "backups"
    out.mkdir(exist_ok=True)
    dest = out / f"{Path(db_path).stem}-pre-teams-{datetime.now():%Y%m%d-%H%M%S}.db"
    import sqlite3
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(dest)
        with dst:
            src.backup(dst)
        dst.close()
    finally:
        src.close()
    return str(dest)


def _migrate_legacy(engine) -> None:
    sqlite = engine.dialect.name == "sqlite"
    if sqlite:
        bk = _backup_sqlite(engine)
        if bk:
            log.warning("Backed up the database to %s before the multi-team upgrade", bk)
    with engine.connect() as conn:
        if sqlite:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.commit()
        insp = inspect(conn)
        conn.commit()
        with conn.begin():
            Team.__table__.create(conn, checkfirst=True)
            tid = conn.execute(Team.__table__.insert().values(
                name=LEGACY_TEAM_NAME, slug=LEGACY_TEAM_SLUG, active=True, created_at=utcnow())).inserted_primary_key[0]

            for t in ADD_TEAM_COLUMN:
                if not insp.has_table(t) or "team_id" in _cols(insp, t):
                    continue
                conn.exec_driver_sql(f"ALTER TABLE {t} ADD COLUMN team_id INTEGER REFERENCES teams(id)")
                conn.execute(text(f"UPDATE {t} SET team_id = :tid"), {"tid": tid})
                conn.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS ix_{t}_team_id ON {t} (team_id)")
            if insp.has_table("demo_records") and "city" not in _cols(insp, "demo_records"):
                conn.exec_driver_sql("ALTER TABLE demo_records ADD COLUMN city VARCHAR(200)")

            if insp.has_table("admin_users"):
                ucols = _cols(insp, "admin_users")
                if "role" not in ucols:
                    conn.exec_driver_sql("ALTER TABLE admin_users ADD COLUMN role VARCHAR(20)")
                if "team_id" not in ucols:
                    conn.exec_driver_sql("ALTER TABLE admin_users ADD COLUMN team_id INTEGER REFERENCES teams(id)")
                # Existing logins managed the whole app -> they become super admins.
                conn.execute(text("UPDATE admin_users SET role = :r"), {"r": ROLE_SUPER})

            for t, spec in REBUILD.items():
                if not insp.has_table(t) or "team_id" in _cols(insp, t):
                    continue
                if sqlite:
                    _rebuild_sqlite(conn, insp, t, tid)
                else:
                    _alter_postgres(conn, insp, t, spec, tid)
        if sqlite:
            bad = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if bad:
                log.error("Foreign key problems after migration: %s", bad[:10])
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            conn.commit()


def _rebuild_sqlite(conn, insp, table: str, tid: int) -> None:
    md = MetaData()
    Base.metadata.tables["teams"].to_metadata(md)
    new = Base.metadata.tables[table].to_metadata(md, name=f"{table}__new")
    new.create(conn)
    old_cols = _cols(insp, table)
    cols = [c.name for c in new.columns if c.name != "team_id" and c.name in old_cols]
    collist = ", ".join(cols)
    conn.execute(text(f"INSERT INTO {table}__new (team_id, {collist}) SELECT :tid, {collist} FROM {table}"),
                 {"tid": tid})
    conn.exec_driver_sql(f"DROP TABLE {table}")
    conn.exec_driver_sql(f"ALTER TABLE {table}__new RENAME TO {table}")


def _alter_postgres(conn, insp, table: str, spec: dict, tid: int) -> None:
    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN team_id INTEGER REFERENCES teams(id)")
    conn.execute(text(f"UPDATE {table} SET team_id = :tid"), {"tid": tid})
    conn.exec_driver_sql(f"ALTER TABLE {table} ALTER COLUMN team_id SET NOT NULL")
    conn.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS ix_{table}_team_id ON {table} (team_id)")
    for uc in insp.get_unique_constraints(table):
        conn.exec_driver_sql(f'ALTER TABLE {table} DROP CONSTRAINT "{uc["name"]}"')
    if spec["pk"]:
        pk = insp.get_pk_constraint(table)
        if pk.get("name"):
            conn.exec_driver_sql(f'ALTER TABLE {table} DROP CONSTRAINT "{pk["name"]}"')
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD PRIMARY KEY ({', '.join(spec['pk'])})")
    for i, cols in enumerate(spec["uniques"]):
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD CONSTRAINT uq_{table}_team_{i} UNIQUE ({', '.join(cols)})")


def ensure_default_team(engine) -> None:
    from sqlalchemy.orm import Session
    with Session(engine) as db:
        db.info["team_unscoped"] = True
        if db.query(Team).count() == 0:
            db.add(Team(name=LEGACY_TEAM_NAME, slug=LEGACY_TEAM_SLUG))
            db.commit()


def ensure_schema(engine) -> None:
    if is_legacy(engine):
        log.warning("Upgrading the database to the multi-team schema (existing data -> team '%s')",
                    LEGACY_TEAM_NAME)
        _migrate_legacy(engine)
    Base.metadata.create_all(engine)
    ensure_default_team(engine)
