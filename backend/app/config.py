"""League configuration stored in the `settings` table, with defaults from the master spec."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, time

from sqlalchemy.orm import Session

from .models import Setting

DEFAULTS: dict = {
    "league_name": "FireFlink 4.0 – Go Beyond – Ee Sala Market Namde!",
    "league_start": "2026-11-01",
    "league_end": "2026-12-20",
    "timezone": "Asia/Kolkata",
    "office_login_time": "08:30",
    "standup_time": "08:45",
    "day_cutoff_time": "23:59",
    "week_start_day": 0,  # 0 = Monday ... 6 = Sunday
    "daily_target": 1,
    "f2f_target": 45,
    "f2f_milestones": [10, 20, 30, 40, 45],
    "revenue_threshold_inr": 1000000,
    # Region -> aliases matched (case-insensitive) against tokens of the free-text Country field.
    "f2f_regions": {
        "Malaysia": ["malaysia", "malasia", "kuala lumpur", "penang", "johor"],
        "Singapore": ["singapore", "sg"],
        "Middle East": [
            "uae", "u.a.e", "united arab emirates", "dubai", "abu dhabi", "aabu dhabi", "sharjah", "ajman",
            "saudi", "saudi arabia", "ksa", "soudi", "riyadh", "jeddah", "dammam", "qatar", "doha", "oman",
            "muscat", "bahrain", "manama", "kuwait",
        ],
    },
    # Informational only (admin decision 2026-11-03): every league date counts for the F2F challenge.
    "f2f_windows": [
        {"regions": ["Malaysia", "Singapore"], "start": "2026-11-16", "end": "2026-11-27"},
        {"regions": ["Middle East"], "start": "2026-11-23", "end": "2026-12-05"},
    ],
    "awards": {
        "weekly_demo": {"title": "Weekly Demo Champion", "prize": "₹1,500 Amazon voucher"},
        "league_champion": {"title": "Champion of the League", "prize": None},  # not confirmed
        "revenue": {"title": "Revenue Champion", "prize": "₹1,00,000 cash", "prize_amount_inr": 100000},
        "f2f": {"title": "F2F Champion", "prize": "₹1,500"},
    },
    "motivational_messages": [
        "Champions are made by what they do every single day.",
        "Don't watch the leaderboard. Make someone watch you.",
        "One more demo. One more opportunity. One step closer to the championship.",
        "Consistency creates champions. Every single day counts.",
        "The market belongs to those who go beyond!",
    ],
    "arena_refresh_seconds": 30,
    # Live Google Sheet mode: the sheet is the source of truth for demo + revenue rows.
    "gsheet_url": "https://docs.google.com/spreadsheets/d/16DbYr551dULe0g3tsFME4ezg3-L2LDhBFXIh9j5Kxzg/",
    "gsheet_sync_enabled": False,
    "gsheet_sync_interval_seconds": 60,
    "arena_token_hash": None,
    # Sheet-format rules (per team). APAC's sheet has Qualified Demo + Demo Type + Country columns;
    # other teams may track a simpler sheet.
    #  - count_requires_qualified: True  -> a demo counts only when Completed AND Qualified Demo = Yes.
    #                              False -> every Completed demo counts unless Qualified Demo = No.
    #  - f2f_from_location: True -> when Demo Type is blank, a demo whose Country/City maps to an
    #                       F2F challenge region is treated as F2F.
    "count_requires_qualified": True,
    "f2f_from_location": False,
}

# Overrides applied when a NEW team is created (on top of DEFAULTS). Existing teams keep their values.
NEW_TEAM_DEFAULTS: dict = {
    "gsheet_url": "",
    "gsheet_sync_enabled": False,
    "count_requires_qualified": False,
    "f2f_from_location": True,
}


@dataclass
class LeagueConfig:
    league_name: str
    league_start: date
    league_end: date
    timezone: str
    office_login_time: time
    day_cutoff_time: time
    week_start_day: int
    daily_target: int
    f2f_target: int
    f2f_milestones: list[int]
    revenue_threshold_inr: float
    f2f_regions: dict[str, list[str]]
    require_qualified: bool = True
    f2f_from_location: bool = False
    raw: dict = field(default_factory=dict)


def _t(s: str) -> time:
    h, m = s.split(":")[:2]
    return time(int(h), int(m))


def load_raw(db: Session) -> dict:
    data = copy.deepcopy(DEFAULTS)
    for row in db.query(Setting).all():
        data[row.key] = row.value
    return data


def to_config(raw: dict) -> LeagueConfig:
    return LeagueConfig(
        league_name=raw["league_name"],
        league_start=date.fromisoformat(raw["league_start"]),
        league_end=date.fromisoformat(raw["league_end"]),
        timezone=raw["timezone"],
        office_login_time=_t(raw["office_login_time"]),
        day_cutoff_time=_t(raw["day_cutoff_time"]),
        week_start_day=int(raw["week_start_day"]),
        daily_target=int(raw["daily_target"]),
        f2f_target=int(raw["f2f_target"]),
        f2f_milestones=[int(x) for x in raw["f2f_milestones"]],
        revenue_threshold_inr=float(raw["revenue_threshold_inr"]),
        f2f_regions={k: [a.lower().strip() for a in v] for k, v in raw["f2f_regions"].items()},
        require_qualified=bool(raw.get("count_requires_qualified", True)),
        f2f_from_location=bool(raw.get("f2f_from_location", False)),
        raw=raw,
    )


def load_config(db: Session) -> LeagueConfig:
    return to_config(load_raw(db))


EDITABLE_KEYS = {
    "league_name", "league_start", "league_end", "daily_target", "office_login_time", "standup_time", "day_cutoff_time",
    "week_start_day", "f2f_target", "f2f_milestones", "revenue_threshold_inr", "f2f_regions", "f2f_windows",
    "awards", "motivational_messages", "arena_refresh_seconds", "timezone",
    "gsheet_url", "gsheet_sync_enabled", "gsheet_sync_interval_seconds",
    "count_requires_qualified", "f2f_from_location",
}


def save_setting(db: Session, key: str, value) -> None:
    """Saves a setting for the session's team (the team filter applies to this query)."""
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
