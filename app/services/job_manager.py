"""Job persistence — Redis-backed with PostgreSQL and in-memory fallback.

Persistence hierarchy (write-through):
    1. Redis  — fast ephemeral cache (24h TTL)
    2. PostgreSQL — durable persistent store (optional, requires SQLAlchemy)
    3. In-memory dict — last-resort fallback for local dev

Reads check Redis first, then PostgreSQL, then memory.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.models.jobs import Job, JobState

log = logging.getLogger(__name__)
_JOB_TTL = 86400  # 24 hours


class JobManager:
    """CRUD for async analysis jobs."""

    def __init__(self, redis_url: str = "", database_url: str = "") -> None:
        self._redis: Any = None
        self._pg: Any = None
        self._memory: Dict[str, Dict[str, Any]] = {}

        if redis_url:
            try:
                import redis as r
                self._redis = r.from_url(redis_url, socket_connect_timeout=3)
                self._redis.ping()
                log.info("JobManager backend: Redis")
            except Exception as exc:  # noqa: BLE001
                log.warning("JobManager Redis unavailable (%s); using fallback", exc)
                self._redis = None

        if database_url:
            try:
                from app.services.postgres_jobs import PostgresJobStore, SQLALCHEMY_AVAILABLE
                if SQLALCHEMY_AVAILABLE:
                    self._pg = PostgresJobStore(database_url)
                    log.info("JobManager backend: PostgreSQL")
                else:
                    log.warning("SQLAlchemy not installed; PostgreSQL persistence disabled")
            except Exception as exc:  # noqa: BLE001
                log.warning("JobManager PostgreSQL unavailable (%s); using fallback", exc)
                self._pg = None

    @property
    def backend(self) -> str:
        """Human-readable description of active backends."""
        parts = []
        if self._redis:
            parts.append("redis")
        if self._pg:
            parts.append("postgresql")
        return "+".join(parts) if parts else "memory"

    def create_job(self, request_data: Dict[str, Any]) -> Job:
        job = Job(job_id=str(uuid.uuid4()), request_data=request_data)
        self._save(job)
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        data = self._load(job_id)
        if data is None:
            return None
        job = Job.__new__(Job)
        job.__dict__.update(data)
        job.state      = JobState(data["state"])
        job.created_at = datetime.fromisoformat(data["created_at"])
        job.updated_at = datetime.fromisoformat(data["updated_at"])
        return job

    def update_job(
        self,
        job_id: str,
        state: JobState,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        job = self.get_job(job_id)
        if job is None:
            log.warning("update_job: job %s not found", job_id)
            return
        job.state      = state
        job.result     = result
        job.error      = error
        job.updated_at = datetime.now(timezone.utc)
        self._save(job)

    def _save(self, job: Job) -> None:
        d = job.to_dict()
        d["request_data"] = job.request_data
        # Write-through: save to all available backends
        if self._redis:
            try:
                self._redis.setex(f"job:{job.job_id}", _JOB_TTL, json.dumps(d, default=str))
            except Exception as exc:  # noqa: BLE001
                log.debug("Redis save failed: %s", exc)
        if self._pg:
            try:
                self._pg.save(d)
            except Exception as exc:  # noqa: BLE001
                log.debug("PostgreSQL save failed: %s", exc)
        # Always keep in memory as last-resort
        self._memory[job.job_id] = d

    def _load(self, job_id: str) -> Optional[Dict[str, Any]]:
        # 1. Redis (fastest)
        if self._redis:
            try:
                raw = self._redis.get(f"job:{job_id}")
                if raw:
                    return json.loads(raw)
            except Exception as exc:  # noqa: BLE001
                log.debug("Redis load failed: %s", exc)
        # 2. PostgreSQL (durable)
        if self._pg:
            try:
                data = self._pg.load(job_id)
                if data:
                    return data
            except Exception as exc:  # noqa: BLE001
                log.debug("PostgreSQL load failed: %s", exc)
        # 3. In-memory (fallback)
        return self._memory.get(job_id)
