"""Alembic migration environment.

Migrations run synchronously. The async app URL (``sqlite+aiosqlite`` /
``postgresql+asyncpg``) is translated to its sync equivalent by
``settings.sync_database_url`` so the same configuration drives both.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Make the app package importable and pull in configuration + metadata.
from app.config import settings
from app.models.base import Base
import app.models  # noqa: F401  (import side effects register every mapper)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Resolve the (synchronous) database URL from application settings.
DB_URL = settings.sync_database_url
IS_SQLITE = DB_URL.startswith("sqlite")


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (`alembic upgrade --sql`)."""
    context.configure(
        url=DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=IS_SQLITE,  # SQLite can't ALTER in place
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(DB_URL, poolclass=pool.NullPool, future=True)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=IS_SQLITE,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
