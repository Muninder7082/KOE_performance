"""HTML + plain-text e-mail bodies. Every dynamic value is HTML-escaped."""
from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from ..models import PerformanceResult
from .pagespeed import psi_report_link

_STATUS_COLORS = {"GOOD": "#047857", "ATTENTION": "#b45309", "FAILED": "#b91c1c", "PENDING": "#475569"}


def _v(value, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        value = (f"{value:.2f}".rstrip("0").rstrip(".") or "0") if suffix != "" else f"{value:g}"
    return f"{value}{suffix}"


def _wrap(title: str, body: str, footer: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;padding:24px;background:#f1f5f9;font-family:Segoe UI,Arial,sans-serif;color:#0f172a">
<table role="presentation" width="100%" style="max-width:760px;margin:0 auto;background:#fff;border-radius:10px;border:1px solid #e2e8f0">
<tr><td style="padding:20px 24px;border-bottom:1px solid #e2e8f0"><h1 style="margin:0;font-size:19px">{escape(title)}</h1></td></tr>
<tr><td style="padding:20px 24px;font-size:14px;line-height:1.5">{body}</td></tr>
<tr><td style="padding:14px 24px;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b">{footer}</td></tr>
</table></body></html>"""


def _footer(base_url: str) -> str:
    link = f' &middot; <a href="{escape(base_url)}">Open dashboard</a>' if base_url else ""
    return f"Sent by Website Performance Monitor{link}"


def _metrics_table(r: PerformanceResult) -> str:
    rows = [("Performance Score", _v(r.performance_score)), ("LCP", _v(r.lcp_s, " s")),
            ("CLS", _v(r.cls)), ("TBT", _v(r.tbt_ms, " ms")), ("FCP", _v(r.fcp_s, " s")),
            ("Speed Index", _v(r.speed_index_s, " s"))]
    cells = "".join(
        f'<tr><td style="padding:6px 10px;border:1px solid #e2e8f0;color:#475569">{escape(k)}</td>'
        f'<td style="padding:6px 10px;border:1px solid #e2e8f0;font-weight:600">{escape(v)}</td></tr>' for k, v in rows)
    return f'<table style="border-collapse:collapse;margin:8px 0 16px">{cells}</table>'


def alert_email(r: PerformanceResult, website_name: str, url: str, threshold: int, tz: ZoneInfo,
                base_url: str) -> tuple[str, str, str]:
    date = r.tested_at.astimezone(tz).strftime("%d-%b-%Y %H:%M")
    link = psi_report_link(url, r.strategy)
    subject = f"Performance Attention Required - {website_name}"
    body = f"""<p>A monitored page scored below its performance threshold.</p>
<table style="border-collapse:collapse;margin-bottom:12px">
<tr><td style="padding:4px 12px 4px 0;color:#475569">Website</td><td><strong>{escape(website_name)}</strong></td></tr>
<tr><td style="padding:4px 12px 4px 0;color:#475569">URL</td><td><a href="{escape(url)}">{escape(url)}</a></td></tr>
<tr><td style="padding:4px 12px 4px 0;color:#475569">Device</td><td>{escape(r.strategy.capitalize())}</td></tr>
<tr><td style="padding:4px 12px 4px 0;color:#475569">Performance Score</td><td style="color:#b91c1c;font-weight:700">{escape(_v(r.performance_score))}</td></tr>
<tr><td style="padding:4px 12px 4px 0;color:#475569">Threshold</td><td>{threshold}</td></tr>
<tr><td style="padding:4px 12px 4px 0;color:#475569">Date</td><td>{escape(date)}</td></tr>
</table>
<h3 style="font-size:15px;margin:12px 0 4px">Metrics</h3>{_metrics_table(r)}
<p><a href="{escape(link)}" style="display:inline-block;background:#0f62fe;color:#fff;padding:9px 16px;border-radius:6px;text-decoration:none">Review in PageSpeed Insights</a></p>"""
    text = (f"Performance Attention Required\n\nWebsite: {website_name}\nURL: {url}\nDevice: {r.strategy.capitalize()}\n"
            f"Performance Score: {_v(r.performance_score)}\nThreshold: {threshold}\n\nMetrics:\n"
            f"LCP: {_v(r.lcp_s, ' s')}\nCLS: {_v(r.cls)}\nTBT: {_v(r.tbt_ms, ' ms')}\nFCP: {_v(r.fcp_s, ' s')}\n"
            f"Speed Index: {_v(r.speed_index_s, ' s')}\n\nDate: {date}\nPageSpeed Insights: {link}\n")
    return subject, _wrap(subject, body, _footer(base_url)), text


def recovery_email(r: PerformanceResult, website_name: str, url: str, threshold: int, tz: ZoneInfo,
                   base_url: str) -> tuple[str, str, str]:
    date = r.tested_at.astimezone(tz).strftime("%d-%b-%Y %H:%M")
    subject = f"Performance Recovered - {website_name} ({r.strategy.capitalize()})"
    body = (f"<p><strong>{escape(website_name)}</strong> (<a href=\"{escape(url)}\">{escape(url)}</a>) is back above its "
            f"threshold on <strong>{escape(r.strategy.capitalize())}</strong>.</p>"
            f"<p>Performance Score: <strong style=\"color:#047857\">{escape(_v(r.performance_score))}</strong> "
            f"(threshold {threshold}) &middot; {escape(date)}</p>{_metrics_table(r)}")
    text = (f"{subject}\n\nURL: {url}\nDevice: {r.strategy.capitalize()}\nPerformance Score: "
            f"{_v(r.performance_score)} (threshold {threshold})\nDate: {date}\n")
    return subject, _wrap(subject, body, _footer(base_url)), text


def daily_report_email(ov, tz: ZoneInfo, now: datetime, base_url: str, attached: bool) -> tuple[str, str, str]:
    day = now.astimezone(tz).strftime("%d-%b-%Y")
    subject = f"Daily Website Performance Report - {day}"
    summary = [
        ("Total Websites", ov.total_websites), ("Active Websites", ov.active_websites),
        ("Successful Tests (today)", ov.successful_today), ("Failed Tests (today)", ov.failed_today),
        ("Average Desktop Performance", _v(ov.avg_desktop)), ("Average Mobile Performance", _v(ov.avg_mobile)),
        ("Pages Requiring Attention", ov.attention + ov.failed_websites),
    ]
    cards = "".join(
        f'<tr><td style="padding:5px 14px 5px 0;color:#475569">{escape(k)}</td><td style="font-weight:600">{escape(str(v))}</td></tr>'
        for k, v in summary)
    th = 'style="text-align:left;padding:7px 9px;background:#0f2b46;color:#fff;font-size:12px"'
    td = 'style="padding:7px 9px;border-bottom:1px solid #e2e8f0;font-size:13px"'
    rows_html, rows_text = [], []
    for row in ov.rows:
        w = row["website"]
        if not w.is_active:
            continue
        d, m = row["desktop"], row["mobile"]
        ds = _v(d.performance_score) if d and d.status == "success" else ("ERR" if d else "—")
        ms = _v(m.performance_score) if m and m.status == "success" else ("ERR" if m else "—")
        last = row["last_checked"].astimezone(tz).strftime("%d-%b-%Y %H:%M") if row["last_checked"] else "Never"
        color = _STATUS_COLORS.get(row["status"], "#475569")
        rows_html.append(
            f"<tr><td {td}>{escape(w.name)}</td><td {td}><a href=\"{escape(w.url)}\">{escape(w.url)}</a></td>"
            f"<td {td}>{escape(ds)}</td><td {td}>{escape(ms)}</td>"
            f"<td {td}><strong style=\"color:{color}\">{escape(row['status'])}</strong></td><td {td}>{escape(last)}</td></tr>")
        rows_text.append(f"{w.name} | {w.url} | {ds} | {ms} | {row['status']} | {last}")
    table = (f"<table style=\"border-collapse:collapse;width:100%\"><tr><th {th}>Website</th><th {th}>URL</th>"
             f"<th {th}>Desktop</th><th {th}>Mobile</th><th {th}>Status</th><th {th}>Last Checked</th></tr>"
             + ("".join(rows_html) or f"<tr><td {td} colspan=6>No active websites.</td></tr>") + "</table>")
    note = ("<p style=\"color:#475569\">The complete historical workbook <strong>website-performance.xlsx</strong> is attached.</p>"
            if attached else "<p style=\"color:#b91c1c\">The Excel workbook could not be attached — see Email Logs.</p>")
    body = f"<h3 style=\"font-size:15px;margin:0 0 6px\">Summary</h3><table>{cards}</table><h3 style=\"font-size:15px;margin:18px 0 6px\">Websites</h3>{table}{note}"
    text = (f"{subject}\n\n" + "\n".join(f"{k}: {v}" for k, v in summary)
            + "\n\nWebsite | URL | Desktop | Mobile | Status | Last Checked\n" + "\n".join(rows_text) + "\n")
    return subject, _wrap(subject, body, _footer(base_url)), text


def test_email(base_url: str) -> tuple[str, str, str]:
    subject = "Test Email - Website Performance Monitor"
    body = "<p>This is a test e-mail. Your e-mail settings are working.</p>"
    return subject, _wrap(subject, body, _footer(base_url)), "This is a test e-mail. Your e-mail settings are working.\n"
