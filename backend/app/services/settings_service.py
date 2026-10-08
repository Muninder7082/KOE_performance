"""Runtime (non-secret) settings editable from the Settings page."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..clock import now_utc
from ..config import get_settings
from ..models import SystemSetting
from ..schedule import FREQUENCY_HOURS, parse_hhmm

AlertMode = Literal["once_until_recovered", "every_occurrence", "daily"]


def _split_emails(raw: str) -> list[str]:
    return [e.strip() for e in raw.replace(";", ",").split(",") if e.strip()]


class AppSettings(BaseModel):
    report_emails: list[EmailStr] = Field(default_factory=list, max_length=50)
    alert_emails: list[EmailStr] = Field(default_factory=list, max_length=50)
    default_threshold: int = Field(90, ge=1, le=100)
    # ONE schedule for every page: at this time all active pages are tested (queued with
    # controlled concurrency) and the report is e-mailed as soon as the whole run finishes.
    default_monitor_time: str = "08:40"
    default_frequency: str = "daily"
    monitor_day_of_week: int = Field(0, ge=0, le=6)  # weekly only (0 = Monday)
    timezone: str = "Asia/Kolkata"
    alert_mode: AlertMode = "once_until_recovered"
    send_recovery_emails: bool = True
    daily_report_enabled: bool = True  # e-mail the report after each scheduled run
    report_schedule_updated_at: datetime | None = None  # anchor: schedule changes never run retroactively

    @field_validator("default_monitor_time")
    @classmethod
    def _time(cls, v: str) -> str:
        parse_hhmm(v)
        return v

    @field_validator("default_frequency")
    @classmethod
    def _freq(cls, v: str) -> str:
        if v not in FREQUENCY_HOURS:
            raise ValueError("Unknown frequency")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown timezone") from exc
        return v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


EDITABLE_FIELDS = set(AppSettings.model_fields) - {"report_schedule_updated_at"}


def _defaults() -> dict:
    env = get_settings()
    return {
        "report_emails": _split_emails(env.report_emails),
        "alert_emails": _split_emails(env.alert_emails),
        "timezone": env.app_timezone,
    }


async def load(session: AsyncSession) -> AppSettings:
    data = _defaults()
    rows = (await session.scalars(select(SystemSetting))).all()
    for row in rows:
        if row.key in AppSettings.model_fields:
            try:
                data[row.key] = json.loads(row.value)
            except json.JSONDecodeError:
                continue
    try:
        return AppSettings(**data)
    except ValueError:
        # A bad stored value must never take the scheduler down: fall back per field.
        clean = {}
        for k, v in data.items():
            try:
                AppSettings(**{k: v})
                clean[k] = v
            except ValueError:
                pass
        return AppSettings(**clean)


async def update(session: AsyncSession, changes: dict) -> AppSettings:
    current = await load(session)
    merged = current.model_dump(mode="json")
    for k, v in changes.items():
        if k in EDITABLE_FIELDS:
            merged[k] = v
    schedule_keys = ("default_monitor_time", "default_frequency", "monitor_day_of_week", "timezone")
    if any(merged.get(k) != getattr(current, k) for k in schedule_keys):
        merged["report_schedule_updated_at"] = now_utc().isoformat()
    validated = AppSettings(**merged)
    dumped = validated.model_dump(mode="json")
    now = now_utc()
    for key, value in dumped.items():
        row = await session.get(SystemSetting, key)
        encoded = json.dumps(value)
        if row is None:
            session.add(SystemSetting(key=key, value=encoded, updated_at=now))
        elif row.value != encoded:
            row.value = encoded
            row.updated_at = now
    await session.commit()
    return validated


async def ensure_initialized(session: AsyncSession) -> None:
    """Persist defaults once so report_schedule_updated_at is anchored at install time."""
    existing = await session.get(SystemSetting, "report_schedule_updated_at")
    if existing is None:
        session.add(SystemSetting(key="report_schedule_updated_at", value=json.dumps(now_utc().isoformat())))
        await session.commit()
