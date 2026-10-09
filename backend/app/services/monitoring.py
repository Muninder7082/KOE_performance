"""PerformanceMonitoringService — run tests for one website and persist them.

Each strategy produces exactly one PerformanceResult row (success OR failed),
so failures are visible in the dashboard, the logs and the Excel workbook.
A per-website lock prevents a manual test and a scheduled test of the same
website from running at the same time.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..clock import now_utc
from ..models import MonitoredWebsite, PerformanceResult
from .alerts import AlertService
from .excel import ExcelReportService
from .lighthouse_reports import LighthouseReportService
from .pagespeed import PageSpeedError, PageSpeedService

log = logging.getLogger(__name__)

Progress = Callable[[str], Awaitable[None] | None]


@dataclass
class WebsiteRunOutcome:
    website_id: int
    result_ids: list[int]
    succeeded: int
    failed: int
    excel_error: str | None = None


class WebsiteNotFound(Exception):
    pass


class PerformanceMonitoringService:
    def __init__(self, sf: async_sessionmaker[AsyncSession], pagespeed: PageSpeedService,
                 excel: ExcelReportService, alerts: AlertService, reports: LighthouseReportService | None = None):
        self.sf = sf
        self.reports = reports
        self.pagespeed = pagespeed
        self.excel = excel
        self.alerts = alerts
        self._locks: dict[int, asyncio.Lock] = {}

    def lock_for(self, website_id: int) -> asyncio.Lock:
        lock = self._locks.get(website_id)
        if lock is None:
            lock = self._locks[website_id] = asyncio.Lock()
        return lock

    def is_busy(self, website_id: int) -> bool:
        lock = self._locks.get(website_id)
        return bool(lock and lock.locked())

    async def _progress(self, cb: Progress | None, stage: str) -> None:
        if cb is None:
            return
        res = cb(stage)
        if asyncio.iscoroutine(res):
            await res

    async def test_website(self, website_id: int, strategies: list[str], trigger: str, *,
                           run_id: str | None = None, progress: Progress | None = None,
                           sync_excel: bool = True, collect_alerts: list | None = None) -> WebsiteRunOutcome:
        """collect_alerts: a scheduled run passes a list and sends ONE e-mail for all pages at the end;
        a manual test (None) e-mails this page's alerts right away (Desktop + Mobile together)."""
        async with self.lock_for(website_id):
            async with self.sf() as session:
                w = await session.get(MonitoredWebsite, website_id)
                if w is None:
                    raise WebsiteNotFound(website_id)
                snap = {"id": w.id, "name": w.name, "url": w.url, "threshold": w.threshold}
            await self._progress(progress, "Fetching PageSpeed data...")
            ids = await asyncio.gather(*(self._run_one(snap, s, trigger, run_id) for s in strategies))
            await self._progress(progress, "Processing results...")
            async with self.sf() as session:
                w = await session.get(MonitoredWebsite, website_id)
                if w is not None:
                    w.last_checked_at = now_utc()
                    await session.commit()
                rows = [await session.get(PerformanceResult, i) for i in ids]
            ok = sum(1 for r in rows if r and r.status == "success")
            notices = []
            for rid in ids:
                try:
                    notices.append(await self.alerts.process(rid))
                except Exception:  # noqa: BLE001 - alerting must never break monitoring
                    log.exception("Alert processing failed for result %s", rid)
            notices = [n for n in notices if n is not None]
            if collect_alerts is not None:
                collect_alerts.extend(notices)
            elif notices:
                try:
                    await self.alerts.notify(notices)
                except Exception:  # noqa: BLE001
                    log.exception("Alert e-mail failed")
            excel_error = None
            if sync_excel:
                await self._progress(progress, "Updating Excel...")
                try:
                    await self.excel.sync()
                except Exception as exc:  # noqa: BLE001 - rows stay pending and are retried next sync
                    excel_error = f"{type(exc).__name__}: {exc}"
                    log.error("Excel update failed: %s", excel_error)
            return WebsiteRunOutcome(website_id, list(ids), ok, len(ids) - ok, excel_error)

    async def _run_one(self, snap: dict, strategy: str, trigger: str, run_id: str | None) -> int:
        started = now_utc()
        fields: dict = {}
        report = None
        try:
            data = await self.pagespeed.run(snap["url"], strategy)
            report = data.pop("_report", None)
            fields = dict(
                status="success", api_status=data.get("api_status"),
                final_url=(data.get("final_url") or None),
                performance_score=data.get("performance_score"),
                accessibility_score=data.get("accessibility_score"),
                best_practices_score=data.get("best_practices_score"),
                seo_score=data.get("seo_score"), fcp_s=data.get("fcp"), lcp_s=data.get("lcp"),
                tbt_ms=data.get("tbt"), cls=data.get("cls"), speed_index_s=data.get("speed_index"),
            )
        except PageSpeedError as exc:
            fields = dict(status="failed", api_status=exc.api_status, error_code=exc.code,
                          error_message=exc.message[:2000])
        except Exception as exc:  # noqa: BLE001
            log.exception("Unexpected error testing %s (%s)", snap["url"], strategy)
            fields = dict(status="failed", api_status="INTERNAL", error_code="internal_error",
                          error_message=f"{type(exc).__name__}: {str(exc)[:500]}")
        completed = now_utc()
        result = PerformanceResult(
            website_id=snap["id"], website_name=snap["name"], requested_url=snap["url"], strategy=strategy,
            trigger=trigger, threshold=snap["threshold"], started_at=started, completed_at=completed,
            duration_ms=int((completed - started).total_seconds() * 1000), tested_at=completed, run_id=run_id,
            **fields,
        )
        async with self.sf() as session:
            session.add(result)
            await session.commit()
            result_id = result.id
        if report and self.reports is not None:
            await self.reports.save(result_id, report)
        return result_id

