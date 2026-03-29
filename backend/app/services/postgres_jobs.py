"""PostgreSQL job persistence layer using SQLAlchemy.

Provides a ``PostgresJobStore`` that saves/loads job records as rows
in a ``jobs`` table.  When ``database_url`` is configured, this layer
is used by ``JobManager`` as the durable backing store underneath the
fast Redis cache.

If SQLAlchemy is not installed, import is caught and the module
exposes ``SQLALCHEMY_AVAILABLE = False`` so callers can skip.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

SQLALCHEMY_AVAILABLE = False

try:
    from sqlalchemy import Column, DateTime, String, Text, create_engine
    from sqlalchemy.orm import Session, declarative_base, sessionmaker

    SQLALCHEMY_AVAILABLE = True
except ImportError:
    pass


def _build_base():
    """Lazily create the declarative base (only when SQLAlchemy is present)."""
    if not SQLALCHEMY_AVAILABLE:
        return None
    return declarative_base()


Base = _build_base()


if SQLALCHEMY_AVAILABLE and Base is not None:
    class JobRow(Base):  # type: ignore[misc]
        """SQLAlchemy model for the ``jobs`` table."""

        __tablename__ = "jobs"

        job_id       = Column(String(64), primary_key=True)
        state        = Column(String(32), nullable=False, default="pending")
        request_data = Column(Text, nullable=True)
        result       = Column(Text, nullable=True)
        error        = Column(Text, nullable=True)
        created_at   = Column(DateTime, nullable=False, default=datetime.utcnow)
        updated_at   = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PostgresJobStore:
    """Thin CRUD layer over the ``jobs`` table."""

    def __init__(self, database_url: str) -> None:
        if not SQLALCHEMY_AVAILABLE:
            raise RuntimeError("sqlalchemy is required for PostgreSQL job persistence")
        self._engine = create_engine(database_url, pool_pre_ping=True)
        Base.metadata.create_all(self._engine)  # type: ignore[union-attr]
        self._Session = sessionmaker(bind=self._engine)
        log.info("PostgresJobStore connected: %s", database_url.split("@")[-1] if "@" in database_url else "(local)")

    def save(self, data: Dict[str, Any]) -> None:
        """Upsert a job record."""
        with self._Session() as session:
            row = session.get(JobRow, data["job_id"])
            if row is None:
                row = JobRow(
                    job_id=data["job_id"],
                    state=data.get("state", "pending"),
                    request_data=json.dumps(data.get("request_data"), default=str) if data.get("request_data") else None,
                    result=json.dumps(data.get("result"), default=str) if data.get("result") else None,
                    error=data.get("error"),
                    created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.utcnow()),
                    updated_at=datetime.fromisoformat(data["updated_at"]) if isinstance(data.get("updated_at"), str) else data.get("updated_at", datetime.utcnow()),
                )
                session.add(row)
            else:
                row.state = data.get("state", row.state)
                if data.get("result"):
                    row.result = json.dumps(data["result"], default=str)
                if data.get("error"):
                    row.error = data["error"]
                if data.get("request_data") and not row.request_data:
                    row.request_data = json.dumps(data["request_data"], default=str)
                row.updated_at = datetime.fromisoformat(data["updated_at"]) if isinstance(data.get("updated_at"), str) else datetime.utcnow()
            session.commit()

    def load(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load a job record by ID; returns None if not found."""
        with self._Session() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                return None
            return {
                "job_id": row.job_id,
                "state": row.state,
                "request_data": json.loads(row.request_data) if row.request_data else {},
                "result": json.loads(row.result) if row.result else None,
                "error": row.error,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }

    def close(self) -> None:
        """Dispose of the engine connection pool."""
        self._engine.dispose()
