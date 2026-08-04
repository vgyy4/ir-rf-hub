from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from ir_rf_hub.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    # WAL mode lets the App keep serving reads/writes while backup_pre.sh
    # checkpoints -- see app/rootfs/backup_pre.sh for the other half of this.
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(database_url: str | None = None) -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        url = database_url or settings.database_url
        is_memory = ":memory:" in url
        _engine = create_async_engine(
            url,
            poolclass=StaticPool if is_memory else None,
            connect_args={"check_same_thread": False} if is_memory else {},
        )
        event.listen(_engine.sync_engine, "connect", _set_sqlite_pragmas)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with session_scope() as session:
        yield session


async def reset_engine_for_tests() -> None:
    """Test-only helper: drop the cached engine/session factory so a fresh
    in-memory database can be created for the next test.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
