"""Manual test jobs with progress stages (polled by the dashboard).

Protection against accidental repeated API calls:
  * only one running job per website (409), and
  * a cooldown after the last manual test of that website (429).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..clock import now_utc
from ..config import get_settings
from ..models import PerformanceResult
from .monitoring import PerformanceMonitoringService

log = logging.getLogger(__name__)


class JobRejected(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Job:
    id: str
    website_id: int
    strategies: list[str]
    requested_by: str
    status: str = "queued"  # queued | running | completed | failed
    stage: str = "Testing..."
    stages: list[str] = field(default_factory=lambda: ["Testing..."])
    result_ids: list[int] = field(default_factory=list)
    succeeded: int = 0
    failed: int = 0
    error: str | None = None
    warning: str | None = None
    created_at: datetime = field(default_factory=now_utc)
    finished_at: datetime | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["finished_at"] = self.finished_at.isoformat() if self.finished_at else None
        return d


class JobManager:
    def __init__(self, sf: async_sessionmaker[AsyncSession], monitoring: PerformanceMonitoringService):
        self.sf = sf
        self.monitoring = monitoring
        self.jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()

    def _cleanup(self) -> None:
        cutoff = now_utc() - timedelta(hours=2)
        for jid in [j.id for j in self.jobs.values() if j.finished_at and j.finished_at < cutoff]:
            self.jobs.pop(jid, None)

    def active_for(self, website_id: int) -> Job | None:
        for j in self.jobs.values():
            if j.website_id == website_id and j.status in ("queued", "running"):
                return j
        return None

    async def start(self, website_id: int, strategies: list[str], user_email: str) -> Job:
        self._cleanup()
        if self.active_for(website_id) or self.monitoring.is_busy(website_id):
            raise JobRejected(409, "A test for this website is already running.")
        cooldown = get_settings().manual_test_cooldown_seconds
        if cooldown:
            async with self.sf() as session:
                last = await session.scalar(
                    select(PerformanceResult.completed_at)
                    .where(PerformanceResult.website_id == website_id, PerformanceResult.trigger == "manual",
                           PerformanceResult.strategy.in_(strategies))
                    .order_by(PerformanceResult.completed_at.desc()).limit(1))
            if last is not None:
                wait = cooldown - (now_utc() - last).total_seconds()
                if wait > 0:
                    raise JobRejected(429, f"This website was tested moments ago. Please wait {int(wait) + 1}s "
                                           "before running another manual test.")
        job = Job(id=uuid.uuid4().hex, website_id=website_id, strategies=strategies, requested_by=user_email)
        self.jobs[job.id] = job
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run(self, job: Job) -> None:
        def progress(stage: str) -> None:
            job.stage = stage
            job.stages.append(stage)

        job.status = "running"
        try:
            out = await self.monitoring.test_website(job.website_id, job.strategies, "manual",
                                                     run_id=f"manual-{job.id[:12]}", progress=progress)
            job.result_ids = out.result_ids
            job.succeeded, job.failed = out.succeeded, out.failed
            if out.excel_error:
                job.warning = f"Results saved, but the Excel update failed and will be retried: {out.excel_error}"
            job.status = "completed"
            progress("Completed.")
        except Exception as exc:  # noqa: BLE001
            log.exception("Manual job %s failed", job.id)
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
            progress("Failed.")
        finally:
            job.finished_at = now_utc()

    async def shutdown(self) -> None:
        for t in list(self._tasks):
            t.cancel()
