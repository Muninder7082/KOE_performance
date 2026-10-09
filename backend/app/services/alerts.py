"""AlertService — threshold checks with deduplication, sent as ONE combined e-mail.

Alert state lives in alert_events (one *open* row per website + device while
the problem persists).

  once_until_recovered (default)
      first breach -> notify; repeated breaches -> no e-mail;
      score back >= threshold -> row marked recovered (+ optional recovery
      notice); a later breach opens a new row -> notify again.
  every_occurrence  notify on every breaching test.
  daily             at most one notification per open alert per local calendar day.

Two steps:
  1. process(result_id) applies the rules to one result and returns a Notice
     (or None). Nothing is sent yet.
  2. notify(notices) sends ONE e-mail listing every page/device below its
     threshold (plus a "recovered" section). A scheduled run collects the
     notices of all pages and calls notify() once at the end; a manual test
     calls it for the tested page.

If the e-mail fails, last_notified_at stays empty and the next breaching test
retries. Failed PageSpeed tests do not change state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..clock import now_utc
from ..config import get_settings
from ..models import AlertEvent, MonitoredWebsite, PerformanceResult
from . import email_templates, settings_service
from .email_service import PERFORMANCE_ALERT, RECOVERY, EmailService, OutgoingEmail

log = logging.getLogger(__name__)


@dataclass
class Notice:
    kind: str          # "attention" | "recovered"
    alert_id: int
    result_id: int


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

    # ---- step 1: rules ------------------------------------------------------------------
    async def process(self, result_id: int) -> Notice | None:
        """Apply alert rules to one stored result; return what should be e-mailed."""
        async with self.sf() as session:
            r = await session.get(PerformanceResult, result_id)
            if r is None or r.status != "success" or r.performance_score is None or r.website_id is None:
                return None
            website = await session.get(MonitoredWebsite, r.website_id)
            if website is None:
                return None
            app = await settings_service.load(session)
            now = now_utc()
            alert = await session.scalar(
                select(AlertEvent)
                .where(AlertEvent.website_id == website.id, AlertEvent.strategy == r.strategy,
                       AlertEvent.state == "open")
                .order_by(AlertEvent.id.desc()).limit(1)
            )
            if r.performance_score < r.threshold:
                if alert is None:
                    alert = AlertEvent(
                        website_id=website.id, website_name=website.name, url=website.url, strategy=r.strategy,
                        state="open", score=r.performance_score, threshold=r.threshold,
                        first_detected_at=r.tested_at, last_detected_at=r.tested_at, last_result_id=r.id,
                    )
                    session.add(alert)
                else:
                    alert.score = r.performance_score
                    alert.threshold = r.threshold
                    alert.last_detected_at = r.tested_at
                    alert.last_result_id = r.id
                await session.commit()
                if self._should_notify(alert, app.alert_mode, now, app.tz):
                    return Notice("attention", alert.id, r.id)
                return None
            if alert is not None:
                was_notified = alert.last_notified_at is not None
                alert.state = "recovered"
                alert.recovered_at = r.tested_at
                alert.recovered_score = r.performance_score
                alert.last_result_id = r.id
                await session.commit()
                if app.send_recovery_emails and was_notified:
                    return Notice("recovered", alert.id, r.id)
            return None

    # ---- step 2: one combined e-mail ----------------------------------------------------
    async def notify(self, notices: list[Notice]) -> bool | None:
        """Send one e-mail for all notices. Returns None when there was nothing to send."""
        notices = [n for n in notices if n is not None]
        if not notices:
            return None
        async with self.sf() as session:
            app = await settings_service.load(session)
            items: list[dict] = []
            for n in notices:
                r = await session.get(PerformanceResult, n.result_id)
                alert = await session.get(AlertEvent, n.alert_id)
                if r is None or alert is None:
                    continue
                items.append({"kind": n.kind, "result": r, "alert": alert, "name": alert.website_name,
                              "url": alert.url, "threshold": r.threshold})
            if not items:
                return None
            items.sort(key=lambda i: (i["kind"] != "attention", i["name"].lower(), i["result"].strategy != "mobile"))
            attention = [i for i in items if i["kind"] == "attention"]
            recovered = [i for i in items if i["kind"] == "recovered"]
            base_url = get_settings().public_base_url
            subject, html, text = email_templates.alerts_digest_email(attention, recovered, app.tz, base_url)
            pages = {i["alert"].website_id for i in items}
            single = items[0]["alert"] if len(pages) == 1 else None
            ok = await self.email.send(OutgoingEmail(
                PERFORMANCE_ALERT if attention else RECOVERY, list(app.alert_emails), subject, html, text,
                website_id=single.website_id if single else None,
                website_name=single.website_name if single else f"{len(pages)} pages"))
            if ok and attention:
                now = now_utc()
                for i in attention:
                    i["alert"].last_notified_at = now
                    i["alert"].notify_count += 1
                await session.commit()
            return ok

    async def process_and_notify(self, result_ids: list[int]) -> bool | None:
        notices = []
        for rid in result_ids:
            try:
                notices.append(await self.process(rid))
            except Exception:  # noqa: BLE001 - one bad result must not block the others
                log.exception("Alert processing failed for result %s", rid)
        return await self.notify([n for n in notices if n])
