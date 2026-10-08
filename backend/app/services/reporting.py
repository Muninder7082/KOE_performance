"""Shared read-side helpers: status rules, latest results, summaries."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import MonitoredWebsite, PerformanceResult

GOOD, ATTENTION, FAILED, PENDING = "GOOD", "ATTENTION", "FAILED", "PENDING"


def result_status(r: PerformanceResult | None) -> str:
    if r is None:
        return PENDING
    if r.status != "success" or r.performance_score is None:
        return FAILED
    return GOOD if r.performance_score >= r.threshold else ATTENTION


def combined_status(desktop: PerformanceResult | None, mobile: PerformanceResult | None,
                    threshold: int | None = None) -> str:
    statuses = []
    for r in (desktop, mobile):
        if r is None:
            continue
        if r.status != "success" or r.performance_score is None:
            statuses.append(FAILED)
        else:
            t = threshold if threshold is not None else r.threshold
            statuses.append(GOOD if r.performance_score >= t else ATTENTION)
    if not statuses:
        return PENDING
    if FAILED in statuses:
        return FAILED
    if ATTENTION in statuses:
        return ATTENTION
    return GOOD


async def latest_results(session: AsyncSession, website_ids: list[int] | None = None
                         ) -> dict[int, dict[str, PerformanceResult]]:
    """Latest result per (website, strategy) using a window function."""
    rn = func.row_number().over(
        partition_by=(PerformanceResult.website_id, PerformanceResult.strategy),
        order_by=(PerformanceResult.tested_at.desc(), PerformanceResult.id.desc()),
    ).label("rn")
    inner = select(PerformanceResult.id, rn).where(PerformanceResult.website_id.is_not(None))
    if website_ids is not None:
        if not website_ids:
            return {}
        inner = inner.where(PerformanceResult.website_id.in_(website_ids))
    sub = inner.subquery()
    rows = (await session.scalars(
        select(PerformanceResult).join(sub, sub.c.id == PerformanceResult.id).where(sub.c.rn == 1)
    )).all()
    out: dict[int, dict[str, PerformanceResult]] = defaultdict(dict)
    for r in rows:
        out[r.website_id][r.strategy] = r  # type: ignore[index]
    return out


def local_day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    return start, start + timedelta(days=1)


@dataclass
class Overview:
    total_websites: int = 0
    active_websites: int = 0
    tests_today: int = 0
    successful_today: int = 0
    failed_today: int = 0
    avg_desktop: float | None = None
    avg_mobile: float | None = None
    attention: int = 0
    failed_websites: int = 0
    rows: list[dict] = field(default_factory=list)


async def overview(session: AsyncSession, tz: ZoneInfo, now: datetime) -> Overview:
    websites = (await session.scalars(select(MonitoredWebsite).order_by(MonitoredWebsite.name))).all()
    latest = await latest_results(session, [w.id for w in websites])
    start, end = local_day_bounds(now.astimezone(tz).date(), tz)
    counts = dict((await session.execute(
        select(PerformanceResult.status, func.count())
        .where(PerformanceResult.tested_at >= start, PerformanceResult.tested_at < end)
        .group_by(PerformanceResult.status)
    )).all())
    ov = Overview(
        total_websites=len(websites),
        active_websites=sum(1 for w in websites if w.is_active),
        successful_today=int(counts.get("success", 0)),
        failed_today=int(counts.get("failed", 0)),
    )
    ov.tests_today = ov.successful_today + ov.failed_today
    d_scores, m_scores = [], []
    for w in websites:
        lr = latest.get(w.id, {})
        d, m = lr.get("desktop"), lr.get("mobile")
        status = combined_status(d, m, w.threshold)
        if w.is_active:
            if d and d.status == "success" and d.performance_score is not None:
                d_scores.append(d.performance_score)
            if m and m.status == "success" and m.performance_score is not None:
                m_scores.append(m.performance_score)
            if status == ATTENTION:
                ov.attention += 1
            elif status == FAILED:
                ov.failed_websites += 1
        checked = [r.tested_at for r in (d, m) if r]
        ov.rows.append({
            "website": w, "desktop": d, "mobile": m, "status": status,
            "last_checked": max(checked) if checked else None,
        })
    ov.avg_desktop = round(sum(d_scores) / len(d_scores), 1) if d_scores else None
    ov.avg_mobile = round(sum(m_scores) / len(m_scores), 1) if m_scores else None
    return ov
