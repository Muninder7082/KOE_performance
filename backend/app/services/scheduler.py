"""SchedulerService — server-side scheduled monitoring.

Entry point for POST /api/internal/run-scheduled-checks (external cron) and the
optional in-process loop. Both call run_cycle(); a database lease lock makes
concurrent triggers harmless, and per-occurrence bookkeeping makes repeated
triggers idempotent (each scheduled occurrence runs once).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .. import locks
from ..clock import now_utc
from ..config import get_settings
from ..models import MonitoredWebsite, ScheduledTask, TaskRun
from . import global_schedule, settings_service
from .excel import ExcelReportService
from .monitoring import PerformanceMonitoringService, WebsiteNotFound
from .report import ReportService

log = logging.getLogger(__name__)

CYCLE_LOCK = "monitoring_cycle"
REPORT_TASK = "daily_report"
LEASE_TTL = 300
EXCEL_FLUSH_EVERY = 10
MAX_REPORT_ATTEMPTS = 3
PURGE_TASK = "report_purge"


class SchedulerService:
    def __init__(self, sf: async_sessionmaker[AsyncSession], monitoring: PerformanceMonitoringService,
                 excel: ExcelReportService, report: ReportService):
        self.sf = sf
        self.monitoring = monitoring
        self.excel = excel
        self.report = report
        self._tasks: set[asyncio.Task] = set()
        self._report_attempts: dict[datetime, int] = {}
        # In-memory state so idle ticks (every minute) never touch the database. This lets the
        # free Neon database scale to zero between runs instead of staying awake 24x7.
        self._settings_cache: settings_service.AppSettings | None = None
        self._done_occurrence: datetime | None = None

    def invalidate(self) -> None:
        """Called when Settings change: forget the cached schedule."""
        self._settings_cache = None
        self._done_occurrence = None

    async def _cached_occurrence(self, now: datetime) -> datetime | None:
        if self._settings_cache is None:
            async with self.sf() as session:
                self._settings_cache = await settings_service.load(session)
        return global_schedule.compute(self._settings_cache, now).current_occurrence

    # ---- what is due -------------------------------------------------------------
    async def _occurrence(self, now: datetime) -> datetime | None:
        """The global scheduled run that is currently due (same time for every page)."""
        async with self.sf() as session:
            app = await settings_service.load(session)
        return global_schedule.compute(app, now).current_occurrence

    async def due_websites(self, now: datetime) -> list[tuple[int, datetime]]:
        """Active pages not yet tested for the current run. Pages added after the run's
        start time wait for the next run."""
        occ = await self._occurrence(now)
        if occ is None:
            return []
        async with self.sf() as session:
            ids = (await session.scalars(
                select(MonitoredWebsite.id)
                .where(MonitoredWebsite.is_active.is_(True), MonitoredWebsite.created_at <= occ,
                       or_(MonitoredWebsite.last_scheduled_run_at.is_(None),
                           MonitoredWebsite.last_scheduled_run_at < occ))
                .order_by(MonitoredWebsite.id))).all()
        return [(i, occ) for i in ids]

    async def report_due(self, now: datetime) -> datetime | None:
        """The report goes out once every page of the current run has been tested."""
        occ = await self._occurrence(now)
        if occ is None:
            return None
        async with self.sf() as session:
            app = await settings_service.load(session)
            task = await session.scalar(select(ScheduledTask).where(ScheduledTask.name == REPORT_TASK))
        if not app.daily_report_enabled:
            return None
        if task is not None and task.last_occurrence_at is not None and task.last_occurrence_at >= occ:
            return None
        if await self.due_websites(now):
            return None  # still testing (or resuming after a restart)
        return occ

    # ---- triggering ----------------------------------------------------------------
    async def is_running(self) -> bool:
        async with self.sf() as session:
            row = await session.scalar(select(ScheduledTask).where(ScheduledTask.name == CYCLE_LOCK))
        return bool(row and row.locked_until and row.locked_until > now_utc())

    async def trigger(self, trigger: str, wait: bool = False) -> dict:
        occ = await self._cached_occurrence(now_utc())
        if occ is None or occ == self._done_occurrence:
            # Nothing due, or this run already finished: answer without any database query.
            return {"status": "idle", "websites_due": 0, "report_sent": None}
        if await self.is_running():
            return {"status": "already_running"}
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        if wait:
            return await self.run_cycle(trigger, run_id)
        now = now_utc()
        due, report = len(await self.due_websites(now)), (await self.report_due(now)) is not None
        task = asyncio.create_task(self.run_cycle(trigger, run_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return {"status": "started", "run_id": run_id, "websites_due": due, "report_due": report}

    async def shutdown(self) -> None:
        for t in list(self._tasks):
            t.cancel()

    async def _keep_lease(self, owner: str, lost: asyncio.Event) -> None:
        """Extend the cycle lease; survives DB blips and flags a lost lease."""
        failures = 0
        while True:
            await asyncio.sleep(LEASE_TTL / 5)
            try:
                if not await locks.refresh(self.sf, CYCLE_LOCK, LEASE_TTL, owner):
                    log.error("Scheduler lease lost; stopping this cycle before starting new tests")
                    lost.set()
                    return
                failures = 0
            except Exception:  # noqa: BLE001
                failures += 1
                log.warning("Lease refresh failed (%d)", failures, exc_info=True)

    async def _claim(self, website_id: int, occ: datetime) -> bool:
        """Atomically mark this occurrence as taken. Exactly one caller wins, even across
        overlapping cycles or containers, so an occurrence is never tested twice."""
        async with self.sf() as session:
            res = await session.execute(
                update(MonitoredWebsite)
                .where(MonitoredWebsite.id == website_id,
                       or_(MonitoredWebsite.last_scheduled_run_at.is_(None),
                           MonitoredWebsite.last_scheduled_run_at < occ))
                .values(last_scheduled_run_at=occ))
            await session.commit()
            return res.rowcount == 1

    async def _send_report_if_due(self, summary: dict) -> None:
        occ = await self.report_due(now_utc())
        if occ is None:
            return
        await locks.ensure_task_row(self.sf, REPORT_TASK)
        attempts = self._report_attempts.get(occ, 0) + 1
        self._report_attempts = {occ: attempts}
        async with self.sf() as session:
            await session.execute(update(ScheduledTask).where(ScheduledTask.name == REPORT_TASK).values(
                last_started_at=now_utc()))
            await session.commit()
        ok = await self.report.send_daily()
        summary["report_sent"] = ok
        # The occurrence is marked done after a success, or after MAX_REPORT_ATTEMPTS failures
        # (later scheduler calls retry until then).
        done = ok or attempts >= MAX_REPORT_ATTEMPTS
        values = dict(last_completed_at=now_utc(),
                      last_status="sent" if ok else f"failed ({attempts}/{MAX_REPORT_ATTEMPTS})")
        if done:
            values["last_occurrence_at"] = occ
        async with self.sf() as session:
            await session.execute(update(ScheduledTask).where(ScheduledTask.name == REPORT_TASK).values(**values))
            await session.commit()

    # ---- the cycle -----------------------------------------------------------------
    async def run_cycle(self, trigger: str, run_id: str) -> dict:
        owner = f"{locks.INSTANCE_ID}-{run_id}"
        if not await locks.try_acquire(self.sf, CYCLE_LOCK, LEASE_TTL, owner):
            return {"status": "already_running"}
        lost = asyncio.Event()
        keeper = asyncio.create_task(self._keep_lease(owner, lost))
        started = now_utc()
        summary = {"status": "completed", "run_id": run_id, "websites_due": 0, "tests_succeeded": 0,
                   "tests_failed": 0, "report_sent": None, "errors": []}
        try:
            async with self.sf() as session:
                session.add(TaskRun(run_id=run_id, task="scheduled_checks", trigger=trigger, status="running",
                                    started_at=started))
                await session.commit()
            due = await self.due_websites(started)
            summary["websites_due"] = len(due)
            sem = asyncio.Semaphore(get_settings().pagespeed_concurrency)
            processed = 0
            flush_lock = asyncio.Lock()

            async def handle(website_id: int, occ: datetime) -> None:
                nonlocal processed
                async with sem:
                    if lost.is_set():
                        return
                    # Claimed before testing (at-most-once): a crash mid-test skips this occurrence
                    # rather than risking a duplicate run; the next occurrence runs normally.
                    if not await self._claim(website_id, occ):
                        return
                    try:
                        out = await self.monitoring.test_website(website_id, ["desktop", "mobile"], "scheduled",
                                                                 run_id=run_id, sync_excel=False)
                        summary["tests_succeeded"] += out.succeeded
                        summary["tests_failed"] += out.failed
                    except WebsiteNotFound:
                        return
                    processed += 1
                    if processed % EXCEL_FLUSH_EVERY == 0:
                        async with flush_lock:
                            await self._sync_excel(summary)

            results = await asyncio.gather(*(handle(wid, occ) for wid, occ in due), return_exceptions=True)
            for (wid, _), res in zip(due, results):
                if isinstance(res, BaseException):
                    log.error("Scheduled test failed for website %s: %r", wid, res)
                    summary["errors"].append(f"website {wid}: {type(res).__name__}: {res}")
            if due:
                await self._sync_excel(summary)
            if lost.is_set():
                summary["status"] = "failed"
                summary["errors"].append("Scheduler lease lost; remaining websites run on the next call")
            else:
                await self._send_report_if_due(summary)
                await self._purge_reports_daily()
                await self._remember_if_finished()
        except Exception as exc:  # noqa: BLE001
            log.exception("Scheduled cycle %s failed", run_id)
            summary["status"] = "failed"
            summary["errors"].append(f"{type(exc).__name__}: {exc}")
        finally:
            keeper.cancel()
            try:
                await locks.release(self.sf, CYCLE_LOCK, owner)
            except Exception:  # noqa: BLE001 - the lease expires on its own
                log.exception("Could not release scheduler lease")
            parts = list(summary["errors"])
            if summary["report_sent"] is not None:
                parts.append("Daily report sent" if summary["report_sent"] else "Daily report FAILED (see Email Logs)")
            try:
                async with self.sf() as session:
                    await session.execute(update(TaskRun).where(TaskRun.run_id == run_id).values(
                        status=summary["status"], completed_at=now_utc(), websites_due=summary["websites_due"],
                        tests_succeeded=summary["tests_succeeded"], tests_failed=summary["tests_failed"],
                        message="; ".join(parts)[:4000] or None))
                    await session.commit()
            except Exception:  # noqa: BLE001
                log.exception("Could not record scheduler run %s", run_id)
        log.info("Scheduled cycle %s: %s", run_id, summary)
        return summary

    async def _purge_reports_daily(self) -> None:
        reports = self.monitoring.reports
        if reports is None:
            return
        try:
            await locks.ensure_task_row(self.sf, PURGE_TASK)
            async with self.sf() as session:
                row = await session.scalar(select(ScheduledTask).where(ScheduledTask.name == PURGE_TASK))
                if row.last_completed_at and now_utc() - row.last_completed_at < timedelta(hours=23):
                    return
            removed = await reports.purge()
            async with self.sf() as session:
                await session.execute(update(ScheduledTask).where(ScheduledTask.name == PURGE_TASK).values(
                    last_completed_at=now_utc(), last_status="ok", last_message=f"Removed {removed} report(s)"))
                await session.commit()
        except Exception:  # noqa: BLE001 - housekeeping only
            log.exception("Report purge failed")

    async def _remember_if_finished(self) -> None:
        """Mark the current run as finished in memory once every page is tested and the
        report is sent (or given up), so the following idle ticks skip the database."""
        now = now_utc()
        occ = await self._occurrence(now)
        if occ is None:
            return
        if not await self.due_websites(now) and await self.report_due(now) is None:
            self._done_occurrence = occ

    async def abort_stale_runs(self) -> int:
        """At startup: runs left 'running' by a previous container can never finish."""
        if await self.is_running():
            return 0
        async with self.sf() as session:
            res = await session.execute(update(TaskRun).where(TaskRun.status == "running").values(
                status="aborted", completed_at=now_utc(),
                message="Interrupted by an application restart; unfinished websites run on the next call"))
            await session.commit()
            return res.rowcount

    async def _sync_excel(self, summary: dict) -> None:
        try:
            await self.excel.sync()
        except Exception as exc:  # noqa: BLE001 - pending rows are retried on the next sync
            log.error("Excel sync failed during scheduled cycle: %s", exc)
            summary["errors"].append(f"Excel: {exc}")

    # ---- optional in-process loop ------------------------------------------------
    async def internal_loop(self, interval: int) -> None:
        await asyncio.sleep(30)  # let startup finish
        while True:
            try:
                await self.trigger("internal", wait=True)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("Internal scheduler tick failed")
            await asyncio.sleep(interval)
