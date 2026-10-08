"""Google PageSpeed Insights API v5 client.

PageSpeedService.run(url, strategy) returns normalised metrics or raises
PageSpeedError. The API key never leaves the server and is scrubbed from any
error text before it is stored or logged.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from typing import Any

import httpx

from ..clock import now_utc
from ..config import get_settings

log = logging.getLogger(__name__)

API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CATEGORIES = ("performance", "accessibility", "best-practices", "seo")
STRATEGIES = ("desktop", "mobile")
_UNREACHABLE_HINTS = (
    "FAILED_DOCUMENT_REQUEST",
    "ERRORED_DOCUMENT_REQUEST",
    "DNS_FAILURE",
    "NOT_HTML",
    "DOCUMENT_REQUEST",
    "unable to reliably load the page",
    "net::ERR",
)


class PageSpeedError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False, http_status: int | None = None,
                 retry_after: float | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status
        self.retry_after = retry_after

    @property
    def api_status(self) -> str:
        return f"HTTP {self.http_status}" if self.http_status else self.code.upper()


def _scrub(text: str, key: str) -> str:
    if key:
        text = text.replace(key, "***")
    return text[:2000]


def _category_score(categories: dict, name: str) -> int | None:
    cat = categories.get(name) or {}
    score = cat.get("score")
    if isinstance(score, (int, float)):
        return int(round(score * 100))
    return None


def _numeric(audits: dict, name: str) -> float | None:
    audit = audits.get(name) or {}
    value = audit.get("numericValue")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _ms_to_s(value: float | None) -> float | None:
    return round(value / 1000.0, 2) if value is not None else None


def _parse_time(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                return dt
        except ValueError:
            pass
    return now_utc()


def normalize(data: dict, url: str, strategy: str) -> dict:
    """Normalise a raw API response. Every field is optional in the response."""
    lr = data.get("lighthouseResult") or {}
    runtime_error = lr.get("runtimeError") or {}
    if runtime_error.get("code") and runtime_error.get("code") != "NO_ERROR":
        msg = f"{runtime_error.get('code')}: {runtime_error.get('message', '')}".strip()
        code = "website_unavailable" if any(h in msg for h in _UNREACHABLE_HINTS) else "lighthouse_error"
        raise PageSpeedError(code, msg, http_status=200)
    if not lr:
        raise PageSpeedError("invalid_response", "Response did not contain a Lighthouse result", http_status=200)
    categories = lr.get("categories") or {}
    audits = lr.get("audits") or {}
    cls = _numeric(audits, "cumulative-layout-shift")
    tbt = _numeric(audits, "total-blocking-time")
    result = {
        "url": url,
        "requested_url": lr.get("requestedUrl") or data.get("id") or url,
        "final_url": lr.get("finalDisplayedUrl") or lr.get("finalUrl") or data.get("id"),
        "strategy": strategy,
        "performance_score": _category_score(categories, "performance"),
        "accessibility_score": _category_score(categories, "accessibility"),
        "best_practices_score": _category_score(categories, "best-practices"),
        "seo_score": _category_score(categories, "seo"),
        "fcp": _ms_to_s(_numeric(audits, "first-contentful-paint")),
        "lcp": _ms_to_s(_numeric(audits, "largest-contentful-paint")),
        "tbt": round(tbt) if tbt is not None else None,
        "cls": round(cls, 3) if cls is not None else None,
        "speed_index": _ms_to_s(_numeric(audits, "speed-index")),
        "tested_at": _parse_time(lr.get("fetchTime") or data.get("analysisUTCTimestamp")).isoformat(),
        "api_status": "HTTP 200",
    }
    if result["performance_score"] is None:
        raise PageSpeedError("missing_metrics", "Response did not include a Performance score", http_status=200)
    return result


def _classify_http_error(resp: httpx.Response, key: str) -> PageSpeedError:
    status = resp.status_code
    try:
        body = resp.json()
        err = body.get("error") or {}
        message = str(err.get("message") or resp.text)
        reasons = " ".join(str(e.get("reason", "")) for e in (err.get("errors") or []) if isinstance(e, dict))
        details_reasons = " ".join(
            str(d.get("reason", "")) for d in (err.get("details") or []) if isinstance(d, dict)
        )
        reasons = f"{reasons} {details_reasons} {err.get('status', '')}"
    except ValueError:
        message, reasons = resp.text, ""
    message = _scrub(message, key)
    retry_after = None
    ra = resp.headers.get("Retry-After")
    if ra and ra.isdigit():
        retry_after = float(ra)
    lowered = f"{message} {reasons}".lower()
    if status == 429:
        if "per day" in lowered or "dailylimit" in lowered or "quota exceeded for quota metric 'queries' and limit 'queries per day'" in lowered:
            return PageSpeedError("quota_exceeded", f"PageSpeed API daily quota exceeded. {message}", http_status=status)
        return PageSpeedError("rate_limited", f"PageSpeed API rate limit hit. {message}", retryable=True,
                              http_status=status, retry_after=retry_after)
    if "api_key_invalid" in lowered or "api key not valid" in lowered or "api key expired" in lowered:
        return PageSpeedError("api_key_invalid", "PageSpeed API key is invalid or expired.", http_status=status)
    if status in (401, 403):
        if "has not been used" in lowered or "service_disabled" in lowered or "disabled" in lowered:
            return PageSpeedError("api_not_enabled", f"PageSpeed Insights API is not enabled for this key. {message}",
                                  http_status=status)
        return PageSpeedError("forbidden", message, http_status=status)
    if "lighthouse returned error" in lowered or any(h.lower() in lowered for h in _UNREACHABLE_HINTS):
        return PageSpeedError("website_unavailable", message, http_status=status)
    if status == 400:
        return PageSpeedError("invalid_request", message, http_status=status)
    if status >= 500:
        return PageSpeedError("api_error", message, retryable=True, http_status=status, retry_after=retry_after)
    return PageSpeedError("api_error", message, http_status=status)


class PageSpeedService:
    def __init__(self, client: httpx.AsyncClient | None = None, *, sleep=None):
        self._settings = get_settings()
        self._client = client
        self._owns_client = client is None
        self._sleep = sleep
        self.semaphore = asyncio.Semaphore(self._settings.pagespeed_concurrency)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.pagespeed_timeout_seconds, connect=20),
                headers={"User-Agent": "website-performance-monitor/1.0"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    @property
    def configured(self) -> bool:
        return bool(self._settings.pagespeed_api_key)

    async def run(self, url: str, strategy: str) -> dict:
        if strategy not in STRATEGIES:
            raise ValueError("strategy must be 'desktop' or 'mobile'")
        key = self._settings.pagespeed_api_key
        if not key:
            raise PageSpeedError("not_configured", "PAGESPEED_API_KEY is not configured")
        # The key goes in a header (not the query string) so it never appears in URLs or access logs.
        params: list[tuple[str, str]] = [("url", url), ("strategy", strategy)]
        params += [("category", c) for c in CATEGORIES]
        attempts = self._settings.pagespeed_max_retries + 1
        last: PageSpeedError | None = None
        async with self.semaphore:
            client = await self._get_client()
            for attempt in range(attempts):
                try:
                    resp = await client.get(API_URL, params=params, headers={"X-goog-api-key": key})
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                        except ValueError:
                            raise PageSpeedError("invalid_response", "Response was not valid JSON",
                                                 retryable=True, http_status=200) from None
                        result = normalize(data, url, strategy)
                        from .lighthouse_reports import slim

                        result["_report"] = slim(data)  # full report for the dashboard (not in the DB row)
                        return result
                    raise _classify_http_error(resp, key)
                except PageSpeedError as exc:
                    last = exc
                except httpx.TimeoutException:
                    last = PageSpeedError("timeout", "PageSpeed request timed out", retryable=True)
                except httpx.TransportError as exc:
                    last = PageSpeedError("network_error", _scrub(f"Network error: {type(exc).__name__}: {exc}", key),
                                          retryable=True)
                if not last.retryable or attempt == attempts - 1:
                    break
                delay = last.retry_after or min(60.0, self._settings.pagespeed_backoff_base_seconds * (2 ** attempt))
                delay += random.uniform(0, 1)
                log.warning("PageSpeed %s %s attempt %d failed (%s); retrying in %.1fs",
                            strategy, url, attempt + 1, last.code, delay)
                await (self._sleep or asyncio.sleep)(delay)
        assert last is not None
        raise last


def psi_report_link(url: str, strategy: str = "mobile") -> str:
    from urllib.parse import quote

    return f"https://pagespeed.web.dev/report?url={quote(url, safe='')}&form_factor={strategy}"
