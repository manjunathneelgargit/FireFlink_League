"""ORM models. Calculated values (counts, targets, carry-forward, ranks, totals) are NEVER stored
here as editable figures - they are derived in app.services.league from these raw records."""
import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import (JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Team(Base):
    """A league team (e.g. APAC). Every league record, setting and login below belongs to one team."""
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


ROLE_SUPER = "super_admin"   # manages every team, switches between them
ROLE_TEAM = "team_admin"     # sees and manages only its own team


class AdminUser(Base):
    __tablename__ = "admin_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_TEAM)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    team: Mapped["Team | None"] = relationship(lazy="joined")

    @property
    def is_super(self) -> bool:
        return self.role == ROLE_SUPER


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    user: Mapped[AdminUser] = relationship()


class BDMember(Base):
    __tablename__ = "bd_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("team_id", "name"),)


class DemoRecord(Base):
    """One row of the Demos_and_Pipelines worksheet (13 tracked fields) + app metadata."""
    __tablename__ = "demo_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    sl_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bd_id: Mapped[int] = mapped_column(ForeignKey("bd_members.id"))
    customer_name: Mapped[str] = mapped_column(String(300))
    domain: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    demo_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # F2F | Virtual | blank
    demo_on: Mapped[str | None] = mapped_column(String(120), nullable=True)
    demo_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    demo_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    time_zone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(40))
    qualified: Mapped[str | None] = mapped_column(String(3), nullable=True)  # Yes | No | blank
    # Sticky: becomes True when the demo is Completed. Keeps a completed demo's achievement when the
    # opportunity later moves into a POC status (POC must never erase an achieved demo).
    demo_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    poc_started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    poc_status_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    poc_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | import
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bd: Mapped[BDMember] = relationship(lazy="joined")


class RevenueRecord(Base):
    """One row of the League_Revenue worksheet (finalised 13 columns) + conversion metadata."""
    __tablename__ = "revenue_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    sl_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bd_id: Mapped[int] = mapped_column(ForeignKey("bd_members.id"))
    customer_name: Mapped[str] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(200), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(200), nullable=True)
    opportunity_name: Mapped[str] = mapped_column(String(300))
    contract_status: Mapped[str] = mapped_column(String(40))  # Signed | Amount Credited
    currency: Mapped[str] = mapped_column(String(10))
    contract_value: Mapped[float] = mapped_column(Numeric(18, 2))
    contract_signed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount_credited_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_onboarding_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional record-specific rate. If null, the configured ExchangeRate table is used.
    fx_rate_override: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    fx_rate_override_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bd: Mapped[BDMember] = relationship(lazy="joined")


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    currency: Mapped[str] = mapped_column(String(10))
    rate_to_inr: Mapped[float] = mapped_column(Numeric(18, 6))
    effective_date: Mapped[date] = mapped_column(Date)
    basis: Mapped[str | None] = mapped_column(String(300), nullable=True)  # e.g. "RBI reference rate"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    __table_args__ = (UniqueConstraint("team_id", "currency", "effective_date"),)


class DayClosure(Base):
    """Marks a league day as officially closed (manually, before the cutoff). Days are also closed
    automatically once the configured cutoff time passes - that needs no row."""
    __tablename__ = "day_closures"
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    closed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


class AwardFinalization(Base):
    __tablename__ = "award_finalizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    award_key: Mapped[str] = mapped_column(String(40))  # weekly_demo | league_champion | revenue | f2f
    period_key: Mapped[str] = mapped_column(String(40))  # week start ISO date or 'league'
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    result: Mapped[dict] = mapped_column(JSON)  # snapshot of winners/standings at finalization
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    finalized_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finalized_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    __table_args__ = (UniqueConstraint("team_id", "award_key", "period_key"),)


class ImportHistory(Base):
    __tablename__ = "import_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    file_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="preview")  # preview | applied | cancelled
    preview: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    bd_id: Mapped[int | None] = mapped_column(ForeignKey("bd_members.id"), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(80), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
