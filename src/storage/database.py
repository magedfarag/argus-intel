"""Database session management — SQLAlchemy async-compatible (P0-4).

Provides:
  - ``engine`` / ``SessionFactory`` for sync (test / migration) use
  - ``get_db()`` FastAPI dependency that yields a scoped session
  - ``check_db_connectivity()`` for health checks (P0-5.5)

The module gracefully degrades when ``DATABASE_URL`` is not configured —
all helpers return None or raise ``DatabaseNotConfiguredError`` instead of
crashing the application at import time.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, Optional

log = logging.getLogger(__name__)

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker, Session
    _SA_AVAILABLE = True
except ImportError:
    _SA_AVAILABLE = False  # type: ignore[assignment]

from src.storage.models import Base


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when a DB operation is called without DATABASE_URL."""


_engine = None
_SessionFactory = None


def init_db(database_url: str) -> None:
    """Initialise the engine and session factory.

    Call once during application startup (lifespan).
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _engine, _SessionFactory
    if _engine is not None:
        return
    if not _SA_AVAILABLE:
        log.warning("SQLAlchemy not installed — database features disabled")
        return
    if not database_url:
        log.warning("DATABASE_URL not set — database features disabled")
        return

    _engine = create_engine(
        database_url,
        pool_pre_ping=True,  # avoids stale-connection errors after idle
        pool_size=5,
        max_overflow=10,
        echo=False,
    )
    _SessionFactory = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    log.info("Database engine initialised | url=%s", _redact_url(database_url))


def create_all_tables() -> None:
    """Create all tables that do not yet exist (idempotent).

    Use Alembic ``upgrade head`` in production; this helper is for tests
    and development environments without a migration runner.
    """
    if _engine is None:
        raise DatabaseNotConfiguredError("Call init_db() before create_all_tables()")
    Base.metadata.create_all(bind=_engine)


@contextmanager
def get_session() -> Generator["Session", None, None]:  # type: ignore[type-arg]
    """Yield a SQLAlchemy session, committing on exit or rolling back on error."""
    if _SessionFactory is None:
        raise DatabaseNotConfiguredError("Database not initialised — call init_db() first")
    session: Session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator["Session", None, None]:  # type: ignore[type-arg]
    """FastAPI dependency — yields a session and closes it after the request."""
    with get_session() as session:
        yield session


def check_db_connectivity() -> tuple[bool, str]:
    """Probe the database with a lightweight query.

    Returns:
        (True, "ok") on success or (False, error_message) on failure.
    """
    if _engine is None:
        return False, "not_configured"
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


def _redact_url(url: str) -> str:
    """Replace password in connection URL with *** for logging."""
    import re
    return re.sub(r":(//[^:]+:)[^@]+@", r":\1***@", url)

