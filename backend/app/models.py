"""SQLAlchemy models.

Historical tables (performance_results, alert_events, email_logs, task_runs) are
append-only from the application's point of view. Deleting a website keeps its
history: website_id becomes NULL and the name/URL snapshot on each row remains.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .clock import now_utc
from .db import Base, UTCDateTime


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="admin")  # admin | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=now_utc)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class MonitoredWebsite(Base):
    __tablename__ = "monitored_websites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    url_normalized: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    frequency: Mapped[str] = mapped_column(String(30), nullable=False, default="daily")
    monitor_time: Mapped[str] = mapped_column(String(5), nullable=False, default="08:40")  # HH:MM local
    day_of_week: Mapped[int | None] = mapped_column(Integer)  # 0=Mon..6=Sun, weekly only
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=now_utc)
    schedule_updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=now_utc)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_scheduled_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # occurrence processed


class PerformanceResult(Base):
    __tablename__ = "performance_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    website_id: Mapped[int | None] = mapped_column(ForeignKey("monitored_websites.id", ondelete="SET NULL"))
    website_name: Mapped[str] = mapped_column(String(200), nullable=False)
    requested_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str | None] = mapped_column(String(2048))
    strategy: Mapped[str] = mapped_column(String(10), nullable=False)  # desktop | mobile
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)  # manual | scheduled
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # success | failed
    api_status: Mapped[str | None] = mapped_column(String(100))
    performance_score: Mapped[int | None] = mapped_column(Integer)
    accessibility_score: Mapped[int | None] = mapped_column(Integer)
    best_practices_score: Mapped[int | None] = mapped_column(Integer)
    seo_score: Mapped[int | None] = mapped_column(Integer)
    fcp_s: Mapped[float | None] = mapped_column(Float)
    lcp_s: Mapped[float | None] = mapped_column(Float)
    tbt_ms: Mapped[float | None] = mapped_column(Float)
    cls: Mapped[float | None] = mapped_column(Float)
    speed_index_s: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tested_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(40))
    report_key: Mapped[str | None] = mapped_column(String(300))  # stored Lighthouse report
    excel_appended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    excel_appended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    __table_args__ = (
        Index("ix_results_website_strategy_tested", "website_id", "strategy", "tested_at"),
        Index("ix_results_tested_at", "tested_at"),
        Index("ix_results_excel_pending", "excel_appended", "id"),
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    website_id: Mapped[int | None] = mapped_column(ForeignKey("monitored_websites.id", ondelete="SET NULL"))
    website_name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    strategy: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="open")  # open | recovered
    score: Mapped[int | None] = mapped_column(Integer)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    first_detected_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_detected_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notify_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recovered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    recovered_score: Mapped[int | None] = mapped_column(Integer)
    last_result_id: Mapped[int | None] = mapped_column(ForeignKey("performance_results.id", ondelete="SET NULL"))

    __table_args__ = (Index("ix_alerts_website_strategy_state", "website_id", "strategy", "state"),)


class ScheduledTask(Base):
    """Named task state + lease lock (atomic UPDATE ... WHERE locked_until < now)."""

    __tablename__ = "scheduled_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    locked_by: Mapped[str | None] = mapped_column(String(100))
    last_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_status: Mapped[str | None] = mapped_column(String(20))
    last_message: Mapped[str | None] = mapped_column(Text)
    last_occurrence_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class TaskRun(Base):
    """Execution log of each scheduled monitoring cycle / daily report."""

    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    task: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # running | completed | failed | skipped
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    websites_due: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_task_runs_started", "started_at"),)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email_type: Mapped[str] = mapped_column(String(30), nullable=False)
    recipients: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    website_id: Mapped[int | None] = mapped_column(ForeignKey("monitored_websites.id", ondelete="SET NULL"))
    website_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # pending | sent | failed
    error: Mapped[str | None] = mapped_column(Text)
    has_attachment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=now_utc)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    __table_args__ = (Index("ix_email_logs_created", "created_at"),)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON encoded
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=now_utc)
