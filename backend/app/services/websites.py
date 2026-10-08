"""Website management (create / update / delete) and API presentation."""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..clock import now_utc
from ..config import get_settings
from ..models import AlertEvent, MonitoredWebsite, PerformanceResult
from ..repositories import WebsiteRepository
from ..schemas import LatestScores, ResultOut, WebsiteCreate, WebsiteOut, WebsiteUpdate
from ..urls import InvalidUrl, validate_and_normalize
from . import global_schedule, reporting, settings_service
from .global_schedule import GlobalSchedule

SCHEDULE_FIELDS = {"is_active"}


class WebsiteError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def result_out(r: PerformanceResult | None) -> ResultOut | None:
    if r is None:
        return None
    out = ResultOut.model_validate(r)
    out.health = reporting.result_status(r)
    out.has_report = bool(r.report_key)
    return out


async def schedule_info(session: AsyncSession) -> GlobalSchedule:
    app = await settings_service.load(session)
    return global_schedule.compute(app, now_utc())


def website_out(w: MonitoredWebsite, latest: dict[str, PerformanceResult] | None, busy: bool = False,
                sched: GlobalSchedule | None = None) -> WebsiteOut:
    latest = latest or {}
    out = WebsiteOut.model_validate(w)
    if sched is not None:
        out.schedule_description = sched.description if w.is_active else "Monitoring disabled"
        out.next_run_at = sched.next_run_at if w.is_active else None
    d, m = latest.get("desktop"), latest.get("mobile")
    out.latest = LatestScores(desktop=result_out(d), mobile=result_out(m))
    out.status = reporting.combined_status(d, m, w.threshold)
    out.test_running = busy
    return out


class WebsiteService:
    def __init__(self, session: AsyncSession):
        self.s = session
        self.repo = WebsiteRepository(session)

    async def _check_url(self, url: str, exclude_id: int | None = None) -> tuple[str, str]:
        try:
            clean, key = validate_and_normalize(url)
        except InvalidUrl as exc:
            raise WebsiteError(422, str(exc)) from exc
        existing = await self.repo.by_normalized(key)
        if existing is not None and existing.id != exclude_id:
            raise WebsiteError(409, f"This URL is already monitored as \"{existing.name}\".")
        return clean, key

    async def create(self, data: WebsiteCreate) -> MonitoredWebsite:
        app = await settings_service.load(self.s)
        clean, key = await self._check_url(data.url)
        frequency = data.frequency or app.default_frequency
        now = now_utc()
        w = MonitoredWebsite(
            name=data.name, url=clean, url_normalized=key,
            is_active=True if data.is_active is None else data.is_active,
            frequency=frequency, monitor_time=data.monitor_time or app.default_monitor_time,
            day_of_week=(data.day_of_week if data.day_of_week is not None else 0) if frequency == "weekly" else None,
            timezone=data.timezone or app.timezone or get_settings().app_timezone,
            threshold=data.threshold or app.default_threshold, notes=data.notes or None,
            created_at=now, updated_at=now, schedule_updated_at=now,
        )
        self.repo.add(w)
        try:
            await self.s.commit()
        except IntegrityError as exc:
            await self.s.rollback()
            raise WebsiteError(409, "This URL is already monitored.") from exc
        await self.s.refresh(w)
        return w

    async def update(self, website_id: int, data: WebsiteUpdate) -> MonitoredWebsite:
        w = await self.repo.get(website_id)
        if w is None:
            raise WebsiteError(404, "Website not found")
        changes = data.model_dump(exclude_unset=True)
        if "url" in changes and changes["url"] is not None:
            w.url, w.url_normalized = await self._check_url(changes.pop("url"), exclude_id=w.id)
        schedule_changed = False
        for field in ("name", "is_active", "threshold", "notes"):
            if field not in changes:
                continue
            value = changes[field]
            if value is None and field not in ("notes", "day_of_week"):
                continue
            if field == "notes":
                value = value or None
            if getattr(w, field) != value:
                setattr(w, field, value)
                schedule_changed |= field in SCHEDULE_FIELDS
        if w.frequency == "weekly" and w.day_of_week is None:
            w.day_of_week = 0
        if w.frequency != "weekly":
            w.day_of_week = None
        now = now_utc()
        w.updated_at = now
        if schedule_changed:
            # New schedule starts counting from now (no surprise immediate run).
            w.schedule_updated_at = now
        try:
            await self.s.commit()
        except IntegrityError as exc:
            await self.s.rollback()
            raise WebsiteError(409, "This URL is already monitored.") from exc
        await self.s.refresh(w)
        return w

    async def delete(self, website_id: int) -> None:
        w = await self.repo.get(website_id)
        if w is None:
            raise WebsiteError(404, "Website not found")
        # Open alerts can never recover once the website is gone: close them.
        await self.s.execute(update(AlertEvent).where(AlertEvent.website_id == w.id, AlertEvent.state == "open")
                             .values(state="closed", recovered_at=now_utc()))
        # History rows keep their name/URL snapshot; website_id becomes NULL (ON DELETE SET NULL).
        await self.repo.delete(w)
        await self.s.commit()
