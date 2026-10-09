"""FastAPI application entry point (uvicorn app.main:app --port 7860)."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from . import db
from .api import admin, auth, internal, monitoring, websites
from .config import get_settings
from .container import build_container, get_container, set_container
from .migrations import run_migrations
from .ratelimit import client_ip, limiter
from .repositories import UserRepository
from .security import hash_password
from .services import settings_service

log = logging.getLogger("app")


async def bootstrap_admin() -> None:
    s = get_settings()
    async with db.session_factory()() as session:
        repo = UserRepository(session)
        if await repo.count() > 0:
            return
        if not (s.admin_email and s.admin_password):
            log.warning("No users exist. Set ADMIN_EMAIL and ADMIN_PASSWORD to create the first administrator.")
            return
        if len(s.admin_password) < 10:
            log.error("ADMIN_PASSWORD must be at least 10 characters; administrator not created.")
            return
        from .models import User

        session.add(User(email=s.admin_email.strip().lower(), password_hash=hash_password(s.admin_password),
                         role="admin"))
        await session.commit()
        log.info("Created administrator %s", s.admin_email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    logging.basicConfig(level=s.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "botocore", "urllib3", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    await asyncio.to_thread(run_migrations, s.async_database_url)
    sf = db.init_engine(s.async_database_url, s.database_connect_args)
    await bootstrap_admin()
    async with sf() as session:
        await settings_service.ensure_initialized(session)
    factory = getattr(app.state, "container_factory", None) or build_container  # tests inject fakes here
    container = factory(sf)
    set_container(container)
    async with sf() as session:
        startup_settings = await settings_service.load(session)
    sync_task = asyncio.create_task(container.wakeup.sync(startup_settings))  # wake-up job follows Settings
    aborted = await container.scheduler.abort_stale_runs()
    if aborted:
        log.warning("Marked %d interrupted scheduler run(s) as aborted", aborted)
    storage_info = container.storage.describe()
    if storage_info.get("warning"):
        log.warning(storage_info["warning"])
    loop_task = None
    if s.enable_internal_scheduler and s.environment != "test":
        loop_task = asyncio.create_task(container.scheduler.internal_loop(s.internal_scheduler_interval_seconds))
    log.info("Website Performance Monitor started (storage=%s, timezone=%s)", storage_info["backend"],
             s.app_timezone)
    try:
        yield
    finally:
        if loop_task:
            loop_task.cancel()
        sync_task.cancel()
        await container.scheduler.shutdown()
        await container.jobs.shutdown()
        await container.pagespeed.aclose()
        set_container(None)
        await db.dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Website Performance Monitor", lifespan=lifespan,
                  docs_url="/api/docs" if s.environment != "production" else None,
                  redoc_url=None, openapi_url="/api/openapi.json" if s.environment != "production" else None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/health"):
            try:  # coarse per-IP ceiling; sensitive endpoints have tighter limits
                limiter.hit(f"global:{client_ip(request)}", 600, 60)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=429, headers=exc.headers)
        response = await call_next(request)
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
            f"frame-ancestors {s.frame_ancestors}",
        )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errors = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
        first = errors[0]["msg"] if errors else "Invalid request"
        return JSONResponse(status_code=422, content={"detail": first.removeprefix("Value error, "), "errors": errors})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/api/health")
    async def health():
        try:
            c = get_container()
        except AssertionError:
            return JSONResponse({"status": "starting"}, status_code=503)
        return {"status": "ok", "storage": c.storage.name}

    for r in (auth.router, websites.router, monitoring.router, admin.router, internal.router):
        app.include_router(r)

    lh_assets = Path(__file__).parent / "static" / "lighthouse"
    app.mount("/lighthouse-assets", StaticFiles(directory=lh_assets), name="lighthouse-assets")

    dist = Path(s.frontend_dist)
    if (dist / "index.html").exists():
        if (dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404, "Not found")
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
    else:
        log.warning("Frontend build not found at %s (API only)", dist)

    return app


app = create_app()
