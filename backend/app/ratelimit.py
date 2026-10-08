"""Small in-memory sliding-window rate limiter (single container deployment)."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, limit: int, window_seconds: float) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            retry = int(window_seconds - (now - q[0])) + 1
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down.",
                headers={"Retry-After": str(retry)},
            )
        q.append(now)
        if len(self._hits) > 10_000:  # bound memory
            for k in list(self._hits)[:5_000]:
                if not self._hits[k]:
                    del self._hits[k]

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    """Client address for rate limiting.

    The left-most X-Forwarded-For entries are supplied by the client and can be forged, so
    they are ignored. Each trusted proxy appends the address it received the request from;
    with TRUSTED_PROXY_HOPS=1 (Hugging Face's single front proxy) the right-most entry is
    the real client. With TRUSTED_PROXY_HOPS=0 the TCP peer address is used.
    """
    from .config import get_settings

    hops = get_settings().trusted_proxy_hops
    xff = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if hops > 0 and len(parts) >= hops:
        return parts[-hops]
    return request.client.host if request.client else "unknown"
