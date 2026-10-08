"""Repositories — all query construction for the API read/write paths.

SQLAlchemy expressions use bound parameters everywhere (no string SQL), which
protects against SQL injection. LIKE patterns escape user wildcards.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AlertEvent, EmailLog, MonitoredWebsite, PerformanceResult, TaskRun, User


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def paginate(session: AsyncSession, q: Select, page: int, page_size: int) -> tuple[list, int]:
    total = await session.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
    rows = (await session.scalars(q.limit(page_size).offset((page - 1) * page_size))).all()
    return list(rows), int(total or 0)


class WebsiteRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    async def get(self, website_id: int) -> MonitoredWebsite | None:
        return await self.s.get(MonitoredWebsite, website_id)

    async def by_normalized(self, key: str) -> MonitoredWebsite | None:
        return await self.s.scalar(select(MonitoredWebsite).where(MonitoredWebsite.url_normalized == key))

    async def all(self) -> list[MonitoredWebsite]:
        return list((await self.s.scalars(select(MonitoredWebsite).order_by(MonitoredWebsite.name))).all())

    def search_query(self, search: str | None, active: bool | None) -> Select:
        q = select(MonitoredWebsite)
        if search:
            pat = _like(search.strip())
            q = q.where(or_(MonitoredWebsite.name.ilike(pat, escape="\\"), MonitoredWebsite.url.ilike(pat, escape="\\")))
        if active is not None:
            q = q.where(MonitoredWebsite.is_active.is_(active))
        return q.order_by(MonitoredWebsite.name, MonitoredWebsite.id)

    def add(self, w: MonitoredWebsite) -> None:
        self.s.add(w)

    async def delete(self, w: MonitoredWebsite) -> None:
        await self.s.delete(w)


class ResultRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    def query(self, *, website_id: int | None = None, strategy: str | None = None, status: str | None = None,
              date_from: datetime | None = None, date_to: datetime | None = None,
              trigger: str | None = None, search: str | None = None) -> Select:
        q = select(PerformanceResult)
        if website_id is not None:
            q = q.where(PerformanceResult.website_id == website_id)
        if strategy:
            q = q.where(PerformanceResult.strategy == strategy)
        if status == "attention":
            q = q.where(PerformanceResult.status == "success",
                        PerformanceResult.performance_score < PerformanceResult.threshold)
        elif status == "good":
            q = q.where(PerformanceResult.status == "success",
                        PerformanceResult.performance_score >= PerformanceResult.threshold)
        elif status in ("success", "failed"):
            q = q.where(PerformanceResult.status == status)
        if trigger:
            q = q.where(PerformanceResult.trigger == trigger)
        if date_from:
            q = q.where(PerformanceResult.tested_at >= date_from)
        if date_to:
            q = q.where(PerformanceResult.tested_at < date_to)
        if search:
            pat = _like(search.strip())
            q = q.where(or_(PerformanceResult.website_name.ilike(pat, escape="\\"),
                            PerformanceResult.requested_url.ilike(pat, escape="\\")))
        return q.order_by(PerformanceResult.tested_at.desc(), PerformanceResult.id.desc())

    async def history(self, website_id: int, date_from: datetime, date_to: datetime, limit: int = 5000
                      ) -> list[PerformanceResult]:
        q = (select(PerformanceResult)
             .where(PerformanceResult.website_id == website_id, PerformanceResult.tested_at >= date_from,
                    PerformanceResult.tested_at < date_to)
             .order_by(PerformanceResult.tested_at).limit(limit))
        return list((await self.s.scalars(q)).all())


class AlertRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    def query(self, website_id: int | None = None, state: str | None = None) -> Select:
        q = select(AlertEvent)
        if website_id is not None:
            q = q.where(AlertEvent.website_id == website_id)
        if state:
            q = q.where(AlertEvent.state == state)
        return q.order_by(AlertEvent.last_detected_at.desc(), AlertEvent.id.desc())


class EmailLogRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    def query(self, email_type: str | None, status: str | None, date_from: datetime | None,
              date_to: datetime | None, search: str | None) -> Select:
        q = select(EmailLog)
        if email_type:
            q = q.where(EmailLog.email_type == email_type)
        if status:
            q = q.where(EmailLog.status == status)
        if date_from:
            q = q.where(EmailLog.created_at >= date_from)
        if date_to:
            q = q.where(EmailLog.created_at < date_to)
        if search:
            pat = _like(search.strip())
            q = q.where(or_(EmailLog.recipients.ilike(pat, escape="\\"), EmailLog.subject.ilike(pat, escape="\\"),
                            EmailLog.website_name.ilike(pat, escape="\\")))
        return q.order_by(EmailLog.created_at.desc(), EmailLog.id.desc())


class TaskRunRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    def query(self) -> Select:
        return select(TaskRun).order_by(TaskRun.started_at.desc(), TaskRun.id.desc())


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    async def by_email(self, email: str) -> User | None:
        return await self.s.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))

    async def all(self) -> list[User]:
        return list((await self.s.scalars(select(User).order_by(User.email))).all())

    async def count(self) -> int:
        return int(await self.s.scalar(select(func.count(User.id))) or 0)

    async def admin_count(self) -> int:
        return int(await self.s.scalar(
            select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))) or 0)
