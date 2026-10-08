"""Request/response models (input validation lives here)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .schedule import FREQUENCY_HOURS, parse_hhmm

Strategy = Literal["desktop", "mobile"]


def _check_time(v: str | None) -> str | None:
    if v is not None:
        parse_hhmm(v)
    return v


def _check_freq(v: str | None) -> str | None:
    if v is not None and v not in FREQUENCY_HOURS:
        raise ValueError(f"Frequency must be one of: {', '.join(FREQUENCY_HOURS)}")
    return v


def _check_tz(v: str | None) -> str | None:
    if v is not None:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown timezone") from exc
    return v


class WebsiteBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(None, min_length=1, max_length=200)
    url: str | None = Field(None, min_length=1, max_length=2048)
    is_active: bool | None = None
    frequency: str | None = None
    monitor_time: str | None = None
    day_of_week: int | None = Field(None, ge=0, le=6)
    timezone: str | None = None
    threshold: int | None = Field(None, ge=1, le=100)
    notes: str | None = Field(None, max_length=2000)

    @field_validator("monitor_time")
    @classmethod
    def validate_time(cls, v):
        return _check_time(v)

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v):
        return _check_freq(v)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v):
        return _check_tz(v)


class WebsiteCreate(WebsiteBase):
    name: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=1, max_length=2048)


class WebsiteUpdate(WebsiteBase):
    pass


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int | None
    website_name: str
    requested_url: str
    final_url: str | None
    strategy: str
    trigger: str
    status: str
    api_status: str | None
    performance_score: int | None
    accessibility_score: int | None
    best_practices_score: int | None
    seo_score: int | None
    fcp_s: float | None
    lcp_s: float | None
    tbt_ms: float | None
    cls: float | None
    speed_index_s: float | None
    threshold: int
    error_code: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    tested_at: datetime
    excel_appended: bool
    has_report: bool = False
    health: str = "PENDING"


class LatestScores(BaseModel):
    desktop: ResultOut | None = None
    mobile: ResultOut | None = None


class WebsiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    is_active: bool
    frequency: str
    monitor_time: str
    day_of_week: int | None
    timezone: str
    threshold: int
    notes: str | None
    created_at: datetime
    updated_at: datetime
    last_checked_at: datetime | None
    schedule_description: str = ""
    next_run_at: datetime | None = None
    status: str = "PENDING"
    latest: LatestScores = Field(default_factory=LatestScores)
    test_running: bool = False


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int | None
    website_name: str
    url: str
    strategy: str
    state: str
    score: int | None
    threshold: int
    first_detected_at: datetime
    last_detected_at: datetime
    last_notified_at: datetime | None
    notify_count: int
    recovered_at: datetime | None
    recovered_score: int | None


class EmailLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email_type: str
    recipients: str
    subject: str
    website_id: int | None
    website_name: str | None
    status: str
    error: str | None
    has_attachment: bool
    created_at: datetime
    sent_at: datetime | None


class TaskRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    task: str
    trigger: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    websites_due: int
    tests_succeeded: int
    tests_failed: int
    message: str | None


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int


class TestRequest(BaseModel):
    strategies: list[Strategy] = Field(default_factory=lambda: ["desktop", "mobile"], min_length=1, max_length=2)

    @field_validator("strategies")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        return sorted(set(v), key=["desktop", "mobile"].index)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=10, max_length=72)
    role: Literal["admin", "viewer"] = "viewer"


class UserUpdate(BaseModel):
    role: Literal["admin", "viewer"] | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=10, max_length=72)


class PasswordChange(BaseModel):
    current_password: str = Field(..., max_length=200)
    new_password: str = Field(..., min_length=10, max_length=72)


class SettingsUpdate(BaseModel):
    report_emails: list[EmailStr] | None = Field(None, max_length=50)
    alert_emails: list[EmailStr] | None = Field(None, max_length=50)
    default_threshold: int | None = Field(None, ge=1, le=100)
    default_monitor_time: str | None = None
    default_frequency: str | None = None
    timezone: str | None = None
    alert_mode: Literal["once_until_recovered", "every_occurrence", "daily"] | None = None
    send_recovery_emails: bool | None = None
    daily_report_enabled: bool | None = None
    monitor_day_of_week: int | None = Field(None, ge=0, le=6)

    @field_validator("default_monitor_time")
    @classmethod
    def validate_time(cls, v):
        return _check_time(v)

    @field_validator("default_frequency")
    @classmethod
    def validate_frequency(cls, v):
        return _check_freq(v)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v):
        return _check_tz(v)


class TestEmailIn(BaseModel):
    to: EmailStr | None = None


class TestPageSpeedIn(BaseModel):
    url: str | None = Field(None, max_length=2048)
    strategy: Strategy = "mobile"
