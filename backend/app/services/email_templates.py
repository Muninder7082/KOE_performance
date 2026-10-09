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


def _score_ring(r, threshold: int) -> str:
    """Score inside a coloured circle (green >= 90, orange 50-89, red < 50)."""
    font = "font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
    if r is None:
        value, ring, color = "&mdash;", "#cbd5e1", "#64748b"
    elif r.status != "success" or r.performance_score is None:
        value, ring, color = "ERR", "#dc2626", "#dc2626"
    else:
        s = r.performance_score
        value = escape(str(s))
        ring = "#16a34a" if s >= 90 else "#f59e0b" if s >= 50 else "#dc2626"
        color = "#0f172a"
    return (f'<div style="width:34px;height:34px;line-height:34px;border-radius:50%;border:3px solid {ring};'
            f'text-align:center;margin:0 auto;font-size:13px;font-weight:700;color:{color};{font}">{value}</div>')


_STATUS_PILL = {
    "GOOD": ("#dcfce7", "#15803d", "&#10004;&nbsp;GOOD"),
    "ATTENTION": ("#fef3c7", "#b45309", "&#9888;&nbsp;ATTENTION"),
    "FAILED": ("#fee2e2", "#b91c1c", "&#10006;&nbsp;FAILED"),
    "PENDING": ("#f1f5f9", "#475569", "PENDING"),
}


def _insight_sections(ins: dict | None, font: str, card: str) -> tuple[str, str]:
    """HTML + text for: New problems today, Changes since the previous test, Lowest scores."""
    if not ins:
        return "", ""
    td = f'style="padding:9px 10px;border-bottom:1px solid #eef2f7;font-size:13px;color:#0f172a;{font}"'
    th = (f'style="padding:9px 10px;background:#f8fafc;border-bottom:1px solid #e2e8f0;text-align:left;'
          f'font-size:12px;font-weight:700;color:#334155;{font}"')

    def device(i):
        return (f'<span style="display:inline-block;margin-left:6px;padding:1px 7px;border-radius:999px;'
                f'background:#f1f5f9;color:#475569;font-size:11px;font-weight:600;">{escape(i["device"])}</span>')

    def score(v, threshold):
        if v is None:
            return "&mdash;"
        c = "#16a34a" if v >= 90 else "#f59e0b" if v >= 50 else "#dc2626"
        return f'<strong style="color:{c};">{v}</strong>'

    def block(icon, title, sub, header, rows, empty):
        body = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                f'style="border:1px solid #e2e8f0;border-radius:10px;border-collapse:separate;"><tr>{header}</tr>'
                + "".join(rows) + "</table>") if rows else (
                f'<div style="padding:12px 14px;background:#f0fdf4;border-radius:10px;color:#166534;'
                f'font-size:13px;{font}">&#10004;&nbsp; {empty}</div>')
        return (f'<tr><td {card}><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
                f'<tr><td style="padding:16px 20px 10px;{font}"><div style="font-size:16px;font-weight:800;color:#0f172a;">'
                f'{icon}&nbsp; {title}</div><div style="font-size:12px;color:#64748b;">{sub}</div></td></tr>'
                f'<tr><td style="padding:0 20px 18px;">{body}</td></tr></table></td></tr>'
                '<tr><td style="height:14px;line-height:14px;font-size:0;">&nbsp;</td></tr>')

    new = ins.get("new_problems", [])
    new_rows = [f'<tr><td {td}><strong>{escape(i["name"])}</strong>{device(i)}<br>'
                f'<a href="{escape(i["url"])}" style="color:#1d4ed8;font-size:12px;word-break:break-all;">{escape(i["url"])}</a></td>'
                f'<td {td}>{score(i["previous"], i["threshold"])} &rarr; {score(i["score"], i["threshold"])}'
                f' <span style="color:#64748b;font-size:12px;">/ {i["threshold"]}</span></td></tr>' for i in new]
    changes = ins.get("changes", [])
    shown = changes[:10]
    ch_rows = []
    for i in shown:
        up = i["delta"] > 0
        ch_rows.append(
            f'<tr><td {td}>{escape(i["name"])}{device(i)}</td>'
            f'<td {td}>{score(i["previous"], i["threshold"])} &rarr; {score(i["score"], i["threshold"])}</td>'
            f'<td {td}><strong style="color:{"#16a34a" if up else "#dc2626"};">{"&#9650;" if up else "&#9660;"}'
            f'&nbsp;{abs(i["delta"])}</strong></td></tr>')
    if len(changes) > len(shown):
        ch_rows.append(f'<tr><td colspan="3" {td}><span style="color:#64748b;">+ {len(changes) - len(shown)} more '
                       f'(see the Excel file)</span></td></tr>')
    low = ins.get("lowest", [])
    low_rows = [f'<tr><td {td}>{n}</td><td {td}>{escape(i["name"])}{device(i)}</td>'
                f'<td {td}>{score(i["score"], i["threshold"])} <span style="color:#64748b;font-size:12px;">/ {i["threshold"]}</span></td>'
                f'<td {td}>{escape(_v(i["lcp"], " s"))}</td></tr>' for n, i in enumerate(low, 1)]

    html = (block("&#128680;", "New problems today", "Pages that dropped below their threshold in today's test",
                  f'<th {th}>Page</th><th {th}>Previous &rarr; Now</th>', new_rows, "No new problems today.")
            + block("&#8645;", "Changes since the previous test", "Score difference per page and device (largest drops first)",
                    f'<th {th}>Page</th><th {th}>Previous &rarr; Now</th><th {th}>Change</th>', ch_rows,
                    "No score changes since the previous test.")
            + (block("&#128201;", "Lowest scores", "The three weakest results right now",
                     f'<th {th}>#</th><th {th}>Page</th><th {th}>Score</th><th {th}>LCP</th>', low_rows, "")
               if low_rows else ""))

    lines = ["", "New problems today:"]
    lines += [f"- {i['name']} ({i['device']}): {i['previous'] if i['previous'] is not None else '-'} -> {i['score']}"
              f" / {i['threshold']}" for i in new] or ["- none"]
    lines += ["", "Changes since the previous test:"]
    lines += [f"- {i['name']} ({i['device']}): {i['previous']} -> {i['score']} ({'+' if i['delta'] > 0 else ''}{i['delta']})"
              for i in changes] or ["- none"]
    if low:
        lines += ["", "Lowest scores:"] + [f"{n}. {i['name']} ({i['device']}): {i['score']} / {i['threshold']},"
                                           f" LCP {_v(i['lcp'], ' s')}" for n, i in enumerate(low, 1)]
    return html, "\n".join(lines) + "\n"


def daily_report_email(ov, tz: ZoneInfo, now: datetime, base_url: str, attached: bool,
                       insights: dict | None = None) -> tuple[str, str, str]:
    font = "font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
    day = now.astimezone(tz).strftime("%d-%b-%Y")
    subject = f"Daily Website Performance Report - {day}"

    th = (f'style="padding:10px 8px;background:#f8fafc;border-bottom:1px solid #e2e8f0;text-align:left;'
          f'font-size:12px;font-weight:700;color:#334155;{font}"')
    thc = th.replace("text-align:left", "text-align:center")
    td = f'style="padding:10px 8px;border-bottom:1px solid #eef2f7;font-size:13px;color:#0f172a;{font}"'
    tdc = td.replace("padding:10px 8px;", "padding:10px 8px;text-align:center;")
    rows_html, rows_text, n = [], [], 0
    for row in ov.rows:
        w = row["website"]
        if not w.is_active:
            continue
        n += 1
        d, m = row["desktop"], row["mobile"]
        bg, fg, label = _STATUS_PILL.get(row["status"], _STATUS_PILL["PENDING"])
        last = row["last_checked"].astimezone(tz).strftime("%d-%b-%Y<br>%H:%M") if row["last_checked"] else "Never"
        rows_html.append(
            f'<tr><td {td}>{n}</td><td {td}>{escape(w.name)}</td>'
            f'<td {td}><a href="{escape(w.url)}" style="color:#1d4ed8;text-decoration:underline;word-break:break-all;">'
            f'{escape(w.url)}</a>&nbsp;<span style="color:#1d4ed8;">&#8599;</span></td>'
            f'<td {tdc}>{_score_ring(d, w.threshold)}</td><td {tdc}>{_score_ring(m, w.threshold)}</td>'
            f'<td {td}><span style="display:inline-block;padding:4px 9px;border-radius:6px;background:{bg};color:{fg};'
            f'font-size:11px;font-weight:700;white-space:nowrap;">{label}</span></td>'
            f'<td {td}><span style="font-size:12px;color:#334155;white-space:nowrap;">{last}</span></td></tr>')
        ds = _v(d.performance_score) if d and d.status == "success" else ("ERR" if d else "—")
        ms = _v(m.performance_score) if m and m.status == "success" else ("ERR" if m else "—")
        rows_text.append(f"{w.name} | {w.url} | {ds} | {ms} | {row['status']} | {last.replace('<br>', ' ')}")
    if not rows_html:
        rows_html.append(f'<tr><td colspan="7" {td}>No active websites.</td></tr>')

    dot = 'display:inline-block;width:8px;height:8px;border-radius:4px;margin:0 4px 0 10px;'
    legend = (f'<span style="font-size:11px;color:#475569;{font}"><span style="{dot}background:#16a34a;"></span>Good (&ge; 90)'
              f'<span style="{dot}background:#f59e0b;"></span>Needs Attention (50 - 89)'
              f'<span style="{dot}background:#dc2626;"></span>Poor (&lt; 50)</span>')
    note = ('The complete historical workbook <strong style="color:#1d4ed8;">website-performance.xlsx</strong> is attached.'
            if attached else '<span style="color:#b91c1c;">The Excel workbook could not be attached &mdash; see Email Logs.</span>')
    button = (f'<td align="right"><table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
              f'<td bgcolor="#1d4ed8" style="border-radius:8px;"><a href="{escape(base_url)}" style="display:block;'
              f'padding:11px 20px;color:#ffffff;font-size:14px;font-weight:700;text-decoration:none;{font}">'
              f'&#128202;&nbsp; Open dashboard &rarr;</a></td></tr></table></td>' if base_url else "")
    card = 'style="background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;"'
    insights_html, insights_text = _insight_sections(insights, font, card)

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">
<title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:#eef2f7;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef2f7;">
<tr><td align="center" style="padding:20px 10px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:720px;">

<!-- header -->
<tr><td bgcolor="#1d4ed8" style="background:#1d4ed8;background-image:linear-gradient(135deg,#2563eb,#1e40af);border-radius:14px;padding:22px 24px;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
  <td width="58" valign="middle"><div style="width:46px;height:46px;line-height:46px;border-radius:12px;background:#3b82f6;text-align:center;font-size:24px;">&#128202;</div></td>
  <td valign="middle" style="{font}">
   <div style="font-size:22px;line-height:28px;font-weight:800;color:#ffffff;">Daily Website Performance Report</div>
   <div style="font-size:14px;color:#dbeafe;">{escape(day)}</div></td>
  <td align="right" valign="middle">
   <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="background:#2b5fd9;border:1px solid #6b93ee;border-radius:10px;"><tr>
    <td style="padding:8px 12px;font-size:16px;color:#ffffff;">&#128197;</td>
    <td style="padding:8px 14px 8px 0;{font}"><div style="font-size:13px;font-weight:700;color:#ffffff;">{escape(day)}</div>
     <div style="font-size:11px;color:#dbeafe;">Daily Report</div></td></tr></table></td>
 </tr></table>
</td></tr>
<tr><td style="height:14px;line-height:14px;font-size:0;">&nbsp;</td></tr>

{insights_html}
<!-- details -->
<tr><td {card}>
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr><td style="padding:18px 20px 10px;{font}">
   <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td style="{font}"><div style="font-size:16px;font-weight:800;color:#0f172a;">&#9776;&nbsp; Website Details</div>
     <div style="font-size:12px;color:#64748b;">Performance results for all monitored pages</div></td>
    <td align="right" valign="bottom">{legend}</td></tr></table></td></tr>
  <tr><td style="padding:0 20px;">
   <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0;border-radius:10px;border-collapse:separate;">
    <tr><th {th}>#</th><th {th}>Website</th><th {th}>URL</th><th {thc}>Desktop</th><th {thc}>Mobile</th><th {th}>Status</th><th {th}>Last Checked</th></tr>
    {''.join(rows_html)}
   </table></td></tr>
  <tr><td style="padding:14px 20px 20px;">
   <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eff6ff;border-radius:10px;"><tr>
    <td style="padding:12px 14px;font-size:13px;color:#1e3a8a;{font}">&#128206;&nbsp; {note}</td></tr></table></td></tr>
 </table>
</td></tr>
<tr><td style="height:14px;line-height:14px;font-size:0;">&nbsp;</td></tr>

<!-- footer -->
<tr><td {card}>
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
  <td style="padding:16px 20px;font-size:13px;color:#475569;{font}">&#9993;&nbsp; Sent by Website Performance Monitor</td>
  {button.replace('<td align="right">', '<td align="right" style="padding:12px 20px;">')}
 </tr></table>
</td></tr>

</table></td></tr></table></body></html>"""

    text = (f"{subject}\n" + insights_text
            + "\nWebsite | URL | Desktop | Mobile | Status | Last Checked\n" + "\n".join(rows_text) + "\n"
            + ("\nThe complete historical workbook website-performance.xlsx is attached.\n" if attached
               else "\nThe Excel workbook could not be attached - see Email Logs.\n")
            + (f"\nDashboard: {base_url}\n" if base_url else ""))
    return subject, html, text


def test_email(base_url: str) -> tuple[str, str, str]:
    subject = "Test Email - Website Performance Monitor"
    body = "<p>This is a test e-mail. Your e-mail settings are working.</p>"
    return subject, _wrap(subject, body, _footer(base_url)), "This is a test e-mail. Your e-mail settings are working.\n"


# ---- One combined alert e-mail for a whole run ----------------------------------------------
def alerts_digest_email(attention: list[dict], recovered: list[dict], tz: ZoneInfo,
                        base_url: str) -> tuple[str, str, str]:
    """One e-mail for all pages of a run. Items: {"result", "name", "url", "threshold"}.

    A single page/device keeps the detailed card layout; several are listed one card each.
    """
    if len(attention) == 1 and not recovered:
        i = attention[0]
        return alert_email(i["result"], i["name"], i["url"], i["threshold"], tz, base_url)
    if len(recovered) == 1 and not attention:
        i = recovered[0]
        return recovery_email(i["result"], i["name"], i["url"], i["threshold"], tz, base_url)

    font = "font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
    if attention:
        tone, badge = _TONES["attention"], "ATTENTION REQUIRED"
        pages = sorted({i["name"] for i in attention})
        what = pages[0] if len(pages) == 1 else f"{len(pages)} pages"
        subject = f"Performance Attention Required - {what}"
        headline = f"Performance Attention Required — {what}"
        new = sum(1 for i in attention if i.get("new", True))
        intro = (f"{len(attention)} result(s) on {len(pages)} page(s) are below the performance threshold"
                 f" ({new} new)" + (f"; {len(recovered)} recovered." if recovered else "."))
    else:
        tone, badge = _TONES["recovered"], "RECOVERED"
        pages = sorted({i["name"] for i in recovered})
        what = pages[0] if len(pages) == 1 else f"{len(pages)} pages"
        subject = f"Performance Recovered - {what}"
        headline = f"Performance Recovered — {what}"
        intro = f"{len(recovered)} result(s) are back at or above their threshold."
    date = max(i["result"].tested_at for i in attention + recovered).astimezone(tz).strftime("%d-%b-%Y %H:%M")

    def tag(i: dict) -> str:
        if i in recovered:
            return ""
        if i.get("new", True):
            return ('<span style="display:inline-block;margin-left:6px;padding:2px 8px;border-radius:999px;'
                    'background:#dc2626;color:#ffffff;font-size:11px;font-weight:700;">NEW</span>')
        since = i["since"].astimezone(tz).strftime("%d-%b") if i.get("since") else ""
        return ('<span style="display:inline-block;margin-left:6px;padding:2px 8px;border-radius:999px;'
                f'background:#fef3c7;color:#92400e;font-size:11px;font-weight:600;">Still below since {escape(since)}</span>')

    def card(i: dict, t: dict) -> str:
        r = i["result"]
        metrics = (f"LCP {escape(_v(r.lcp_s, ' s'))} &middot; CLS {escape(_v(r.cls))} &middot; "
                   f"TBT {escape(_v(r.tbt_ms, ' ms'))} &middot; FCP {escape(_v(r.fcp_s, ' s'))} &middot; "
                   f"Speed Index {escape(_v(r.speed_index_s, ' s'))}")
        psi = escape(psi_report_link(i["url"], r.strategy))
        return (
            '<tr><td style="padding:0 0 10px;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border:1px solid #e2e8f0;border-left:4px solid {t["accent"]};border-radius:8px;"><tr>'
            f'<td style="padding:12px 14px;{font}">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td style="{font}font-size:15px;font-weight:700;color:#0f172a;">{escape(i["name"])} '
            '<span style="display:inline-block;margin-left:6px;padding:2px 8px;border-radius:999px;'
            f'background:#f1f5f9;color:#475569;font-size:11px;font-weight:600;">{escape(r.strategy.capitalize())}</span>'
            f'{tag(i)}</td>'
            f'<td align="right" style="{font}white-space:nowrap;">'
            f'<span style="font-size:22px;font-weight:800;color:{t["accent"]};">{escape(_v(r.performance_score))}</span>'
            f'<span style="font-size:13px;color:#64748b;"> / {i["threshold"]}</span></td>'
            '</tr></table>'
            f'<div style="padding-top:4px;font-size:13px;"><a href="{escape(i["url"])}" '
            f'style="color:#1d4ed8;text-decoration:underline;word-break:break-all;">{escape(i["url"])}</a></div>'
            f'<div style="padding-top:6px;font-size:12px;color:#475569;">{metrics}</div>'
            f'<div style="padding-top:8px;font-size:13px;"><a href="{psi}" '
            'style="color:#1d4ed8;font-weight:600;text-decoration:none;">&#8599; Review in PageSpeed Insights</a></div>'
            '</td></tr></table></td></tr>')

    def section(title: str, items: list[dict], t: dict) -> str:
        if not items:
            return ""
        return (f'<tr><td style="padding:18px 24px 8px;{font}font-size:14px;font-weight:700;color:{t["accent"]};">'
                f'{escape(title)} ({len(items)})</td></tr><tr><td style="padding:0 24px;">'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
                + "".join(card(i, t) for i in items) + "</table></td></tr>")

    button = ""
    if base_url:
        button = ('<tr><td style="padding:14px 24px 4px;">'
                  '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
                  '<td align="center" bgcolor="#1d4ed8" style="border-radius:10px;">'
                  f'<a href="{escape(base_url)}" style="display:block;padding:14px 18px;color:#ffffff;font-size:15px;'
                  f'font-weight:700;text-decoration:none;border-radius:10px;{font}">&#8599;&nbsp; Open dashboard</a></td>'
                  '</tr></table></td></tr>')

    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">'
        f'<title>{escape(subject)}</title></head><body style="margin:0;padding:0;background:#eef2f7;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef2f7;">'
        '<tr><td align="center" style="padding:24px 12px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="max-width:560px;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;">'
        # header
        '<tr><td style="padding:18px 24px;border-bottom:1px solid #eef2f7;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="{font}font-size:15px;font-weight:700;color:#0f172a;">'
        '<span style="display:inline-block;width:22px;height:22px;line-height:22px;text-align:center;border-radius:6px;'
        'background:#1d4ed8;color:#ffffff;font-size:13px;font-weight:800;vertical-align:middle;">W</span>'
        '<span style="vertical-align:middle;">&nbsp;Website Performance Monitor</span></td>'
        f'<td align="right" style="{font}"><span style="display:inline-block;padding:5px 12px;border-radius:999px;'
        f'background:{tone["badge_bg"]};color:{tone["accent"]};font-size:11px;font-weight:700;letter-spacing:.4px;">'
        f'{tone["icon"]}&nbsp;{badge}</span></td></tr></table></td></tr>'
        # headline box
        '<tr><td style="padding:20px 24px 0;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{tone["box_bg"]};border:1px solid {tone["box_border"]};border-radius:10px;"><tr>'
        '<td width="52" valign="top" style="padding:16px 0 16px 16px;">'
        '<div style="width:36px;height:36px;line-height:36px;border-radius:18px;'
        f'background:{tone["accent"]};color:#ffffff;text-align:center;font-size:20px;font-weight:800;{font}">'
        f'{tone["symbol"]}</div></td>'
        f'<td style="padding:16px 16px 16px 12px;{font}">'
        f'<div style="font-size:19px;line-height:25px;font-weight:700;color:#0f172a;">{escape(headline)}</div>'
        f'<div style="padding-top:6px;font-size:14px;color:#334155;">{escape(intro)}</div>'
        f'<div style="padding-top:4px;font-size:12px;color:#64748b;">Run: {escape(date)}</div>'
        '</td></tr></table></td></tr>'
        + section("Below threshold", attention, _TONES["attention"])
        + section("Recovered", recovered, _TONES["recovered"])
        + button +
        # footer
        '<tr><td style="padding:16px 24px 20px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="border-top:1px solid #eef2f7;"><tr>'
        f'<td style="padding-top:14px;color:#64748b;font-size:12px;{font}">Sent by Website Performance Monitor</td>'
        '</tr></table></td></tr>'
        '</table></td></tr></table></body></html>')

    def line(i: dict) -> str:
        r = i["result"]
        flag = "" if i in recovered else (" [NEW]" if i.get("new", True) else " [still below]")
        return (f"- {i['name']} ({r.strategy.capitalize()}){flag}: {_v(r.performance_score)} / {i['threshold']} | "
                f"LCP {_v(r.lcp_s, ' s')}, CLS {_v(r.cls)}, TBT {_v(r.tbt_ms, ' ms')}, FCP {_v(r.fcp_s, ' s')}, "
                f"Speed Index {_v(r.speed_index_s, ' s')}\n  {i['url']}\n  {psi_report_link(i['url'], r.strategy)}")

    text = f"{headline}\n{intro}\nRun: {date}\n"
    if attention:
        text += "\nBelow threshold:\n" + "\n".join(line(i) for i in attention) + "\n"
    if recovered:
        text += "\nRecovered:\n" + "\n".join(line(i) for i in recovered) + "\n"
    if base_url:
        text += f"\nDashboard: {base_url}\n"
    return subject, html, text
