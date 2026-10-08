from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..clock import now_utc
from ..container import get_container
from ..db import get_session
from ..models import User
from ..ratelimit import limiter
from ..repositories import AlertRepository, ResultRepository, WebsiteRepository, paginate
from ..schemas import AlertOut, TestRequest, WebsiteCreate, WebsiteOut, WebsiteUpdate
from ..security import current_user, require_admin
from ..services import reporting
from ..services.jobs import JobRejected
from ..services.websites import WebsiteError, WebsiteService, result_out, schedule_info, website_out
from .common import Paging, app_tz, day_range

router = APIRouter(prefix="/api/websites", tags=["websites"])


def _err(exc: WebsiteError) -> HTTPException:
    return HTTPException(exc.status, exc.message)


@router.get("")
async def list_websites(search: str | None = Query(None, max_length=200), status: str | None = Query(None),
                        active: bool | None = None, paging: Paging = Depends(),
                        user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    repo = WebsiteRepository(session)
    q = repo.search_query(search, active)
    monitoring = get_container().monitoring
    if status:  # status is derived from latest results, so filter in Python
        sites = list((await session.scalars(q)).all())
        latest = await reporting.latest_results(session, [w.id for w in sites])
        sched = await schedule_info(session)
        outs = [website_out(w, latest.get(w.id), monitoring.is_busy(w.id), sched) for w in sites]
        outs = [o for o in outs if o.status == status.upper()]
        total = len(outs)
        start = (paging.page - 1) * paging.page_size
        items = outs[start:start + paging.page_size]
    else:
        sites, total = await paginate(session, q, paging.page, paging.page_size)
        latest = await reporting.latest_results(session, [w.id for w in sites])
        sched = await schedule_info(session)
        items = [website_out(w, latest.get(w.id), monitoring.is_busy(w.id), sched) for w in sites]
    return {"items": items, "total": total, "page": paging.page, "page_size": paging.page_size}


@router.post("", status_code=201, response_model=WebsiteOut)
async def create_website(body: WebsiteCreate, user: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    try:
        w = await WebsiteService(session).create(body)
    except WebsiteError as exc:
        raise _err(exc) from None
    return website_out(w, {}, sched=await schedule_info(session))


@router.get("/{website_id}", response_model=WebsiteOut)
async def get_website(website_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    w = await WebsiteRepository(session).get(website_id)
    if w is None:
        raise HTTPException(404, "Website not found")
    latest = await reporting.latest_results(session, [w.id])
    return website_out(w, latest.get(w.id), get_container().monitoring.is_busy(w.id), await schedule_info(session))


@router.patch("/{website_id}", response_model=WebsiteOut)
async def update_website(website_id: int, body: WebsiteUpdate, user: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    try:
        w = await WebsiteService(session).update(website_id, body)
    except WebsiteError as exc:
        raise _err(exc) from None
    latest = await reporting.latest_results(session, [w.id])
    return website_out(w, latest.get(w.id), sched=await schedule_info(session))


@router.delete("/{website_id}")
async def delete_website(website_id: int, user: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    try:
        await WebsiteService(session).delete(website_id)
    except WebsiteError as exc:
        raise _err(exc) from None
    return {"ok": True}


@router.post("/{website_id}/test", status_code=202)
async def run_test(website_id: int, body: TestRequest, user: User = Depends(require_admin),
                   session: AsyncSession = Depends(get_session)):
    limiter.hit(f"manual-test:{user.id}", 20, 600)
    if await WebsiteRepository(session).get(website_id) is None:
        raise HTTPException(404, "Website not found")
    try:
        job = await get_container().jobs.start(website_id, list(body.strategies), user.email)
    except JobRejected as exc:
        raise HTTPException(exc.status, exc.message) from None
    return job.to_dict()


@router.get("/{website_id}/history")
async def history(website_id: int, days: int | None = Query(30, ge=1, le=3650), date_from: date | None = None,
                  date_to: date | None = None, user: User = Depends(current_user),
                  session: AsyncSession = Depends(get_session)):
    if await WebsiteRepository(session).get(website_id) is None:
        raise HTTPException(404, "Website not found")
    tz = await app_tz(session)
    if date_from or date_to:
        start, end = day_range(date_from, date_to, tz)
        start = start or datetime(2000, 1, 1, tzinfo=tz)
        end = end or now_utc() + timedelta(minutes=1)
    else:
        end = now_utc() + timedelta(minutes=1)
        start = end - timedelta(days=days or 30)
    rows = await ResultRepository(session).history(website_id, start, end)
    return {"items": [result_out(r) for r in rows], "from": start, "to": end}


@router.get("/{website_id}/results")
async def website_results(website_id: int, paging: Paging = Depends(), user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    q = ResultRepository(session).query(website_id=website_id)
    rows, total = await paginate(session, q, paging.page, paging.page_size)
    return {"items": [result_out(r) for r in rows], "total": total, "page": paging.page,
            "page_size": paging.page_size}


@router.get("/{website_id}/alerts")
async def website_alerts(website_id: int, paging: Paging = Depends(), user: User = Depends(current_user),
                         session: AsyncSession = Depends(get_session)):
    q = AlertRepository(session).query(website_id=website_id)
    rows, total = await paginate(session, q, paging.page, paging.page_size)
    return {"items": [AlertOut.model_validate(a) for a in rows], "total": total, "page": paging.page,
            "page_size": paging.page_size}
