"""The single monitoring schedule shared by all pages (configured on the Settings page)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..config import get_settings
from ..schedule import describe, due_occurrence, latest_occurrence, next_occurrence
from .settings_service import AppSettings


@dataclass
class GlobalSchedule:
    description: str
    next_run_at: datetime
    current_occurrence: datetime | None  # the run that is due now (None when nothing is due)


def compute(app: AppSettings, now: datetime) -> GlobalSchedule:
    dow = app.monitor_day_of_week if app.default_frequency == "weekly" else None
    occ = due_occurrence(now, app.tz, app.default_monitor_time, app.default_frequency, dow,
                         None, app.report_schedule_updated_at or now, get_settings().schedule_catchup_hours)
    return GlobalSchedule(
        description=describe(app.default_frequency, app.default_monitor_time, dow, app.timezone),
        next_run_at=next_occurrence(now, app.tz, app.default_monitor_time, app.default_frequency, dow),
        current_occurrence=occ,
    )


def latest(app: AppSettings, now: datetime) -> datetime:
    dow = app.monitor_day_of_week if app.default_frequency == "weekly" else None
    return latest_occurrence(now, app.tz, app.default_monitor_time, app.default_frequency, dow)
