"""Alembic env.py — PostGIS migration environment (P0-4.4).

Reads DATABASE_URL from the environment (or .env file via pydantic-settings)
so no credentials are ever hardcoded here.
"""
from __future__ import annotations

import logging
import os
from logging.config import fileConfig

from alembic import context

# Import application metadata so Alembic can detect divergence
from src.storage.models import Base  # noqa: F401 — registers all ORM metadata

# Alembic config object (gives access to alembic.ini values)
config = context.config

# Attach Python logging configuration from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

log = logging.getLogger("alembic.env")
target_metadata = Base.metadata


def _get_url() -> str:
    """Resolve DATABASE_URL from environment, application config, or alembic.ini."""
    # 1. Explicit env var (highest priority — works in CI/Docker)
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # 2. Application settings (reads .env file)
    try:
        from app.config import get_settings  # type: ignore[import]
        settings = get_settings()
        if settings.database_url:
            return settings.database_url
    except Exception:  # pragma: no cover
        pass
    # 3. alembic.ini sqlalchemy.url fallback
    return config.get_main_option("sqlalchemy.url", "")


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection.

    Useful for generating migration scripts to review before applying.
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live HTTP connection."""
    from sqlalchemy import create_engine

    url = _get_url()
    if not url:
        log.warning("DATABASE_URL not set — skipping migrations")
        return

    connectable = create_engine(url, pool_pre_ping=True)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

