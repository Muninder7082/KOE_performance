"""Pure schedule arithmetic (no I/O) — unit tested in tests/test_schedule.py.

A website is *due* when its most recent scheduled occurrence:
  * is after the last occurrence we already processed,
  * is after the moment its schedule was created/changed (no surprise runs), and
  * is not older than the catch-up window (a sleeping Space that wakes up late
    still runs today's check, but never replays a week of missed runs).
The external scheduler can therefore call the endpoint as often as it likes:
each occurrence runs at most once.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

FREQUENCY_HOURS: dict[str, int] = {
    "hourly": 1,
    "every_3_hours": 3,
    "every_6_hours": 6,
    "every_12_hours": 12,
    "daily": 24,
    "weekly": 168,
}
FREQUENCY_LABELS: dict[str, str] = {
    "hourly": "Every hour",
    "every_3_hours": "Every 3 hours",
    "every_6_hours": "Every 6 hours",
    "every_12_hours": "Every 12 hours",
    "daily": "Daily",
    "weekly": "Weekly",
}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def parse_hhmm(value: str) -> time:
    try:
        hh, mm = value.split(":")
        t = time(int(hh), int(mm))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Time must be HH:MM (24-hour)") from exc
    if len(hh) != 2 or len(mm) != 2:
        raise ValueError("Time must be HH:MM (24-hour)")
    return t


def _local_at(d: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz).astimezone(timezone.utc)


def latest_occurrence(
    now: datetime, tz: ZoneInfo, hhmm: str, frequency: str, day_of_week: int | None = None
) -> datetime:
    """Most recent scheduled instant <= now (UTC)."""
    if frequency not in FREQUENCY_HOURS:
        raise ValueError(f"Unknown frequency {frequency!r}")
    t = parse_hhmm(hhmm)
    local_now = now.astimezone(tz)
    today = local_now.date()
    if frequency == "weekly":
        dow = 0 if day_of_week is None else day_of_week
        d = today - timedelta(days=(today.weekday() - dow) % 7)
        occ = _local_at(d, t, tz)
        if occ > now:
            occ = _local_at(d - timedelta(days=7), t, tz)
        return occ
    if frequency == "daily":
        occ = _local_at(today, t, tz)
        if occ > now:
            occ = _local_at(today - timedelta(days=1), t, tz)
        return occ
    # Sub-daily: a fixed local wall-clock grid (e.g. every 6 h from 08:40 -> 02:40, 08:40,
    # 14:40, 20:40 every day). Every step divides 24, so the grid never drifts and DST
    # changes cannot create extra or shifted runs.
    return max(o for o in _grid(today - timedelta(days=1), t, frequency, tz)
               + _grid(today, t, frequency, tz) if o <= now)


def _grid(d: date, t: time, frequency: str, tz: ZoneInfo) -> list[datetime]:
    step = FREQUENCY_HOURS[frequency]
    first = t.hour % step
    return [_local_at(d, time(h, t.minute), tz) for h in range(first, 24, step)]


def next_occurrence(
    now: datetime, tz: ZoneInfo, hhmm: str, frequency: str, day_of_week: int | None = None
) -> datetime:
    latest = latest_occurrence(now, tz, hhmm, frequency, day_of_week)
    if frequency == "daily":
        d = latest.astimezone(tz).date() + timedelta(days=1)
        return _local_at(d, parse_hhmm(hhmm), tz)
    if frequency == "weekly":
        d = latest.astimezone(tz).date() + timedelta(days=7)
        return _local_at(d, parse_hhmm(hhmm), tz)
    t = parse_hhmm(hhmm)
    d = latest.astimezone(tz).date()
    return min(o for o in _grid(d, t, frequency, tz) + _grid(d + timedelta(days=1), t, frequency, tz)
               if o > latest)


def due_occurrence(
    now: datetime,
    tz: ZoneInfo,
    hhmm: str,
    frequency: str,
    day_of_week: int | None,
    last_processed: datetime | None,
    schedule_updated_at: datetime,
    catchup_hours: int,
) -> datetime | None:
    """Return the occurrence to run now, or None if nothing is due."""
    occ = latest_occurrence(now, tz, hhmm, frequency, day_of_week)
    if last_processed is not None and occ <= last_processed:
        return None
    if occ < schedule_updated_at:
        return None
    window = timedelta(hours=min(FREQUENCY_HOURS[frequency], catchup_hours))
    if now - occ > window:
        return None
    return occ


def describe(frequency: str, hhmm: str, day_of_week: int | None, tz_name: str) -> str:
    t = parse_hhmm(hhmm).strftime("%I:%M %p")
    if frequency == "daily":
        return f"Daily at {t} ({tz_name})"
    if frequency == "weekly":
        return f"Every {WEEKDAYS[day_of_week or 0]} at {t} ({tz_name})"
    return f"{FREQUENCY_LABELS[frequency]} from {t} ({tz_name})"
