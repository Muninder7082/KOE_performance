"""Stored Lighthouse reports — the exact report behind every saved score.

The PageSpeed API response already contains the complete Lighthouse result plus
Chrome UX Report field data. A trimmed copy (the large full-page screenshot is
dropped) is gzipped and kept in the same persistent storage as the workbook, so
the dashboard can open the identical report later without running a new analysis.
Reports older than REPORT_RETENTION_DAYS are removed; scores stay forever.
"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import timedelta
from html import escape
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..clock import now_utc
from ..config import get_settings
from ..models import PerformanceResult
from .pagespeed import psi_report_link
from .storage import StorageService

log = logging.getLogger(__name__)

_FIELD_METRICS = [
    ("LARGEST_CONTENTFUL_PAINT_MS", "Largest Contentful Paint (LCP)", "ms"),
    ("INTERACTION_TO_NEXT_PAINT", "Interaction to Next Paint (INP)", "ms"),
    ("CUMULATIVE_LAYOUT_SHIFT_SCORE", "Cumulative Layout Shift (CLS)", "cls"),
    ("FIRST_CONTENTFUL_PAINT_MS", "First Contentful Paint (FCP)", "ms"),
    ("EXPERIMENTAL_TIME_TO_FIRST_BYTE", "Time to First Byte (TTFB)", "ms"),
]
_CATEGORY = {"FAST": ("Good", "#0c7a43"), "AVERAGE": ("Needs improvement", "#b45309"),
             "SLOW": ("Poor", "#c5221f"), "NONE": ("No data", "#5f6368")}


def slim(data: dict) -> dict | None:
    """Keep what the PageSpeed report shows; drop the very large full-page screenshot."""
    lr = data.get("lighthouseResult")
    if not isinstance(lr, dict):
        return None
    lr = dict(lr)
    lr.pop("fullPageScreenshot", None)
    audits = dict(lr.get("audits") or {})
    audits.pop("full-page-screenshot", None)
    lr["audits"] = audits
    return {
        "lighthouseResult": lr,
        "loadingExperience": data.get("loadingExperience"),
        "originLoadingExperience": data.get("originLoadingExperience"),
    }


def _key(result: PerformanceResult) -> str:
    t = result.tested_at
    return f"reports/{t:%Y}/{t:%m}/{result.id}-{result.strategy}.json.gz"


class LighthouseReportService:
    def __init__(self, sf: async_sessionmaker[AsyncSession], storage: StorageService):
        self.sf = sf
        self.storage = storage

    async def save(self, result_id: int, report: dict) -> None:
        """Best effort: a storage failure never fails the test itself."""
        try:
            async with self.sf() as session:
                r = await session.get(PerformanceResult, result_id)
                if r is None:
                    return
                key = _key(r)
                payload = gzip.compress(json.dumps(report, separators=(",", ":")).encode("utf-8"), 6)
                await self.storage.put_object(key, payload)
                r.report_key = key
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not store Lighthouse report for result %s: %s", result_id, exc)

    async def load(self, result: PerformanceResult) -> dict | None:
        if not result.report_key:
            return None
        raw = await self.storage.get_object(result.report_key)
        if raw is None:
            return None
        return json.loads(gzip.decompress(raw))

    async def purge(self) -> int:
        days = get_settings().report_retention_days
        if days <= 0:
            return 0
        cutoff = now_utc() - timedelta(days=days)
        async with self.sf() as session:
            rows = (await session.execute(
                select(PerformanceResult.id, PerformanceResult.report_key)
                .where(PerformanceResult.report_key.is_not(None), PerformanceResult.tested_at < cutoff)
                .limit(5000))).all()
        if not rows:
            return 0
        await self.storage.delete_objects([k for _, k in rows])
        async with self.sf() as session:
            await session.execute(update(PerformanceResult).where(PerformanceResult.id.in_([i for i, _ in rows]))
                                  .values(report_key=None))
            await session.commit()
        log.info("Removed %d Lighthouse reports older than %d days", len(rows), days)
        return len(rows)


VIEWER_URL = "https://googlechrome.github.io/lighthouse/viewer/"


def report_signature(result_id: int) -> str:
    """Unguessable signature so a per-test report link can be opened without logging in
    (e.g. from the Excel file) while other result ids cannot be enumerated."""
    import hashlib
    import hmac

    key = get_settings().secret_key.encode("utf-8")
    return hmac.new(key, f"report:{result_id}".encode(), hashlib.sha256).hexdigest()[:24]


def verify_signature(result_id: int, sig: str) -> bool:
    import hmac

    return hmac.compare_digest(report_signature(result_id), sig or "")


def public_report_link(result: PerformanceResult) -> str | None:
    """Short per-test link that opens this test's report on Google Lighthouse Viewer.
    (The viewer URL itself carries the whole report and is far too long for an Excel cell.)"""
    base = get_settings().public_base_url.rstrip("/")
    if not base or result.status != "success" or not result.report_key:
        return None
    return f"{base}/api/public/report/{result.id}/{report_signature(result.id)}"


def viewer_redirect_page(report: dict) -> str:
    """Tiny page that sends the browser to Google Lighthouse Viewer with the stored report."""
    url = viewer_url(report)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
            '<title>Opening Lighthouse Viewer…</title></head><body style="font-family:Segoe UI,Arial,sans-serif;padding:40px">'
            '<p>Opening the saved report on Google Lighthouse Viewer…</p>'
            f'<script type="application/json" id="viewer-url">{json.dumps(url)}</script>'
            '<script src="/lighthouse-assets/open-viewer.js"></script></body></html>')


def viewer_url(report: dict) -> str:
    """Link that opens this exact report in Google's official Lighthouse Viewer.

    Same encoding as the report's own "Open in Viewer" menu item: gzip + base64 of
    {"lhr": ...} in the URL fragment. The fragment is never sent to any server; the
    viewer decodes it in the browser.
    """
    import base64

    lhr = report.get("lighthouseResult") or {}
    packed = gzip.compress(json.dumps({"lhr": lhr}, separators=(",", ":")).encode("utf-8"), 9)
    return f"{VIEWER_URL}?gzip=1#{base64.b64encode(packed).decode('ascii')}"


# ---- HTML ---------------------------------------------------------------------------------
def _fmt_field(value, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "cls":
        return f"{value / 100:.2f}"
    return f"{value / 1000:.1f} s" if value >= 1000 else f"{int(value)} ms"


def _field_section(title: str, exp: dict | None) -> str:
    metrics = (exp or {}).get("metrics") or {}
    if not metrics:
        return (f'<div class="fd"><h3>{escape(title)}</h3><p class="muted">The Chrome UX Report has no real-user '
                'data for this page yet (not enough traffic).</p></div>')
    overall = _CATEGORY.get((exp or {}).get("overall_category", "NONE"), _CATEGORY["NONE"])
    cells = []
    for key, label, kind in _FIELD_METRICS:
        m = metrics.get(key)
        if not m:
            continue
        cat_label, color = _CATEGORY.get(m.get("category", "NONE"), _CATEGORY["NONE"])
        cells.append(f'<div class="m"><div class="ml">{escape(label)}</div>'
                     f'<div class="mv" style="color:{color}">{escape(_fmt_field(m.get("percentile"), kind))}</div>'
                     f'<div class="mc" style="color:{color}">{escape(cat_label)}</div></div>')
    return (f'<div class="fd"><h3>{escape(title)} <span class="badge" style="background:{overall[1]}">'
            f'Core Web Vitals: {escape(overall[0])}</span></h3><div class="grid">{"".join(cells)}</div>'
            '<p class="muted">75th percentile of real Chrome users over the previous 28 days (Chrome UX Report).</p></div>')


_ICONS = {
    "mobile": '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M16 1H8a3 3 0 0 0-3 3v16a3 3 0 0 0 3 3h8a3 3 0 0 0 3-3V4a3 3 0 0 0-3-3zm1 19a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v16zm-5-1.5a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5z"/></svg>',
    "desktop": '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M20 3H4a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h6v2H8v2h8v-2h-2v-2h6a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm0 13H4V5h16v11z"/></svg>',
}


def _score_color(score) -> str:
    if score is None:
        return "#5f6368"
    return "#0c7a43" if score >= 90 else "#c33300" if score < 50 else "#b45309"


def _tabs(result: PerformanceResult, siblings: dict) -> str:
    """PageSpeed-style Mobile / Desktop tabs. siblings[strategy] = PerformanceResult | None."""
    items = []
    for strategy in ("mobile", "desktop"):
        r = result if strategy == result.strategy else siblings.get(strategy)
        label = strategy.capitalize()
        score = ""
        if r is not None and r.performance_score is not None:
            score = f'<span class="sc" style="color:{_score_color(r.performance_score)}">{r.performance_score}</span>'
        elif r is not None and r.status != "success":
            score = '<span class="sc" style="color:#c5221f">ERR</span>'
        inner = f"{_ICONS[strategy]}<span>{label}</span>{score}"
        if strategy == result.strategy:
            items.append(f'<span class="tab active" aria-current="page">{inner}</span>')
        elif r is not None:
            items.append(f'<a class="tab" href="/api/results/{r.id}/report">{inner}</a>')
        else:
            items.append(f'<span class="tab disabled" title="{label} was not tested in this run">{inner}</span>')
    return f'<nav class="tabs" aria-label="Device">{"".join(items)}</nav>'


def render_html(result: PerformanceResult, report: dict, tz: ZoneInfo, siblings: dict | None = None) -> str:
    lhr = report.get("lighthouseResult") or {}
    data = json.dumps(lhr, separators=(",", ":")).replace("<", "\\u003c") \
        .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    tested = result.tested_at.astimezone(tz).strftime("%d %b %Y, %H:%M")
    device = result.strategy.capitalize()
    fresh = psi_report_link(result.requested_url, result.strategy)
    field = (_field_section("Real users — this URL", report.get("loadingExperience"))
             + _field_section("Real users — whole origin", report.get("originLoadingExperience")))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{escape(result.website_name)} — {device} — PageSpeed report {escape(tested)}</title>
<style>
body{{margin:0;font-family:Roboto,"Segoe UI",Arial,sans-serif;color:#202124}}
.bar{{background:#0f2b46;color:#fff;padding:14px 20px;display:flex;flex-wrap:wrap;gap:8px 20px;align-items:center;justify-content:space-between}}
.bar b{{font-size:15px}} .bar span{{font-size:13px;opacity:.85}} .bar a{{color:#9cc3ff;font-size:13px}}
.fdwrap{{max-width:1200px;margin:0 auto;padding:16px 20px 0}}
.fd{{border:1px solid #e0e0e0;border-radius:8px;padding:14px 16px;margin-bottom:12px}}
.fd h3{{margin:0 0 10px;font-size:15px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.badge{{color:#fff;font-size:12px;padding:2px 8px;border-radius:10px;font-weight:500}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}}
.m{{background:#f8f9fa;border-radius:6px;padding:8px 10px}} .ml{{font-size:12px;color:#5f6368}}
.mv{{font-size:22px;font-weight:600;margin-top:2px}} .mc{{font-size:12px}} .muted{{color:#5f6368;font-size:12px;margin:8px 0 0}}
.tabsbar{{border-bottom:1px solid #dadce0;background:#fff}}
.tabs{{display:flex;justify-content:center;gap:4px;max-width:1200px;margin:0 auto}}
.tab{{display:inline-flex;align-items:center;gap:8px;padding:12px 22px;font-size:15px;color:#5f6368;text-decoration:none;border-bottom:3px solid transparent}}
.tab:hover{{background:#f1f3f4;color:#202124}} .tab.active{{color:#1a73e8;border-bottom-color:#1a73e8;font-weight:500}}
.tab.disabled{{opacity:.45;cursor:not-allowed}} .tab .sc{{font-weight:600;font-size:14px}}
.sub{{max-width:1200px;margin:0 auto;padding:10px 20px 0;font-size:13px;color:#5f6368;display:flex;flex-wrap:wrap;gap:6px 18px;justify-content:space-between}}
.sub a{{color:#1a73e8}}
</style></head><body>
<div class="bar"><div><b>{escape(result.website_name)}</b><br><span>{escape(result.requested_url)}</span></div>
<span>Saved report · {escape(tested)} ({escape(str(tz))})</span></div>
<div class="tabsbar">{_tabs(result, siblings or {})}</div>
<div class="sub"><span>{device} — the exact PageSpeed data behind the score in the dashboard (no new analysis).</span>
<span><a href="/api/results/{result.id}/viewer" target="_blank" rel="noreferrer noopener">Open on Google Lighthouse Viewer ↗</a> &nbsp;·&nbsp;
<a href="{escape(fresh)}" target="_blank" rel="noreferrer noopener">Run a fresh analysis on PageSpeed Insights ↗</a></span></div>
<div class="fdwrap">{field}</div>
<div id="lh-log"></div>
<script type="application/json" id="lhr-json">{data}</script>
<script src="/lighthouse-assets/standalone.js"></script>
<script src="/lighthouse-assets/report-init.js"></script>
</body></html>"""


def missing_html(result: PerformanceResult) -> str:
    fresh = psi_report_link(result.requested_url, result.strategy)
    reason = ("This test failed, so PageSpeed returned no report." if result.status != "success"
              else "The stored report for this test is no longer available (older than the retention period, "
                   "or it could not be saved).")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Report not available</title>
<style>body{{font-family:"Segoe UI",Arial,sans-serif;max-width:640px;margin:60px auto;padding:0 20px;color:#202124}}
a{{color:#1a73e8}}</style></head><body><h2>Report not available</h2><p>{escape(reason)}</p>
<p><a href="{escape(fresh)}" target="_blank" rel="noreferrer noopener">Run a fresh analysis on PageSpeed Insights ↗</a></p>
</body></html>"""
