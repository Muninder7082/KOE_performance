from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Timestamp stored as timestamptz; always returned as an aware UTC datetime."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime passed to UTCDateTime column")
        value = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str, connect_args: dict | None = None) -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    kwargs: dict = {"pool_pre_ping": True}
    if not url.startswith("sqlite"):
        kwargs.update(pool_size=10, max_overflow=10, pool_recycle=1800)
    _engine = create_async_engine(url, connect_args=connect_args or {}, **kwargs)
    if url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(_engine.sync_engine, "connect")
        def _fk_on(dbapi_conn, _record):  # ON DELETE SET NULL needs this on SQLite
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


def get_engine() -> AsyncEngine:
    assert _engine is not None, "Database engine not initialised"
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    assert _session_factory is not None, "Database engine not initialised"
    return _session_factory


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session
