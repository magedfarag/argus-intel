"""Unit tests for PostgreSQL job persistence (P3-3).

Uses SQLite in-memory as the test database to avoid requiring a real
PostgreSQL server.
"""
from __future__ import annotations

import pytest
from datetime import datetime, UTC

from app.services.postgres_jobs import SQLALCHEMY_AVAILABLE


pytestmark = pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE,
    reason="SQLAlchemy not installed",
)

SQLITE_URL = "sqlite://"  # in-memory SQLite


@pytest.fixture
def pg_store():
    """Fresh PostgresJobStore backed by in-memory SQLite."""
    from app.services.postgres_jobs import PostgresJobStore
    store = PostgresJobStore(SQLITE_URL)
    yield store
    store.close()


@pytest.fixture
def sample_job_data():
    now = datetime.now(UTC).isoformat()
    return {
        "job_id": "test-job-1",
        "state": "pending",
        "request_data": {"geometry": {"type": "Polygon", "coordinates": []}},
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }


class TestPostgresJobStore:
    """CRUD operations on the job store."""

    def test_save_and_load(self, pg_store, sample_job_data):
        pg_store.save(sample_job_data)
        loaded = pg_store.load("test-job-1")
        assert loaded is not None
        assert loaded["job_id"] == "test-job-1"
        assert loaded["state"] == "pending"

    def test_load_nonexistent_returns_none(self, pg_store):
        assert pg_store.load("no-such-job") is None

    def test_update_existing_job(self, pg_store, sample_job_data):
        pg_store.save(sample_job_data)
        updated = {**sample_job_data, "state": "completed", "result": {"analysis_id": "a-1"}}
        pg_store.save(updated)
        loaded = pg_store.load("test-job-1")
        assert loaded["state"] == "completed"
        assert loaded["result"]["analysis_id"] == "a-1"

    def test_error_field_persisted(self, pg_store, sample_job_data):
        pg_store.save(sample_job_data)
        updated = {**sample_job_data, "state": "failed", "error": "boom"}
        pg_store.save(updated)
        loaded = pg_store.load("test-job-1")
        assert loaded["error"] == "boom"

    def test_request_data_persisted(self, pg_store, sample_job_data):
        pg_store.save(sample_job_data)
        loaded = pg_store.load("test-job-1")
        assert loaded["request_data"]["geometry"]["type"] == "Polygon"

    def test_multiple_jobs(self, pg_store, sample_job_data):
        pg_store.save(sample_job_data)
        job2 = {**sample_job_data, "job_id": "test-job-2", "state": "running"}
        pg_store.save(job2)
        assert pg_store.load("test-job-1")["state"] == "pending"
        assert pg_store.load("test-job-2")["state"] == "running"


class TestJobManagerWithPostgres:
    """JobManager integration with PostgreSQL backend."""

    def test_backend_property_with_database(self):
        from app.services.job_manager import JobManager
        jm = JobManager(database_url=SQLITE_URL)
        assert "postgresql" in jm.backend

    def test_backend_property_memory_only(self):
        from app.services.job_manager import JobManager
        jm = JobManager()
        assert jm.backend == "memory"

    def test_create_and_get_job_via_postgres(self):
        from app.services.job_manager import JobManager
        jm = JobManager(database_url=SQLITE_URL)
        job = jm.create_job(request_data={"test": True})
        loaded = jm.get_job(job.job_id)
        assert loaded is not None
        assert loaded.job_id == job.job_id

    def test_update_job_via_postgres(self):
        from app.services.job_manager import JobManager
        from app.models.jobs import JobState
        jm = JobManager(database_url=SQLITE_URL)
        job = jm.create_job(request_data={"test": True})
        jm.update_job(job.job_id, JobState.COMPLETED, result={"analysis_id": "a-1"})
        loaded = jm.get_job(job.job_id)
        assert loaded.state == JobState.COMPLETED

    def test_postgres_survives_memory_clear(self):
        """Jobs persisted to PG are recoverable even if memory dict is cleared."""
        from app.services.job_manager import JobManager
        jm = JobManager(database_url=SQLITE_URL)
        job = jm.create_job(request_data={"test": True})
        jm._memory.clear()  # simulate process restart
        loaded = jm.get_job(job.job_id)
        assert loaded is not None
        assert loaded.job_id == job.job_id
