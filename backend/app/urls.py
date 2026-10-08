"""URL validation and normalisation for monitored websites."""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

_HOST_RE = re.compile(r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}


class InvalidUrl(ValueError):
    pass


def validate_and_normalize(raw: str) -> tuple[str, str]:
    """Return (clean_url, normalized_key).

    PageSpeed Insights can only test publicly reachable http(s) pages, so local,
    private and malformed addresses are rejected before saving.
    """
    url = (raw or "").strip()
    if not url:
        raise InvalidUrl("URL is required")
    if len(url) > 2048:
        raise InvalidUrl("URL is too long (max 2048 characters)")
    if any(c.isspace() for c in url):
        raise InvalidUrl("URL must not contain spaces")
    if "://" not in url:
        raise InvalidUrl("URL must start with http:// or https://")
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise InvalidUrl("Only http:// and https:// URLs are supported")
    if parts.username or parts.password:
        raise InvalidUrl("URLs with embedded credentials are not allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise InvalidUrl("URL has no host name")
    if host in _BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        raise InvalidUrl("Local addresses cannot be tested by PageSpeed Insights")
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        ip = None
    if ip is not None:
        if not ip.is_global:
            raise InvalidUrl("Private or reserved IP addresses cannot be tested")
    else:
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise InvalidUrl("Invalid host name") from exc
        if not _HOST_RE.match(ascii_host):
            raise InvalidUrl("Invalid host name")
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidUrl("Invalid port") from exc
    netloc = host if ip is None or ip.version == 4 else f"[{host.strip('[]')}]"
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{netloc}:{port}"
    path = parts.path or "/"
    clean = urlunsplit((scheme, netloc, path, parts.query, ""))
    # Duplicate key: scheme-insensitive, trailing slash-insensitive, no fragment.
    key_path = path.rstrip("/") or "/"
    key = urlunsplit(("", netloc, key_path, parts.query, "")).lstrip("/")
    return clean, key
