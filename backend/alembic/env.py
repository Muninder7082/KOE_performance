from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app import models  # noqa: F401 - register tables
from app.db import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    url = config.attributes.get("url")
    if not url:
        from app.config import get_settings

        url = get_settings().async_database_url
    return url


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async() -> None:
    connect_args = config.attributes.get("connect_args") or {}
    engine = create_async_engine(_url(), connect_args=connect_args)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
        await conn.commit()
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_async())
