"""Async SQLAlchemy engine & session management."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# SQLite needs check_same_thread disabled; Postgres ignores connect_args below.
_connect_args = {}
if settings.is_sqlite:
    # ``timeout`` is SQLite's busy-timeout (seconds): wait for a competing writer
    # to release its lock instead of failing immediately with "database is locked".
    _connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    connect_args=_connect_args,
    # asyncpg pools are configured here; SQLite ignores pool sizing.
    **({} if settings.is_sqlite else {"pool_size": 20, "max_overflow": 10}),
)


if settings.is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
        """Enable WAL so readers (dashboard/analytics) don't block the streaming
        writer, and set a busy timeout as a second line of defense against locks."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session with commit/rollback handling."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all() -> None:
    """Create tables from metadata (local-dev convenience)."""
    from app.models.base import Base  # local import to avoid cycles
    import app.models  # noqa: F401  (register all mappers)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ping() -> bool:
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
