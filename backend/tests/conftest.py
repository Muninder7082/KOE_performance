"""Test fixtures.

Mock PageSpeed responses exist ONLY here (httpx.MockTransport). Production code
always calls the real Google PageSpeed Insights API.

Database: SQLite by default; set PT_TEST_DATABASE_URL to a PostgreSQL URL to
run the same suite against PostgreSQL (each test gets a clean schema).
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

os.environ.update({
    "PT_ENV_FILE": "",  # never read the developer's backend/.env during tests
    "ENVIRONMENT": "test",
    "SECRET_KEY": "test-secret-key-0123456789-abcdefghijklmnop",
    "SCHEDULER_TOKEN": "test-scheduler-token-0123456789-abcdefghij",
    "PAGESPEED_API_KEY": "TEST-PSI-KEY-123",
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_PASSWORD": "Admin-Password-123",
    "COOKIE_SECURE": "false",
    "EMAIL_PROVIDER": "smtp",
    "SMTP_HOST": "smtp.test.invalid",
    "EMAIL_FROM": "monitor@example.com",
    "REPORT_EMAILS": "reports@example.com",
    "ALERT_EMAILS": "alerts@example.com",
    "STORAGE_BACKEND": "local",
    "PAGESPEED_BACKOFF_BASE_SECONDS": "0",
    "MANUAL_TEST_COOLDOWN_SECONDS": "0",
    "ENABLE_INTERNAL_SCHEDULER": "false",
    "DATABASE_URL": "sqlite+aiosqlite:///placeholder.db",
})

from app import clock  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.ratelimit import limiter  # noqa: E402

PG_URL = os.getenv("PT_TEST_DATABASE_URL")


def lighthouse_payload(url: str, strategy: str, score: int | None, *, missing: tuple[str, ...] = ()) -> dict:
    audits = {
        "first-contentful-paint": {"numericValue": 1800.4},
        "largest-contentful-paint": {"numericValue": 2912.0},
        "total-blocking-time": {"numericValue": 310.2},
        "cumulative-layout-shift": {"numericValue": 0.0812},
        "speed-index": {"numericValue": 3204.0},
    }
    for m in missing:
        audits.pop(m, None)
    categories = {
        "performance": {"score": None if score is None else score / 100},
        "accessibility": {"score": 0.95},
        "best-practices": {"score": 0.92},
        "seo": {"score": 0.9},
    }
    return {
        "id": url,
        "lighthouseResult": {
            "requestedUrl": url, "finalDisplayedUrl": url, "fetchTime": clock.now_utc().isoformat(),
            "categories": categories, "audits": audits,
        },
    }


@dataclass
class FakePSI:
    """Scripted PageSpeed API. scores[(url, strategy)] = int | ("http", status, body)."""

    scores: dict = field(default_factory=dict)
    default: int = 95
    calls: list = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        url, strategy = params["url"], params["strategy"]
        assert request.headers["X-goog-api-key"] == "TEST-PSI-KEY-123" and "key" not in params
        assert set(params.get_list("category")) == {"performance", "accessibility", "best-practices", "seo"}
        self.calls.append((url, strategy))
        spec = self.scores.get((url, strategy), self.default)
        if isinstance(spec, list):  # sequence of responses for retries
            spec = spec.pop(0) if len(spec) > 1 else spec[0]
        if isinstance(spec, tuple) and spec[0] == "http":
            return httpx.Response(spec[1], json=spec[2])
        if isinstance(spec, tuple) and spec[0] == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json=lighthouse_payload(url, strategy, spec))

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


@dataclass
class Outbox:
    sent: list = field(default_factory=list)
    fail: bool = False


@pytest.fixture(autouse=True)
def _reset():
    clock.set_now(None)
    limiter.reset()
    yield
    clock.set_now(None)


async def _prepare_database(tmp_path: Path) -> str:
    if not PG_URL:
        return f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
    import asyncpg

    raw = PG_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(raw)
    await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    await conn.close()
    return PG_URL


@dataclass
class Env:
    tmp: Path
    db_url: str
    storage_dir: Path
    psi: FakePSI
    outbox: Outbox


@pytest.fixture
async def env(tmp_path, monkeypatch) -> Env:
    db_url = await _prepare_database(tmp_path)
    storage = tmp_path / "storage"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(storage))
    get_settings.cache_clear()
    from app.services import storage as storage_mod

    storage_mod.set_storage(None)
    e = Env(tmp_path, db_url, storage, FakePSI(), Outbox())

    from app.services.email_service import EmailService

    async def fake_deliver(self, mail, recipients):
        if e.outbox.fail:
            raise ConnectionError("SMTP server unreachable")
        e.outbox.sent.append({"type": mail.email_type, "to": recipients, "subject": mail.subject,
                              "html": mail.html, "text": mail.text,
                              "attachments": [(a.filename, a.content) for a in mail.attachments]})

    monkeypatch.setattr(EmailService, "_deliver", fake_deliver)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep(asyncio.sleep))
    yield e
    get_settings.cache_clear()
    storage_mod.set_storage(None)


def _fast_sleep(real_sleep):
    async def sleeper(delay, *a, **k):
        return await real_sleep(min(delay, 0.01), *a, **k)
    return sleeper


@asynccontextmanager
async def running_app(e: Env):
    """Start the full application (migrations, bootstrap, services) like uvicorn does."""
    from app.container import build_container
    from app.main import create_app

    app = create_app()
    app.state.container_factory = lambda sf: build_container(sf, psi_client=e.psi.client())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, client=("203.0.113.9", 5555))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield app, client


async def login(client: httpx.AsyncClient, email="admin@example.com", password="Admin-Password-123") -> dict:
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["csrf_token"]
    client.headers["X-CSRF-Token"] = token
    return r.json()


async def wait_job(client: httpx.AsyncClient, job_id: str, timeout: float = 20) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        r = await client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        job = r.json()
        if job["status"] in ("completed", "failed"):
            return job
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"job did not finish: {job}")
        await asyncio.sleep(0.05)


def ist(y, mo, d, h, mi) -> datetime:
    from zoneinfo import ZoneInfo

    return datetime(y, mo, d, h, mi, tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)


SCHED_HEADERS = {"Authorization": "Bearer test-scheduler-token-0123456789-abcdefghij"}
