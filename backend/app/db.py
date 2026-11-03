"""Database engine/session setup. SQLite by default; set DATABASE_URL for PostgreSQL."""
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = f"sqlite:///{BASE_DIR / 'league.db'}"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DB)

_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def make_engine(url: str):
    """Used by tests to build an isolated engine."""
    eng = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    return eng
