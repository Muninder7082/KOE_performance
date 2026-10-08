"""Daily performance report e-mail with the complete Excel workbook attached."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..clock import now_utc
from ..config import get_settings
from . import email_templates, reporting, settings_service
from .email_service import DAILY_REPORT, Attachment, EmailService, OutgoingEmail
from .excel import ExcelReportService

log = logging.getLogger(__name__)
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024  # stay under common provider limits (Gmail 25 MB)


class ReportService:
    def __init__(self, sf: async_sessionmaker[AsyncSession], excel: ExcelReportService, email: EmailService):
        self.sf = sf
        self.excel = excel
        self.email = email

    async def send_daily(self) -> bool:
        # Make sure every stored result is in the workbook before attaching it.
        try:
            await self.excel.sync()
        except Exception as exc:  # noqa: BLE001 - still send the report with the stored workbook
            log.error("Excel sync before daily report failed: %s", exc)
        async with self.sf() as session:
            app = await settings_service.load(session)
            now = now_utc()
            ov = await reporting.overview(session, app.tz, now)
        attachments: list[Attachment] = []
        filename = get_settings().excel_filename
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / filename
            try:
                if await self.excel.fetch_latest(path):
                    size = path.stat().st_size
                    if size <= MAX_ATTACHMENT_BYTES:
                        attachments.append(Attachment(filename, path.read_bytes()))
                    else:
                        log.error("Workbook is %.1f MB, too large to attach", size / 1e6)
            except Exception as exc:  # noqa: BLE001
                log.error("Could not load workbook for the daily report: %s", exc)
        subject, html, text = email_templates.daily_report_email(
            ov, app.tz, now, get_settings().public_base_url, attached=bool(attachments))
        return await self.email.send(OutgoingEmail(DAILY_REPORT, list(app.report_emails), subject, html, text,
                                                   attachments=attachments))
