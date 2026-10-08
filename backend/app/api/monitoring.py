"""Dashboard, jobs, logs (monitoring / email / alerts / scheduler runs)."""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..clock import now_utc
from ..container import get_container
from ..db import get_session
from ..models import User
from ..repositories import AlertRepository, EmailLogRepository, ResultRepository, TaskRunRepository, paginate
from ..schemas import AlertOut, EmailLogOut, TaskRunOut
from ..security import current_user
from ..services import reporting
from ..services.websites import schedule_info, website_out
from .common import Paging, app_tz, day_range

router = APIRouter(prefix="/api", tags=["monitoring"])


@router.get("/dashboard")
async def dashboard(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    tz = await app_tz(session)
    ov = await reporting.overview(session, tz, now_utc())
    monitoring = get_container().monitoring
    sched = await schedule_info(session)
    lowest = None  # weakest latest score among active pages
    for r in ov.rows:
        if not r["website"].is_active:
            continue
        for dev in ("mobile", "desktop"):
            res = r[dev]
            if res is not None and res.status == "success" and res.performance_score is not None:
                if lowest is None or res.performance_score < lowest["score"]:
                    lowest = {"score": res.performance_score, "website_id": r["website"].id,
                              "website_name": r["website"].name, "device": dev,
                              "threshold": r["website"].threshold}
    rows = [website_out(r["website"], {k: v for k, v in (("desktop", r["desktop"]), ("mobile", r["mobile"])) if v},
                        monitoring.is_busy(r["website"].id), sched) for r in ov.rows]
    return {
        "cards": {
            "total_websites": ov.total_websites,
            "active_monitors": ov.active_websites,
            "tests_today": ov.tests_today,
            "avg_desktop": ov.avg_desktop,
            "avg_mobile": ov.avg_mobile,
            "attention": ov.attention,
            "failed_tests_today": ov.failed_today,
            "failing_websites": ov.failed_websites,
            "lowest": lowest,
        },
        "websites": rows,
        "scheduler_running": await get_container().scheduler.is_running(),
        "schedule": {"description": sched.description, "next_run_at": sched.next_run_at},
    }


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, user: User = Depends(current_user)):
    job = get_container().jobs.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found (jobs are kept for 2 hours)")
    return job.to_dict()


@router.get("/results")
async def monitoring_logs(website_id: int | None = None, strategy: str | None = Query(None, pattern="^(desktop|mobile)$"),
                          status: str | None = Query(None, pattern="^(success|failed|good|attention)$"),
                          trigger: str | None = Query(None, pattern="^(manual|scheduled)$"),
                          date_from: date | None = None, date_to: date | None = None,
                          search: str | None = Query(None, max_length=200), paging: Paging = Depends(),
                          user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    from ..services.websites import result_out

    start, end = day_range(date_from, date_to, await app_tz(session))
    q = ResultRepository(session).query(website_id=website_id, strategy=strategy, status=status, date_from=start,
                                        date_to=end, trigger=trigger, search=search)
    rows, total = await paginate(session, q, paging.page, paging.page_size)
    return {"items": [result_out(r) for r in rows], "total": total, "page": paging.page, "page_size": paging.page_size}


async def _siblings(session: AsyncSession, r) -> dict:
    """The other device's result from the same run (manual "Both" or scheduled), for the tabs."""
    from datetime import timedelta

    from sqlalchemy import select

    from ..models import PerformanceResult

    other = "desktop" if r.strategy == "mobile" else "mobile"
    if r.website_id is None:
        return {other: None}
    q = select(PerformanceResult).where(PerformanceResult.website_id == r.website_id,
                                        PerformanceResult.strategy == other)
    if r.run_id:
        q = q.where(PerformanceResult.run_id == r.run_id)
    else:
        q = q.where(PerformanceResult.tested_at.between(r.tested_at - timedelta(minutes=15),
                                                        r.tested_at + timedelta(minutes=15)))
    match = await session.scalar(q.order_by(PerformanceResult.id.desc()).limit(1))
    return {other: match}


@router.get("/results/{result_id}/report", response_class=HTMLResponse)
async def stored_report(result_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    """The exact PageSpeed/Lighthouse report captured by this test (no new analysis)."""
    from ..models import PerformanceResult
    from ..services import lighthouse_reports

    r = await session.get(PerformanceResult, result_id)
    if r is None:
        raise HTTPException(404, "Result not found")
    report = None
    try:
        report = await get_container().reports.load(r)
    except Exception:  # noqa: BLE001 - shown as "not available"
        report = None
    if report is None:
        return HTMLResponse(lighthouse_reports.missing_html(r), status_code=404)
    html = lighthouse_reports.render_html(r, report, await app_tz(session), await _siblings(session, r))
    return HTMLResponse(html, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/results/{result_id}/viewer-url")
async def google_viewer_url(result_id: int, user: User = Depends(current_user),
                            session: AsyncSession = Depends(get_session)):
    """URL that opens the stored report directly on Google's Lighthouse Viewer."""
    from ..models import PerformanceResult
    from ..services import lighthouse_reports

    r = await session.get(PerformanceResult, result_id)
    if r is None:
        raise HTTPException(404, "Result not found")
    try:
        report = await get_container().reports.load(r)
    except Exception:  # noqa: BLE001
        report = None
    if report is None:
        raise HTTPException(404, "No saved report for this test")
    return {"url": lighthouse_reports.viewer_url(report)}


@router.get("/results/{result_id}/viewer")
async def open_in_google_viewer(result_id: int, user: User = Depends(current_user),
                                session: AsyncSession = Depends(get_session)):
    """Open the stored report on Google's Lighthouse Viewer (googlechrome.github.io).

    The report travels in the URL fragment (often 100-300 KB), too long for a redirect
    header, so a tiny page hands it to the browser via a JSON data block + external script.
    """
    from html import escape as _esc

    from ..models import PerformanceResult
    from ..services import lighthouse_reports

    r = await session.get(PerformanceResult, result_id)
    if r is None:
        raise HTTPException(404, "Result not found")
    try:
        report = await get_container().reports.load(r)
    except Exception:  # noqa: BLE001
        report = None
    if report is None:
        return HTMLResponse(lighthouse_reports.missing_html(r), status_code=404)
    url = lighthouse_reports.viewer_url(report)
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
            '<title>Opening Lighthouse Viewer…</title></head><body style="font-family:Segoe UI,Arial,sans-serif;padding:40px">'
            '<p>Opening the saved report on Google Lighthouse Viewer…</p>'
            f'<script type="application/json" id="viewer-url">{json.dumps(url)}</script>'
            '<script src="/lighthouse-assets/open-viewer.js"></script></body></html>')
    return HTMLResponse(page, headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"})


@router.get("/email-logs")
async def email_logs(email_type: str | None = Query(None, max_length=40),
                     status: str | None = Query(None, pattern="^(pending|sent|failed)$"),
                     date_from: date | None = None, date_to: date | None = None,
                     search: str | None = Query(None, max_length=200), paging: Paging = Depends(),
                     user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    start, end = day_range(date_from, date_to, await app_tz(session))
    q = EmailLogRepository(session).query(email_type, status, start, end, search)
    rows, total = await paginate(session, q, paging.page, paging.page_size)
    return {"items": [EmailLogOut.model_validate(r) for r in rows], "total": total, "page": paging.page,
            "page_size": paging.page_size}


@router.get("/alerts")
async def alerts(state: str | None = Query(None, pattern="^(open|recovered|closed)$"), paging: Paging = Depends(),
                 user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    q = AlertRepository(session).query(state=state)
    rows, total = await paginate(session, q, paging.page, paging.page_size)
    return {"items": [AlertOut.model_validate(a) for a in rows], "total": total, "page": paging.page,
            "page_size": paging.page_size}


@router.get("/task-runs")
async def task_runs(paging: Paging = Depends(), user: User = Depends(current_user),
                    session: AsyncSession = Depends(get_session)):
    rows, total = await paginate(session, TaskRunRepository(session).query(), paging.page, paging.page_size)
    return {"items": [TaskRunOut.model_validate(r) for r in rows], "total": total, "page": paging.page,
            "page_size": paging.page_size}
