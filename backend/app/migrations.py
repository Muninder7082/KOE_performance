"""Run Alembic migrations at startup (called in a worker thread)."""
from __future__ import annotations

from alembic import command
from alembic.config import Config

from .config import BASE_DIR, get_settings


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    s = get_settings()
    cfg.attributes["url"] = url or s.async_database_url
    cfg.attributes["connect_args"] = s.database_connect_args
    return cfg


def run_migrations(url: str | None = None) -> None:
    command.upgrade(alembic_config(url), "head")
