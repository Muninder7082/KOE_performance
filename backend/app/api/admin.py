"""Settings, integration tests, Excel and user management."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..container import get_container
from ..db import get_session
from ..models import ScheduledTask, User
from ..ratelimit import limiter
from ..repositories import UserRepository
from ..schemas import SettingsUpdate, TestEmailIn, TestPageSpeedIn, UserCreate, UserOut, UserUpdate
from ..security import current_user, hash_password, require_admin, validate_password_strength
from ..clock import now_utc
from ..services import email_templates, global_schedule, settings_service
from ..services.email_service import TEST_EMAIL, OutgoingEmail
from ..services.pagespeed import PageSpeedError
from ..services.scheduler import REPORT_TASK
from ..urls import InvalidUrl, validate_and_normalize

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/settings")
async def get_app_settings(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    c = get_container()
    env = get_settings()
    app = await settings_service.load(session)
    report_task = await session.scalar(select(ScheduledTask).where(ScheduledTask.name == REPORT_TASK))
    return {
        "settings": app.model_dump(mode="json"),
        "integrations": {
            "pagespeed": {"configured": c.pagespeed.configured, "concurrency": env.pagespeed_concurrency},
            "email": c.email.status(),
            "storage": c.storage.describe(),
            "excel": await c.excel.status(),
            "database": {"engine": "sqlite" if env.is_sqlite else "postgresql"},
            "scheduler": {
                "internal_enabled": env.enable_internal_scheduler,
                "internal_interval_seconds": env.internal_scheduler_interval_seconds,
                "endpoint": "/api/internal/run-scheduled-checks",
                "catchup_hours": env.schedule_catchup_hours,
                "token_configured": bool(env.scheduler_token),
            },
            "schedule": {
                "description": (sch := global_schedule.compute(app, now_utc())).description,
                "next_run_at": sch.next_run_at,
            },
            "daily_report": {
                "last_sent_occurrence": report_task.last_occurrence_at if report_task else None,
                "last_status": report_task.last_status if report_task else None,
            },
        },
    }


@router.put("/settings")
async def update_app_settings(body: SettingsUpdate, user: User = Depends(require_admin),
                              session: AsyncSession = Depends(get_session)):
    try:
        app = await settings_service.update(session, body.model_dump(exclude_unset=True, mode="json"))
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_input=False)) from None
    get_container().scheduler.invalidate()  # new schedule takes effect on the next tick
    return {"settings": app.model_dump(mode="json")}


@router.post("/settings/test-pagespeed")
async def test_pagespeed(body: TestPageSpeedIn, user: User = Depends(require_admin)):
    limiter.hit(f"test-psi:{user.id}", 5, 300)
    url = body.url or "https://www.google.com/"
    try:
        clean, _ = validate_and_normalize(url)
    except InvalidUrl as exc:
        raise HTTPException(422, str(exc)) from None
    try:
        data = await get_container().pagespeed.run(clean, body.strategy)
    except PageSpeedError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message, "api_status": exc.api_status}
    return {"ok": True, "result": data}


@router.post("/settings/test-email")
async def test_email(body: TestEmailIn, user: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session)):
    limiter.hit(f"test-email:{user.id}", 5, 300)
    app = await settings_service.load(session)
    to = [body.to] if body.to else (list(app.report_emails) or [user.email])
    subject, html, text = email_templates.test_email(get_settings().public_base_url)
    ok = await get_container().email.send(OutgoingEmail(TEST_EMAIL, to, subject, html, text))
    return {"ok": ok, "recipients": to}


@router.post("/reports/daily/send")
async def send_daily_report(background: BackgroundTasks, user: User = Depends(require_admin)):
    limiter.hit(f"send-report:{user.id}", 3, 600)
    background.add_task(get_container().report.send_daily)
    return {"ok": True, "message": "Daily report is being generated; check Email Logs in a minute."}


# ---- Excel ------------------------------------------------------------------------
@router.get("/excel/download")
async def download_excel(background: BackgroundTasks, user: User = Depends(current_user)):
    limiter.hit(f"excel-dl:{user.id}", 30, 300)
    c = get_container()
    tmpdir = tempfile.mkdtemp(prefix="xlsx-")
    path = Path(tmpdir) / get_settings().excel_filename
    try:
        if not await c.excel.fetch_latest(path):
            # First use (or storage reset): build it from the database, then serve it.
            await c.excel.sync()
            if not await c.excel.fetch_latest(path):
                raise HTTPException(404, "Workbook not available yet")
    except HTTPException:
        shutil.rmtree(tmpdir, True)
        raise
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmpdir, True)
        raise HTTPException(503, f"Workbook could not be loaded from storage: {exc}") from None
    background.add_task(shutil.rmtree, tmpdir, True)
    return FileResponse(path, filename=get_settings().excel_filename,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Cache-Control": "no-store"})


@router.post("/excel/sync")
async def sync_excel(user: User = Depends(require_admin)):
    limiter.hit(f"excel-sync:{user.id}", 6, 300)
    try:
        res = await get_container().excel.sync()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Excel update failed: {exc}") from None
    return {"ok": True, "appended": res.appended, "total_rows": res.total_rows - 1, "rebuilt": res.rebuilt,
            "preserved_corrupt_copy": res.preserved_corrupt_copy}


# ---- Users --------------------------------------------------------------------------
@router.get("/users")
async def list_users(user: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    return {"items": [UserOut.model_validate(u) for u in await UserRepository(session).all()]}


@router.post("/users", status_code=201)
async def create_user(body: UserCreate, user: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    repo = UserRepository(session)
    if await repo.by_email(body.email):
        raise HTTPException(409, "A user with this e-mail already exists")
    validate_password_strength(body.password)
    u = User(email=body.email.lower(), password_hash=hash_password(body.password), role=body.role)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return UserOut.model_validate(u)


@router.patch("/users/{user_id}")
async def update_user(user_id: int, body: UserUpdate, user: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    repo = UserRepository(session)
    demoting = (body.role == "viewer" and target.role == "admin") or (body.is_active is False and target.is_active)
    if demoting and target.role == "admin" and await repo.admin_count() <= 1:
        raise HTTPException(400, "At least one active administrator is required")
    if body.role is not None:
        target.role = body.role
    if body.is_active is not None:
        target.is_active = body.is_active
        if not body.is_active:
            target.session_version += 1
    if body.password:
        validate_password_strength(body.password)
        target.password_hash = hash_password(body.password)
        target.session_version += 1
    await session.commit()
    await session.refresh(target)
    return UserOut.model_validate(target)


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, user: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    if user_id == user.id:
        raise HTTPException(400, "You cannot delete your own account")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    if target.role == "admin" and target.is_active and await UserRepository(session).admin_count() <= 1:
        raise HTTPException(400, "At least one active administrator is required")
    await session.delete(target)
    await session.commit()
    return {"ok": True}
