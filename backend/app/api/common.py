from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..services import settings_service


async def app_tz(session: AsyncSession) -> ZoneInfo:
    return (await settings_service.load(session)).tz


def day_range(date_from: date | None, date_to: date | None, tz: ZoneInfo) -> tuple[datetime | None, datetime | None]:
    """Inclusive local calendar dates -> [start, end) UTC instants."""
    start = datetime.combine(date_from, datetime.min.time(), tzinfo=tz) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=tz) if date_to else None
    if start and end and end <= start:
        raise HTTPException(422, "End date must be on or after start date")
    return start, end


class Paging:
    def __init__(self, page: int = Query(1, ge=1, le=100000), page_size: int = Query(25, ge=1, le=200)):
        self.page = page
        self.page_size = page_size
