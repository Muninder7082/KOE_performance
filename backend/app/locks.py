"""Database lease locks.

Works across processes/containers: the lock is a row in scheduled_tasks and is
taken with a single conditional UPDATE, which PostgreSQL executes atomically.
Leases expire, so a crashed container never blocks work forever.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from datetime import timedelta
from typing import AsyncIterator

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .clock import now_utc
from .models import ScheduledTask

INSTANCE_ID = f"{os.getenv('HOSTNAME', 'local')}-{uuid.uuid4().hex[:8]}"


async def ensure_task_row(sf: async_sessionmaker[AsyncSession], name: str) -> None:
    async with sf() as s:
        exists = await s.scalar(select(ScheduledTask.id).where(ScheduledTask.name == name))
        if exists:
            return
        s.add(ScheduledTask(name=name))
        try:
            await s.commit()
        except IntegrityError:
            await s.rollback()


async def try_acquire(sf: async_sessionmaker[AsyncSession], name: str, ttl_seconds: int, owner: str) -> bool:
    await ensure_task_row(sf, name)
    now = now_utc()
    async with sf() as s:
        res = await s.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.name == name,
                or_(ScheduledTask.locked_until.is_(None), ScheduledTask.locked_until < now),
            )
            .values(locked_until=now + timedelta(seconds=ttl_seconds), locked_by=owner)
        )
        await s.commit()
        return res.rowcount == 1


async def refresh(sf: async_sessionmaker[AsyncSession], name: str, ttl_seconds: int, owner: str) -> bool:
    """Extend the lease. Returns False if this owner no longer holds it."""
    async with sf() as s:
        res = await s.execute(
            update(ScheduledTask)
            .where(ScheduledTask.name == name, ScheduledTask.locked_by == owner)
            .values(locked_until=now_utc() + timedelta(seconds=ttl_seconds))
        )
        await s.commit()
        return res.rowcount == 1


async def release(sf: async_sessionmaker[AsyncSession], name: str, owner: str) -> None:
    async with sf() as s:
        await s.execute(
            update(ScheduledTask)
            .where(ScheduledTask.name == name, ScheduledTask.locked_by == owner)
            .values(locked_until=None, locked_by=None)
        )
        await s.commit()


@contextlib.asynccontextmanager
async def lease(
    sf: async_sessionmaker[AsyncSession],
    name: str,
    ttl_seconds: int,
    wait_seconds: float = 0,
) -> AsyncIterator[str | None]:
    """Yield the owner id when the lock was obtained (waiting up to wait_seconds), else None."""
    owner = f"{INSTANCE_ID}-{uuid.uuid4().hex[:6]}"
    deadline = asyncio.get_running_loop().time() + wait_seconds
    got = await try_acquire(sf, name, ttl_seconds, owner)
    while not got and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.5)
        got = await try_acquire(sf, name, ttl_seconds, owner)
    try:
        yield owner if got else None
    finally:
        if got:
            await release(sf, name, owner)
