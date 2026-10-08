"""Application configuration.

Every secret comes from environment variables (Hugging Face Space Secrets in
production). Nothing secret is ever sent to the frontend.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["production", "development", "test"] = "production"
    log_level: str = "INFO"

    # --- Core secrets -----------------------------------------------------
    database_url: str = Field(..., description="PostgreSQL connection URL")
    secret_key: str = Field(..., min_length=32, description="Session signing key")
    scheduler_token: str = Field(..., min_length=32, description="Bearer token for the scheduler endpoint")
    pagespeed_api_key: str = ""

    # --- Bootstrap admin (only used when the users table is empty) --------
    admin_email: str = ""
    admin_password: str = ""

    # --- Time ------------------------------------------------------------------
    app_timezone: str = "Asia/Kolkata"

    # --- PageSpeed -------------------------------------------------------------
    pagespeed_concurrency: int = Field(3, ge=1, le=10)
    pagespeed_timeout_seconds: int = Field(150, ge=30, le=600)
    pagespeed_max_retries: int = Field(3, ge=0, le=6)
    pagespeed_backoff_base_seconds: float = Field(4.0, ge=0)
    manual_test_cooldown_seconds: int = Field(120, ge=0)
    report_retention_days: int = Field(90, ge=0)  # stored Lighthouse reports; 0 = keep forever

    # --- Scheduling ------------------------------------------------------------
    schedule_catchup_hours: int = Field(6, ge=1, le=24)
    enable_internal_scheduler: bool = True
    internal_scheduler_interval_seconds: int = Field(60, ge=30)

    # --- Email -----------------------------------------------------------------
    email_provider: Literal["smtp", "sendgrid", "resend", "disabled"] = "smtp"
    email_from: str = ""
    email_from_name: str = "Website Performance Monitor"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: int = 30
    sendgrid_api_key: str = ""
    resend_api_key: str = ""
    report_emails: str = ""  # comma separated defaults; editable in Settings page
    alert_emails: str = ""

    # --- Excel storage ---------------------------------------------------------
    storage_backend: Literal["local", "s3", "hf_dataset"] = "local"
    local_storage_dir: str = "/data"
    storage_local_is_persistent: bool = False  # set true when LOCAL_STORAGE_DIR is a Docker volume / local disk
    excel_filename: str = "website-performance.xlsx"
    s3_bucket: str = ""
    s3_prefix: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    hf_token: str = ""
    hf_dataset_repo: str = ""
    hf_dataset_path: str = ""

    # --- Web / security --------------------------------------------------------
    public_base_url: str = ""
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_hours: int = Field(12, ge=1, le=168)
    trusted_proxy_hops: int = Field(1, ge=0, le=5)  # 1 = Hugging Face front proxy; 0 = direct exposure
    frame_ancestors: str = "'self' https://huggingface.co https://*.hf.space"
    frontend_dist: str = str(BASE_DIR / "frontend_dist")

    @field_validator("app_timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:  # pragma: no cover - config error
            raise ValueError(f"Unknown timezone {v!r}") from exc
        return v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @property
    def async_database_url(self) -> str:
        return normalize_database_url(self.database_url)[0]

    @property
    def database_connect_args(self) -> dict:
        return normalize_database_url(self.database_url)[1]

    @property
    def is_sqlite(self) -> bool:
        return self.async_database_url.startswith("sqlite")


def normalize_database_url(url: str) -> tuple[str, dict]:
    """Convert provider URLs (Neon, Supabase, Render...) to an asyncpg URL.

    asyncpg does not understand libpq query parameters such as ``sslmode`` or
    ``channel_binding``; they are translated into ``connect_args``.
    """
    if url.startswith("sqlite"):
        if "+aiosqlite" not in url:
            url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url, {}
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"):
        scheme = "postgresql+asyncpg"
    query = dict(parse_qsl(parts.query))
    connect_args: dict = {}
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    ssl_q = query.pop("ssl", None)
    if sslmode in ("require", "verify-ca", "verify-full") or ssl_q in ("true", "require"):
        connect_args["ssl"] = "require" if sslmode in (None, "require") else True
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)), connect_args


@lru_cache
def get_settings() -> Settings:
    import os

    # PT_ENV_FILE="" disables the .env file (the test suite uses this so a developer's
    # local .env with real credentials is never picked up by tests).
    env_file = os.getenv("PT_ENV_FILE", ".env") or None
    return Settings(_env_file=env_file)  # type: ignore[call-arg]
