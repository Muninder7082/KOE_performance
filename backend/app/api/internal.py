"""Scheduler endpoint for external cron services (token protected)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..container import get_container
from ..ratelimit import client_ip, limiter
from ..security import verify_scheduler_token

router = APIRouter(prefix="/api/internal", tags=["internal"])


def _guard(request: Request) -> None:
    # Rate-limit before checking the token so brute force is throttled too.
    limiter.hit(f"internal:{client_ip(request)}", 30, 60)
    verify_scheduler_token(request)


@router.post("/run-scheduled-checks")
async def run_scheduled_checks(request: Request, wait: bool = Query(False), _: None = Depends(_guard)):
    """Find due websites, test desktop + mobile, save, update Excel, alert, send the daily report.

    By default the work runs in the background and the call returns immediately
    (most cron services time out after ~30 s). Pass ?wait=true to block until the
    cycle finishes (useful for GitHub Actions).
    """
    trigger = request.headers.get("X-Scheduler-Source", "external")[:30] or "external"
    return await get_container().scheduler.trigger(trigger, wait=wait)


@router.get("/scheduler-status")
async def scheduler_status(_: None = Depends(_guard)):
    from ..clock import now_utc

    s = get_container().scheduler
    now = now_utc()
    due = await s.due_websites(now)
    return {"running": await s.is_running(), "websites_due": len(due),
            "report_due": (await s.report_due(now)) is not None, "server_time": now}
