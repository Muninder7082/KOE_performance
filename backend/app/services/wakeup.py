"""Wake the server only around the scheduled run (saves free-hosting hours).

Free hosts such as Render put the app to sleep after ~15 minutes without inbound
requests. Instead of pinging it 24x7:

1. cron-job.org wakes it shortly before each scheduled run (WAKE_LEAD_MINUTES early,
   a few pings in a row so one slow cold start cannot leave it asleep). When
   CRONJOB_API_KEY and CRONJOB_JOB_ID are set, that job's schedule is updated
   automatically whenever the Settings schedule changes (cron-job.org REST API).
2. Once awake, the app keeps itself awake by requesting its own public URL
   (PUBLIC_BASE_URL/api/health) every few minutes, but only while a run is coming
   up or still unfinished.
3. When every page is tested and the report has been e-mailed, the pings stop and
   the host lets the server sleep again.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from ..clock import now_utc
from ..config import get_settings
from ..schedule import FREQUENCY_HOURS, WEEKDAYS, parse_hhmm
from .settings_service import AppSettings

log = logging.getLogger(__name__)

WAKE_LEAD_MINUTES = 20      # first wake-up ping this long before the run
WAKE_PINGS = 4              # consecutive one-minute pings (covers a slow cold start)
STAY_AWAKE_BEFORE = timedelta(minutes=WAKE_LEAD_MINUTES + 5)
SELF_PING_EVERY = timedelta(minutes=4)  # well under the host's 15-minute idle limit
CRONJOB_API = "https://api.cron-job.org"


def wake_schedule(app: AppSettings) -> dict:
    """cron-job.org schedule object that fires shortly before every scheduled run.

    cron-job.org schedules are a cross product of hours x minutes, so the wake minutes
    are kept inside one clock hour (relative to each run) to avoid stray executions.
    """
    t = parse_hhmm(app.default_monitor_time)
    step = FREQUENCY_HOURS[app.default_frequency]
    run_hours = [t.hour] if step >= 24 else list(range(t.hour % step, 24, step))
    groups: dict[int, list[int]] = {}
    for i in range(WAKE_PINGS):
        offset = t.minute - WAKE_LEAD_MINUTES + i  # minutes relative to the run's hour
        groups.setdefault(offset // 60, []).append(offset % 60)  # key -1 = previous hour
    hour_shift, minutes = max(groups.items(), key=lambda kv: (len(kv[1]), -kv[0]))
    hours = sorted({(h + hour_shift) % 24 for h in run_hours})
    wdays = [-1]
    if app.default_frequency == "weekly":
        cron_wday = (app.monitor_day_of_week + 1) % 7  # cron: 0 = Sunday; ours: 0 = Monday
        if t.hour + hour_shift < 0:
            cron_wday = (cron_wday - 1) % 7  # wake-up falls on the previous day
        wdays = [cron_wday]
    return {"timezone": app.timezone, "expiresAt": 0, "hours": hours, "minutes": sorted(minutes),
            "mdays": [-1], "months": [-1], "wdays": wdays}


def describe_wake(app: AppSettings) -> str:
    sch = wake_schedule(app)
    hours, minutes = sch["hours"], sch["minutes"]
    first = f"{hours[0]:02d}:{minutes[0]:02d}"
    span = f"{len(minutes)} pings from {first}" if len(hours) == 1 else (
        f"{len(minutes)} pings at minute {minutes[0]:02d}–{minutes[-1]:02d} of hours {', '.join(str(h) for h in hours)}")
    when = "daily" if sch["wdays"] == [-1] else f"every {WEEKDAYS[(sch['wdays'][0] - 1) % 7]}"
    return f"{when}, {span} ({app.timezone})"


@dataclass
class SyncStatus:
    configured: bool
    ok: bool | None = None
    message: str | None = None
    synced_at: datetime | None = None


class WakeupService:
    def __init__(self, http: httpx.AsyncClient | None = None):
        self._http = http
        self.status = SyncStatus(configured=self.configured)
        self._last_ping: datetime | None = None
        self.last_ping_ok: bool | None = None

    @property
    def configured(self) -> bool:
        s = get_settings()
        return bool(s.cronjob_api_key and s.cronjob_job_id)

    async def _client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._http is not None:
            return self._http, False
        return httpx.AsyncClient(timeout=30), True

    # ---- 1. keep cron-job.org in step with the Settings schedule ------------------------
    async def sync(self, app: AppSettings) -> SyncStatus:
        s = get_settings()
        if not self.configured:
            self.status = SyncStatus(configured=False)
            return self.status
        body = {"job": {"enabled": True, "schedule": wake_schedule(app)}}
        client, owned = await self._client()
        try:
            resp = await client.patch(f"{CRONJOB_API}/jobs/{s.cronjob_job_id}", json=body,
                                      headers={"Authorization": f"Bearer {s.cronjob_api_key}"})
            ok = resp.status_code < 300
            msg = f"Wake-up job updated: {describe_wake(app)}" if ok else f"cron-job.org HTTP {resp.status_code}: {resp.text[:200]}"
        except httpx.HTTPError as exc:
            ok, msg = False, f"cron-job.org unreachable: {type(exc).__name__}"
        finally:
            if owned:
                await client.aclose()
        msg = msg.replace(s.cronjob_api_key, "***")
        (log.info if ok else log.warning)(msg)
        self.status = SyncStatus(configured=True, ok=ok, message=msg, synced_at=now_utc())
        return self.status

    # ---- 2./3. stay awake only while a run is near or unfinished -------------------------
    @staticmethod
    def needs_to_stay_awake(now: datetime, current_occurrence: datetime | None,
                            done_occurrence: datetime | None, next_run_at: datetime, run_active: bool) -> bool:
        if run_active:
            return True
        if current_occurrence is not None and current_occurrence != done_occurrence:
            return True  # due / in progress / report not sent yet
        return next_run_at - now <= STAY_AWAKE_BEFORE

    async def keep_alive(self, need: bool) -> None:
        base = get_settings().public_base_url.rstrip("/")
        if not need or not base or not get_settings().keep_alive_enabled:
            return
        now = now_utc()
        if self._last_ping is not None and now - self._last_ping < SELF_PING_EVERY:
            return
        self._last_ping = now
        client, owned = await self._client()
        try:
            resp = await client.get(f"{base}/api/health", timeout=20)
            self.last_ping_ok = resp.status_code < 500
        except httpx.HTTPError:
            self.last_ping_ok = False
        finally:
            if owned:
                await client.aclose()
