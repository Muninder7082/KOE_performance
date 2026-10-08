"""Single source of "now" so tests can move time forward deterministically."""
from __future__ import annotations

from datetime import datetime, timezone

_override: datetime | None = None


def now_utc() -> datetime:
    if _override is not None:
        return _override
    return datetime.now(timezone.utc)


def set_now(value: datetime | None) -> None:
    """Test helper. Never called by application code."""
    global _override
    if value is not None and value.tzinfo is None:
        raise ValueError("set_now requires an aware datetime")
    _override = value.astimezone(timezone.utc) if value else None
