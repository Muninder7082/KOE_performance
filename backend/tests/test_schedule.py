from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest

from app.schedule import due_occurrence, latest_occurrence, next_occurrence, parse_hhmm
from tests.conftest import ist

IST = ZoneInfo("Asia/Kolkata")


def test_daily_latest_and_next():
    now = ist(2026, 10, 8, 9, 0)
    assert latest_occurrence(now, IST, "08:40", "daily") == ist(2026, 10, 8, 8, 40)
    assert next_occurrence(now, IST, "08:40", "daily") == ist(2026, 10, 9, 8, 40)
    before = ist(2026, 10, 8, 8, 0)
    assert latest_occurrence(before, IST, "08:40", "daily") == ist(2026, 10, 7, 8, 40)


def test_individual_schedules_are_independent():
    now = ist(2026, 10, 8, 10, 5)
    created = ist(2026, 10, 1, 0, 0)
    a = due_occurrence(now, IST, "08:40", "daily", None, None, created, 6)
    b = due_occurrence(now, IST, "10:00", "daily", None, None, created, 6)
    c = due_occurrence(now, IST, "18:30", "daily", None, None, created, 6)
    assert a == ist(2026, 10, 8, 8, 40)
    assert b == ist(2026, 10, 8, 10, 0)
    assert c is None  # 18:30 yesterday is outside the 6h catch-up window


def test_each_occurrence_runs_once():
    created = ist(2026, 10, 1, 0, 0)
    now = ist(2026, 10, 8, 8, 45)
    occ = due_occurrence(now, IST, "08:40", "daily", None, None, created, 6)
    assert occ == ist(2026, 10, 8, 8, 40)
    later = ist(2026, 10, 8, 8, 55)
    assert due_occurrence(later, IST, "08:40", "daily", None, occ, created, 6) is None
    tomorrow = ist(2026, 10, 9, 8, 41)
    assert due_occurrence(tomorrow, IST, "08:40", "daily", None, occ, created, 6) == ist(2026, 10, 9, 8, 40)


def test_new_or_changed_schedule_does_not_run_retroactively():
    now = ist(2026, 10, 8, 10, 0)
    assert due_occurrence(now, IST, "08:40", "daily", None, None, ist(2026, 10, 8, 9, 0), 6) is None
    # created before today's time -> runs today
    assert due_occurrence(ist(2026, 10, 8, 8, 41), IST, "08:40", "daily", None, None,
                          ist(2026, 10, 8, 8, 30), 6) == ist(2026, 10, 8, 8, 40)


def test_catch_up_window_after_sleep():
    created = ist(2026, 10, 1, 0, 0)
    assert due_occurrence(ist(2026, 10, 8, 14, 0), IST, "08:40", "daily", None, None, created, 6) is not None
    assert due_occurrence(ist(2026, 10, 8, 15, 0), IST, "08:40", "daily", None, None, created, 6) is None


def test_every_6_hours_and_weekly():
    now = ist(2026, 10, 8, 20, 10)
    assert latest_occurrence(now, IST, "08:40", "every_6_hours") == ist(2026, 10, 8, 14, 40)
    early = ist(2026, 10, 8, 3, 0)
    assert latest_occurrence(early, IST, "08:40", "every_6_hours") == ist(2026, 10, 8, 2, 40)
    # 2026-10-08 is a Thursday (weekday 3)
    assert latest_occurrence(now, IST, "09:15", "weekly", 0) == ist(2026, 10, 5, 9, 15)
    assert latest_occurrence(ist(2026, 10, 5, 9, 0), IST, "09:15", "weekly", 0) == ist(2026, 9, 28, 9, 15)
    hourly = latest_occurrence(now, IST, "08:40", "hourly")
    assert hourly == ist(2026, 10, 8, 19, 40)
    assert next_occurrence(now, IST, "08:40", "hourly") - hourly == timedelta(hours=1)


def test_other_timezone():
    ny = ZoneInfo("America/New_York")
    now = ist(2026, 10, 8, 20, 0)  # 10:30 New York
    occ = latest_occurrence(now, ny, "10:00", "daily")
    assert occ.astimezone(ny).hour == 10


@pytest.mark.parametrize("bad", ["8:40", "24:00", "08:60", "abc", "", "08-40"])
def test_parse_rejects(bad):
    with pytest.raises(ValueError):
        parse_hhmm(bad)


def test_dst_fall_back_does_not_create_extra_runs():
    ny = ZoneInfo("America/New_York")
    from datetime import datetime, timezone
    # Walk 3 days across the 2026-11-01 fall-back in 5-minute steps; collect distinct occurrences.
    start = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    for freq, hhmm, per_day in (("every_12_hours", "23:00", 2), ("every_3_hours", "23:30", 8), ("hourly", "00:15", 24)):
        occs = {latest_occurrence(start + timedelta(minutes=5 * i), ny, hhmm, freq) for i in range(12 * 24 * 3)}
        local = sorted(o.astimezone(ny) for o in occs)
        utc = sorted(occs)
        gaps = {(b - a) for a, b in zip(utc, utc[1:])}  # real elapsed time
        step = timedelta(hours=24 // per_day)
        assert all(g >= step for g in gaps), (freq, sorted(gaps))
        assert {o.minute for o in local} == {int(hhmm[3:])}


def test_next_is_after_latest():
    now = ist(2026, 10, 8, 20, 10)
    for freq in ("hourly", "every_3_hours", "every_6_hours", "every_12_hours", "daily", "weekly"):
        assert next_occurrence(now, IST, "08:40", freq, 0) > now
