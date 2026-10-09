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


def _card_email(*, tone: str, badge: str, title: str, intro: str, website_name: str, url: str, device: str,
                score_label: str, r: PerformanceResult, threshold: int, date: str, button_text: str,
                button_url: str, base_url: str) -> str:
    """Card-style alert e-mail (Performance Attention / Recovered).

    Built only from tables and inline styles, without SVG or web fonts, so it renders the
    same in Outlook (desktop, web, dark mode) and Gmail. Every dynamic value is escaped.
    """
    t = _TONES[tone]
    font = "font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
    dash = "&mdash;"
    label = f"padding:7px 0;width:110px;color:#64748b;font-size:14px;{font}"
    value = f"padding:7px 0;color:#0f172a;font-size:14px;font-weight:600;{font}"
    metrics = [("Performance Score", _v(r.performance_score), t["accent"]), ("LCP", _v(r.lcp_s, " s"), "#0f172a"),
               ("CLS", _v(r.cls), "#0f172a"), ("TBT", _v(r.tbt_ms, " ms"), "#0f172a"),
               ("FCP", _v(r.fcp_s, " s"), "#0f172a"), ("Speed Index", _v(r.speed_index_s, " s"), "#0f172a")]
    metric_rows = "".join(
        f'<tr><td style="padding:9px 16px;border-top:1px solid #e2e8f0;color:#475569;font-size:14px;{font}">{escape(k)}</td>'
        f'<td style="padding:9px 16px;border-top:1px solid #e2e8f0;color:{c};font-size:14px;font-weight:700;{font}">'
        f'{escape(v)}</td></tr>' for k, v, c in metrics)
    dashboard = (f'<a href="{escape(base_url)}" style="color:#1d4ed8;text-decoration:underline">Open dashboard</a>'
                 if base_url else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">
<title>{escape(title)}</title></head>
<body style="margin:0;padding:0;background:#eef2f7;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef2f7;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
 style="max-width:560px;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;">

<!-- header: brand + badge -->
<tr><td style="padding:18px 24px;border-bottom:1px solid #eef2f7;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
  <td style="{font}font-size:15px;font-weight:700;color:#0f172a;">
   <span style="display:inline-block;width:22px;height:22px;line-height:22px;text-align:center;border-radius:6px;background:#1d4ed8;color:#ffffff;font-size:13px;font-weight:800;vertical-align:middle;">W</span>
   <span style="vertical-align:middle;">&nbsp;Website Performance Monitor</span></td>
  <td align="right" style="{font}">
   <span style="display:inline-block;padding:5px 12px;border-radius:999px;background:{t['badge_bg']};color:{t['accent']};font-size:11px;font-weight:700;letter-spacing:.4px;">{t['icon']}&nbsp;{escape(badge)}</span></td>
 </tr></table>
</td></tr>

<!-- headline box -->
<tr><td style="padding:20px 24px 4px;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="background:{t['box_bg']};border:1px solid {t['box_border']};border-radius:10px;"><tr>
  <td width="52" valign="top" style="padding:16px 0 16px 16px;">
   <div style="width:36px;height:36px;line-height:36px;border-radius:18px;background:{t['accent']};color:#ffffff;text-align:center;font-size:20px;font-weight:800;{font}">{t['symbol']}</div></td>
  <td style="padding:16px 16px 16px 12px;{font}">
   <div style="font-size:19px;line-height:25px;font-weight:700;color:#0f172a;">{escape(title)} {dash} {escape(website_name)}</div>
   <div style="padding-top:6px;font-size:14px;color:#334155;">{escape(intro)}</div></td>
 </tr></table>
</td></tr>

<!-- details -->
<tr><td style="padding:12px 24px 0;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr><td style="{label}">Website</td><td style="{value}">{escape(website_name)}</td></tr>
  <tr><td style="{label}">URL</td><td style="{value}"><a href="{escape(url)}" style="color:#1d4ed8;text-decoration:underline;word-break:break-all;">{escape(url)}</a></td></tr>
  <tr><td style="{label}">Device</td><td style="{value}">{escape(device)}</td></tr>
 </table>
</td></tr>

<!-- score + threshold cards -->
<tr><td style="padding:14px 24px 0;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
  <td width="50%" valign="top" style="padding-right:6px;">
   <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{t['box_bg']};border-radius:10px;"><tr>
    <td style="padding:14px 16px;{font}"><div style="font-size:13px;color:#475569;">{escape(score_label)}</div>
     <div style="padding-top:4px;font-size:28px;line-height:32px;font-weight:800;color:{t['accent']};">{escape(_v(r.performance_score))}<span style="font-size:15px;font-weight:600;color:{t['accent']};"> / 100</span></div></td>
   </tr></table></td>
  <td width="50%" valign="top" style="padding-left:6px;">
   <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f1f5f9;border-radius:10px;"><tr>
    <td style="padding:14px 16px;{font}"><div style="font-size:13px;color:#475569;">Threshold</div>
     <div style="padding-top:4px;font-size:28px;line-height:32px;font-weight:800;color:#0f172a;">{threshold}</div></td>
   </tr></table></td>
 </tr></table>
</td></tr>

<!-- date -->
<tr><td style="padding:14px 24px 0;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr><td style="{label}">Date</td><td style="{value}">{escape(date)}</td></tr>
 </table>
</td></tr>

<!-- metrics -->
<tr><td style="padding:12px 24px 0;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="border:1px solid #e2e8f0;border-radius:10px;border-collapse:separate;">
  <tr><td colspan="2" style="padding:11px 16px;background:#f8fafc;border-radius:10px 10px 0 0;color:#0f172a;font-size:14px;font-weight:700;{font}">Metrics</td></tr>
  {metric_rows}
 </table>
</td></tr>

<!-- button -->
<tr><td style="padding:20px 24px 4px;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
  <td align="center" bgcolor="#1d4ed8" style="border-radius:10px;">
   <a href="{escape(button_url)}" style="display:block;padding:14px 18px;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;border-radius:10px;{font}">&#8599;&nbsp; {escape(button_text)}</a></td>
 </tr></table>
</td></tr>

<!-- footer -->
<tr><td style="padding:16px 24px 20px;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid #eef2f7;"><tr>
  <td style="padding-top:14px;color:#64748b;font-size:12px;{font}">Sent by Website Performance Monitor</td>
  <td align="right" style="padding-top:14px;font-size:12px;{font}">{dashboard}</td>
 </tr></table>
</td></tr>

</table>
</td></tr></table>
</body></html>"""


_TONES = {
    "attention": {"accent": "#dc2626", "badge_bg": "#fee2e2", "box_bg": "#fdecec", "box_border": "#f9caca",
                  "icon": "&#9888;", "symbol": "!"},
    "recovered": {"accent": "#059669", "badge_bg": "#d1fae5", "box_bg": "#e8f8f1", "box_border": "#b7ebd5",
                  "icon": "&#10003;", "symbol": "&#10003;"},
}


def alert_email(r: PerformanceResult, website_name: str, url: str, threshold: int, tz: ZoneInfo,
                base_url: str) -> tuple[str, str, str]:
    date = r.tested_at.astimezone(tz).strftime("%d-%b-%Y %H:%M")
    link = psi_report_link(url, r.strategy)
    subject = f"Performance Attention Required - {website_name}"
    html = _card_email(tone="attention", badge="ATTENTION REQUIRED", title="Performance Attention Required",
                       intro="A monitored page scored below its performance threshold.", website_name=website_name,
                       url=url, device=r.strategy.capitalize(), score_label="Performance Score", r=r,
                       threshold=threshold, date=date, button_text="Review in PageSpeed Insights",
                       button_url=link, base_url=base_url)
    text = (f"Performance Attention Required\n\nWebsite: {website_name}\nURL: {url}\nDevice: {r.strategy.capitalize()}\n"
            f"Performance Score: {_v(r.performance_score)}\nThreshold: {threshold}\n\nMetrics:\n"
            f"LCP: {_v(r.lcp_s, ' s')}\nCLS: {_v(r.cls)}\nTBT: {_v(r.tbt_ms, ' ms')}\nFCP: {_v(r.fcp_s, ' s')}\n"
            f"Speed Index: {_v(r.speed_index_s, ' s')}\n\nDate: {date}\nPageSpeed Insights: {link}\n")
    return subject, html, text


def recovery_email(r: PerformanceResult, website_name: str, url: str, threshold: int, tz: ZoneInfo,
                   base_url: str) -> tuple[str, str, str]:
    date = r.tested_at.astimezone(tz).strftime("%d-%b-%Y %H:%M")
    subject = f"Performance Recovered - {website_name} ({r.strategy.capitalize()})"
    html = _card_email(tone="recovered", badge="RECOVERED", title="Performance Recovered",
                       intro="This page is back at or above its performance threshold.", website_name=website_name,
                       url=url, device=r.strategy.capitalize(), score_label="Performance Score", r=r,
                       threshold=threshold, date=date, button_text="View in PageSpeed Insights",
                       button_url=psi_report_link(url, r.strategy), base_url=base_url)
    text = (f"{subject}\n\nURL: {url}\nDevice: {r.strategy.capitalize()}\nPerformance Score: "
            f"{_v(r.performance_score)} (threshold {threshold})\nDate: {date}\n")
    return subject, html, text


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
