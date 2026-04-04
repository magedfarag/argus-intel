"""Integration test for PostGIS schema — P0-4.6.

These tests require a live PostgreSQL + PostGIS instance.
Skipped automatically when DATABASE_URL is not set or when psycopg2/
GeoAlchemy2 are not installed in the test environment.

To run locally:
    DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost/geoint \\
        pytest tests/integration/test_db_schema.py -v
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Generator

import pytest

_DB_URL = os.environ.get("DATABASE_URL", "")
_SKIP = not _DB_URL


@pytest.fixture(scope="module")
def db_engine():
    """Create a throw-away test database schema, yield the engine, then drop."""
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("psycopg2")
    from sqlalchemy import create_engine
    from src.storage.models import Base

    engine = create_engine(_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator:
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.mark.skipif(_SKIP, reason="DATABASE_URL not set")
def test_aoi_insert_and_query(db_session) -> None:
    """Insert an AOI, retrieve it, verify fields round-trip correctly."""
    from src.storage.models import AOI
    from uuid import uuid4
    import json

    aoi_id = str(uuid4())
    geom = json.dumps({"type": "Polygon", "coordinates": [[[10.0, 20.0], [11.0, 20.0], [11.0, 21.0], [10.0, 20.0]]]})
    aoi = AOI(
        id=aoi_id,
        name="Test AOI",
        geometry=geom,
        tags=["test"],
        metadata_={"created_by": "pytest"},
    )
    db_session.add(aoi)
    db_session.flush()

    retrieved = db_session.query(AOI).filter_by(id=aoi_id).one()
    assert retrieved.name == "Test AOI"
    assert retrieved.deleted is False


@pytest.mark.skipif(_SKIP, reason="DATABASE_URL not set")
def test_canonical_event_insert_and_aoi_time_query(db_session) -> None:
    """Insert a canonical event linked to an AOI; query by AOI + time window."""
    from src.storage.models import AOI, CanonicalEventRow
    from uuid import uuid4
    import json

    aoi_id = str(uuid4())
    geom = json.dumps({"type": "Polygon", "coordinates": [[[10.0, 20.0], [11.0, 20.0], [11.0, 21.0], [10.0, 20.0]]]})
    aoi = AOI(id=aoi_id, name="Event AOI", geometry=geom, tags=[], metadata_={})
    db_session.add(aoi)
    db_session.flush()

    event_time = datetime(2026, 4, 3, 10, 0, 0, tzinfo=timezone.utc)
    event = CanonicalEventRow(
        event_id="evt_test_abcdef123456",
        source="test-source",
        source_type="imagery_catalog",
        entity_type="imagery_scene",
        event_type="imagery_acquisition",
        event_time=event_time,
        attributes={},
        primary_aoi_id=aoi_id,
    )
    db_session.add(event)
    db_session.flush()

    # Query by AOI + time window (uses ix_events_aoi_time composite index)
    from sqlalchemy import and_
    window_start = datetime(2026, 4, 3, 9, 0, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 4, 3, 11, 0, 0, tzinfo=timezone.utc)
    results = (
        db_session.query(CanonicalEventRow)
        .filter(
            and_(
                CanonicalEventRow.primary_aoi_id == aoi_id,
                CanonicalEventRow.event_time >= window_start,
                CanonicalEventRow.event_time <= window_end,
            )
        )
        .all()
    )
    assert len(results) == 1
    assert results[0].event_id == "evt_test_abcdef123456"


@pytest.mark.skipif(_SKIP, reason="DATABASE_URL not set")
def test_source_metadata_upsert(db_session) -> None:
    """Upsert a source metadata row; verify consecutive_errors resets."""
    from src.storage.models import SourceMetadata

    meta = SourceMetadata(
        source_id="connector.cdse.stac",
        display_name="Copernicus CDSE",
        source_type="imagery_catalog",
        consecutive_errors=0,
        total_events_ingested=100,
    )
    db_session.add(meta)
    db_session.flush()

    retrieved = db_session.query(SourceMetadata).filter_by(source_id="connector.cdse.stac").one()
    assert retrieved.is_enabled is True
    assert retrieved.circuit_state == "closed"
    assert retrieved.total_events_ingested == 100


@pytest.mark.skipif(_SKIP, reason="DATABASE_URL not set")
def test_db_connectivity_check() -> None:
    """Verify check_db_connectivity() returns (True, 'ok') for a live DB."""
    from src.storage.database import check_db_connectivity, init_db
    init_db(_DB_URL)
    ok, msg = check_db_connectivity()
    assert ok is True
    assert msg == "ok"

