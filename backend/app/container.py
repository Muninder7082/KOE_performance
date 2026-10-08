"""Service wiring (one instance of each service per process)."""
from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .services.alerts import AlertService
from .services.email_service import EmailService
from .services.excel import ExcelReportService
from .services.jobs import JobManager
from .services.lighthouse_reports import LighthouseReportService
from .services.monitoring import PerformanceMonitoringService
from .services.pagespeed import PageSpeedService
from .services.report import ReportService
from .services.scheduler import SchedulerService
from .services.storage import StorageService, get_storage


@dataclass
class Container:
    sf: async_sessionmaker[AsyncSession]
    storage: StorageService
    pagespeed: PageSpeedService
    email: EmailService
    excel: ExcelReportService
    alerts: AlertService
    reports: LighthouseReportService
    monitoring: PerformanceMonitoringService
    report: ReportService
    scheduler: SchedulerService
    jobs: JobManager


def build_container(sf: async_sessionmaker[AsyncSession], *, storage: StorageService | None = None,
                    psi_client: httpx.AsyncClient | None = None, email_http: httpx.AsyncClient | None = None,
                    psi_sleep=None) -> Container:
    storage = storage or get_storage()
    pagespeed = PageSpeedService(psi_client, **({"sleep": psi_sleep} if psi_sleep else {}))
    email = EmailService(sf, email_http)
    excel = ExcelReportService(sf, storage)
    alerts = AlertService(sf, email)
    reports = LighthouseReportService(sf, storage)
    monitoring = PerformanceMonitoringService(sf, pagespeed, excel, alerts, reports)
    report = ReportService(sf, excel, email)
    scheduler = SchedulerService(sf, monitoring, excel, report)
    jobs = JobManager(sf, monitoring)
    return Container(sf, storage, pagespeed, email, excel, alerts, reports, monitoring, report, scheduler, jobs)


_container: Container | None = None


def set_container(c: Container | None) -> None:
    global _container
    _container = c


def get_container() -> Container:
    assert _container is not None, "Application not started"
    return _container
