"""EmailService — SMTP (default) or HTTPS e-mail APIs.

Hugging Face Spaces may block outbound SMTP ports; in that case set
EMAIL_PROVIDER=brevo, sendgrid or resend, which send over HTTPS (port 443).
Every attempt is recorded in email_logs; failures never raise to callers.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..clock import now_utc
from ..config import get_settings
from ..models import EmailLog

log = logging.getLogger(__name__)

DAILY_REPORT = "daily_report"
PERFORMANCE_ALERT = "performance_alert"
RECOVERY = "recovery_notification"
TEST_EMAIL = "test_email"
EMAIL_TYPE_LABELS = {
    DAILY_REPORT: "Daily Report",
    PERFORMANCE_ALERT: "Performance Alert",
    RECOVERY: "Recovery Notification",
    TEST_EMAIL: "Test Email",
}
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass
class Attachment:
    filename: str
    content: bytes
    mime: str = XLSX_MIME


@dataclass
class OutgoingEmail:
    email_type: str
    to: list[str]
    subject: str
    html: str
    text: str
    attachments: list[Attachment] = field(default_factory=list)
    website_id: int | None = None
    website_name: str | None = None


class EmailSendError(Exception):
    pass


class EmailService:
    def __init__(self, sf: async_sessionmaker[AsyncSession], http: httpx.AsyncClient | None = None):
        self.sf = sf
        self.s = get_settings()
        self._http = http

    # ---- status ---------------------------------------------------------------
    def status(self) -> dict:
        s = self.s
        provider = s.email_provider
        missing: list[str] = []
        if provider == "smtp":
            for name, val in (("SMTP_HOST", s.smtp_host), ("EMAIL_FROM", s.email_from or s.smtp_username)):
                if not val:
                    missing.append(name)
        elif provider == "brevo":
            missing += [n for n, v in (("BREVO_API_KEY", s.brevo_api_key), ("EMAIL_FROM", s.email_from)) if not v]
        elif provider == "sendgrid":
            missing += [n for n, v in (("SENDGRID_API_KEY", s.sendgrid_api_key), ("EMAIL_FROM", s.email_from)) if not v]
        elif provider == "resend":
            missing += [n for n, v in (("RESEND_API_KEY", s.resend_api_key), ("EMAIL_FROM", s.email_from)) if not v]
        return {
            "provider": provider,
            "configured": provider != "disabled" and not missing,
            "missing": missing,
            "from": self._from_address() if provider != "disabled" else None,
            "smtp_host": s.smtp_host if provider == "smtp" else None,
            "smtp_port": s.smtp_port if provider == "smtp" else None,
            "smtp_security": s.smtp_security if provider == "smtp" else None,
        }

    def _from_address(self) -> str:
        return self.s.email_from or self.s.smtp_username

    # ---- sending ----------------------------------------------------------------
    async def send(self, mail: OutgoingEmail) -> bool:
        recipients = sorted({r.strip() for r in mail.to if r and r.strip()})
        async with self.sf() as session:
            entry = EmailLog(
                email_type=mail.email_type, recipients=", ".join(recipients), subject=mail.subject[:500],
                website_id=mail.website_id, website_name=mail.website_name, status="pending",
                has_attachment=bool(mail.attachments), created_at=now_utc(),
            )
            session.add(entry)
            await session.commit()
            log_id = entry.id
        error: str | None = None
        if not recipients:
            error = "No recipients configured (set report/alert e-mails in Settings)"
        elif not self.status()["configured"]:
            st = self.status()
            error = ("E-mail is disabled" if st["provider"] == "disabled"
                     else f"E-mail provider not configured; missing: {', '.join(st['missing'])}")
        else:
            for attempt in range(2):
                try:
                    await self._deliver(mail, recipients)
                    error = None
                    break
                except Exception as exc:  # noqa: BLE001 - every failure is logged, never raised
                    error = self._scrub(f"{type(exc).__name__}: {exc}")
                    log.warning("E-mail '%s' attempt %d failed: %s", mail.subject, attempt + 1, error)
                    if attempt == 0:
                        await asyncio.sleep(3)
        async with self.sf() as session:
            entry = await session.get(EmailLog, log_id)
            if entry is not None:
                entry.status = "failed" if error else "sent"
                entry.error = error[:2000] if error else None
                entry.sent_at = None if error else now_utc()
                await session.commit()
        return error is None

    def _scrub(self, text: str) -> str:
        for secret in (self.s.smtp_password, self.s.sendgrid_api_key, self.s.resend_api_key, self.s.brevo_api_key):
            if secret:
                text = text.replace(secret, "***")
        return text

    async def _deliver(self, mail: OutgoingEmail, recipients: list[str]) -> None:
        provider = self.s.email_provider
        if provider == "smtp":
            await asyncio.to_thread(self._send_smtp, mail, recipients)
        elif provider == "brevo":
            await self._send_brevo(mail, recipients)
        elif provider == "sendgrid":
            await self._send_sendgrid(mail, recipients)
        elif provider == "resend":
            await self._send_resend(mail, recipients)
        else:  # pragma: no cover - guarded by status()
            raise EmailSendError("E-mail disabled")

    def _send_smtp(self, mail: OutgoingEmail, recipients: list[str]) -> None:
        s = self.s
        msg = EmailMessage()
        msg["Subject"] = mail.subject
        msg["From"] = formataddr((s.email_from_name, self._from_address()))
        msg["To"] = ", ".join(recipients)
        msg["Message-ID"] = make_msgid(domain=(self._from_address().split("@")[-1] or None))
        msg.set_content(mail.text)
        msg.add_alternative(mail.html, subtype="html")
        for a in mail.attachments:
            maintype, subtype = a.mime.split("/", 1)
            msg.add_attachment(a.content, maintype=maintype, subtype=subtype, filename=a.filename)
        context = ssl.create_default_context()
        if s.smtp_security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds,
                                                    context=context)
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds)
        try:
            server.ehlo()
            if s.smtp_security == "starttls":
                server.starttls(context=context)
                server.ehlo()
            if s.smtp_username:
                server.login(s.smtp_username, s.smtp_password)
            server.send_message(msg, to_addrs=recipients)
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass

    async def _post(self, url: str, headers: dict, payload: dict) -> None:
        client = self._http or httpx.AsyncClient(timeout=60)
        try:
            resp = await client.post(url, headers=headers, json=payload)
        finally:
            if self._http is None:
                await client.aclose()
        if resp.status_code >= 300:
            raise EmailSendError(f"HTTP {resp.status_code}: {resp.text[:500]}")

    async def _send_brevo(self, mail: OutgoingEmail, recipients: list[str]) -> None:
        """Brevo transactional e-mail API (free tier: 300 e-mails/day). The sender address must be
        verified in Brevo (Senders, domains & dedicated IPs -> Senders)."""
        payload = {
            "sender": {"email": self._from_address(), "name": self.s.email_from_name},
            "to": [{"email": r} for r in recipients],
            "subject": mail.subject,
            "htmlContent": mail.html,
            "textContent": mail.text,
        }
        if mail.attachments:
            payload["attachment"] = [{"name": a.filename, "content": base64.b64encode(a.content).decode("ascii")}
                                     for a in mail.attachments]
        await self._post("https://api.brevo.com/v3/smtp/email",
                         {"api-key": self.s.brevo_api_key, "accept": "application/json"}, payload)

    async def _send_sendgrid(self, mail: OutgoingEmail, recipients: list[str]) -> None:
        payload = {
            "personalizations": [{"to": [{"email": r} for r in recipients]}],
            "from": {"email": self._from_address(), "name": self.s.email_from_name},
            "subject": mail.subject,
            "content": [{"type": "text/plain", "value": mail.text}, {"type": "text/html", "value": mail.html}],
        }
        if mail.attachments:
            payload["attachments"] = [{
                "content": base64.b64encode(a.content).decode("ascii"), "filename": a.filename,
                "type": a.mime, "disposition": "attachment"} for a in mail.attachments]
        await self._post("https://api.sendgrid.com/v3/mail/send",
                         {"Authorization": f"Bearer {self.s.sendgrid_api_key}"}, payload)

    async def _send_resend(self, mail: OutgoingEmail, recipients: list[str]) -> None:
        payload = {
            "from": formataddr((self.s.email_from_name, self._from_address())),
            "to": recipients, "subject": mail.subject, "html": mail.html, "text": mail.text,
        }
        if mail.attachments:
            payload["attachments"] = [{"filename": a.filename,
                                       "content": base64.b64encode(a.content).decode("ascii")}
                                      for a in mail.attachments]
        await self._post("https://api.resend.com/emails",
                         {"Authorization": f"Bearer {self.s.resend_api_key}"}, payload)
