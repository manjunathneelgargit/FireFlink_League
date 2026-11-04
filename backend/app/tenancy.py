"""Team isolation.

Every league table carries a `team_id`. A session is bound to one team with `bind_team(db, team_id)`;
from then on:

* every ORM SELECT / UPDATE / DELETE on a team-scoped model is automatically filtered to that team
  (`with_loader_criteria`), so existing queries such as `db.query(DemoRecord)` never see another
  team's rows, and
* every new team-scoped row is stamped with that team on flush.

A session that is NOT bound to a team cannot read or write team data (reads return nothing, writes
raise) - this fails closed instead of leaking data across teams.
"""
from __future__ import annotations

from sqlalchemy import event, false
from sqlalchemy.orm import Session, with_loader_criteria

from .models import (ActivityEvent, AuditLog, AwardFinalization, BDMember, DayClosure, DemoRecord, ExchangeRate,
                     ImportHistory, RevenueRecord, Setting)

TEAM_SCOPED = (BDMember, DemoRecord, RevenueRecord, ExchangeRate, DayClosure, Setting, AwardFinalization,
               ImportHistory, AuditLog, ActivityEvent)
_KEY = "team_id"
_UNSCOPED = "team_unscoped"


class TeamScopeError(RuntimeError):
    pass


def bind_team(db: Session, team_id: int) -> Session:
    db.info[_KEY] = int(team_id)
    db.info.pop(_UNSCOPED, None)
    return db


def team_of(db: Session) -> int | None:
    return db.info.get(_KEY)


def unscoped(db: Session) -> Session:
    """Opt a session out of team filtering (super-admin maintenance, background worker discovery)."""
    db.info.pop(_KEY, None)
    db.info[_UNSCOPED] = True
    return db


@event.listens_for(Session, "do_orm_execute")
def _scope_queries(state):
    if state.is_column_load or state.is_relationship_load:
        return
    if not (state.is_select or state.is_update or state.is_delete):
        return
    if state.session.info.get(_UNSCOPED):
        return
    tid = state.session.info.get(_KEY)
    for cls in TEAM_SCOPED:
        if tid is None:
            # Not bound to a team: fail closed - no team data is visible.
            state.statement = state.statement.options(
                with_loader_criteria(cls, lambda c: false(), include_aliases=True))
        else:
            state.statement = state.statement.options(
                with_loader_criteria(cls, lambda c: c.team_id == tid, include_aliases=True))


@event.listens_for(Session, "before_flush")
def _stamp_team(session: Session, _ctx, _instances):
    tid = session.info.get(_KEY)
    for obj in session.new:
        if not isinstance(obj, TEAM_SCOPED):
            continue
        if getattr(obj, "team_id", None) is None:
            if tid is None:
                if isinstance(obj, AuditLog):
                    continue  # super-admin actions outside a team are still audited
                raise TeamScopeError(f"Cannot save {type(obj).__name__} outside a team")
            obj.team_id = tid
        elif tid is not None and obj.team_id != tid:
            raise TeamScopeError(f"{type(obj).__name__} belongs to another team")


def team_session(team_id: int = 1) -> Session:
    """A new database session bound to one team (CLI, tests, background jobs)."""
    from .db import SessionLocal
    return bind_team(SessionLocal(), team_id)
