"""AlertService — threshold checks with deduplication.

Alert state lives in alert_events (one *open* row per website + device while
the problem persists).

  once_until_recovered (default)
      first breach -> e-mail; repeated breaches -> no e-mail;
      score back >= threshold -> row marked recovered (+ optional recovery
      e-mail); a later breach opens a new row -> e-mail again.
  every_occurrence  e-mail on every breaching test.
  daily             at most one e-mail per open alert per local calendar day.

If the alert e-mail fails, last_notified_at stays empty and the next breaching
test retries the notification. Failed PageSpeed tests do not change state.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..clock import now_utc
from ..config import get_settings
from ..models import AlertEvent, MonitoredWebsite, PerformanceResult
from . import email_templates, settings_service
from .email_service import PERFORMANCE_ALERT, RECOVERY, EmailService, OutgoingEmail

log = logging.getLogger(__name__)


class AlertService:
    def __init__(self, sf: async_sessionmaker[AsyncSession], email: EmailService):
        self.sf = sf
        self.email = email

    @staticmethod
    def _should_notify(alert: AlertEvent, mode: str, now: datetime, tz) -> bool:
        if alert.last_notified_at is None:
            return True
        if mode == "every_occurrence":
            return True
        if mode == "daily":
            return alert.last_notified_at.astimezone(tz).date() != now.astimezone(tz).date()
        return False

    async def process(self, result_id: int) -> str | None:
        """Apply alert rules to one stored result. Returns the action taken."""
        async with self.sf() as session:
            r = await session.get(PerformanceResult, result_id)
            if r is None or r.status != "success" or r.performance_score is None or r.website_id is None:
                return None
            website = await session.get(MonitoredWebsite, r.website_id)
            if website is None:
                return None
            app = await settings_service.load(session)
            tz = app.tz
            now = now_utc()
            threshold = r.threshold
            alert = await session.scalar(
                select(AlertEvent)
                .where(AlertEvent.website_id == website.id, AlertEvent.strategy == r.strategy,
                       AlertEvent.state == "open")
                .order_by(AlertEvent.id.desc()).limit(1)
            )
            base_url = get_settings().public_base_url
            if r.performance_score < threshold:
                action = "repeat"
                if alert is None:
                    alert = AlertEvent(
                        website_id=website.id, website_name=website.name, url=website.url, strategy=r.strategy,
                        state="open", score=r.performance_score, threshold=threshold,
                        first_detected_at=r.tested_at, last_detected_at=r.tested_at, last_result_id=r.id,
                    )
                    session.add(alert)
                    action = "opened"
                else:
                    alert.score = r.performance_score
                    alert.threshold = threshold
                    alert.last_detected_at = r.tested_at
                    alert.last_result_id = r.id
                await session.commit()
                if self._should_notify(alert, app.alert_mode, now, tz):
                    subject, html, text = email_templates.alert_email(r, website.name, website.url, threshold, tz,
                                                                      base_url)
                    ok = await self.email.send(OutgoingEmail(
                        PERFORMANCE_ALERT, list(app.alert_emails), subject, html, text,
                        website_id=website.id, website_name=website.name))
                    if ok:
                        alert.last_notified_at = now
                        alert.notify_count += 1
                        await session.commit()
                        action += "+notified"
                    else:
                        action += "+notify_failed"
                return action
            if alert is not None:
                alert.state = "recovered"
                alert.recovered_at = r.tested_at
                alert.recovered_score = r.performance_score
                alert.last_result_id = r.id
                await session.commit()
                if app.send_recovery_emails and alert.last_notified_at is not None:
                    subject, html, text = email_templates.recovery_email(r, website.name, website.url, threshold, tz,
                                                                         base_url)
                    await self.email.send(OutgoingEmail(
                        RECOVERY, list(app.alert_emails), subject, html, text,
                        website_id=website.id, website_name=website.name))
                return "recovered"
            return None
