"""Alembic environment configuration.

Supports both:
  - Online (async) migrations executed via ``alembic upgrade head``
  - Offline (SQL script) generation via ``alembic upgrade head --sql``

The async engine is built from the DATABASE_URL_SYNC environment variable
(standard sync PostgreSQL DSN) which Alembic requires for its own connection
management.  The application's async DSN (``DATABASE_URL``) is used at runtime
by SQLAlchemy inside the FastAPI app.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ---------------------------------------------------------------------------
# Import the declarative Base and all model modules so that Base.metadata is
# populated with every table before autogenerate compares it to the database.
# ---------------------------------------------------------------------------
# Base must be imported first
from app.db.base import Base  # noqa: F401

# Import all models – each model registers itself with Base.metadata on import.
# Add a new import line here whenever a new model module is created.
import app.db.models.price_series       # noqa: F401
import app.db.models.generation_mix     # noqa: F401
import app.db.models.cross_border_flows # noqa: F401
import app.db.models.weather            # noqa: F401
import app.db.models.feature_snapshots  # noqa: F401
import app.db.models.ml_model_registry  # noqa: F401
import app.db.models.signals            # noqa: F401
import app.db.models.paper_trades       # noqa: F401
import app.db.models.users              # noqa: F401

# ---------------------------------------------------------------------------
# Alembic Config object – provides access to the values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Interpret the alembic.ini logging section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Override the SQLAlchemy URL from environment variable if available.
# This allows docker-compose / k8s to inject the real DSN without editing ini.
# ---------------------------------------------------------------------------
_db_url = os.environ.get("DATABASE_URL_SYNC") or os.environ.get(
    "DATABASE_URL", ""
).replace("postgresql+asyncpg://", "postgresql://")

if _db_url:
    config.set_main_option("sqlalchemy.url", _db_url)

# Target metadata for autogenerate support
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline migration helpers
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine; calls to
    ``context.execute()`` emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Include schema names in ``CREATE TABLE`` statements so that
        # the generated SQL is portable between schemas.
        include_schemas=True,
        # Render ``AS IDENTITY`` for auto-increment columns on PostgreSQL 10+
        render_as_batch=False,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online (async) migration helpers
# ---------------------------------------------------------------------------

def do_run_migrations(connection: Connection) -> None:
    """Execute migrations using a synchronous-style connection adapter."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        render_as_batch=False,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through a sync shim.

    ``async_engine_from_config`` builds an AsyncEngine from the alembic.ini
    ``[alembic]`` section keys prefixed with ``sqlalchemy.``.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # never pool connections in migration scripts
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations – drives the async coroutine."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point – called by the Alembic CLI
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
