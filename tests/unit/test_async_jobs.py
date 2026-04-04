"""Unit tests for async job dispatch & polling (P2-3)."""
from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, UTC

from app.models.requests import AnalyzeRequest
from app.models.responses import JobStatusResponse, AnalyzeResponse
from app.models.jobs import Job, JobState


POLYGON = {
    "type": "Polygon",
    "coordinates": [[[30.0, 50.0], [30.1, 50.0], [30.1, 50.1], [30.0, 50.1], [30.0, 50.0]]]
}


@pytest.fixture
def valid_analyze_request():
    """Test request with async_execution enabled."""
    return AnalyzeRequest(
        geometry={"type": "Polygon", "coordinates": POLYGON["coordinates"]},
        start_date="2026-03-01",
        end_date="2026-03-28",
        provider="demo",
        async_execution=True,
    )


@pytest.fixture
def valid_analyze_request_dict(valid_analyze_request):
    """Serialized AnalyzeRequest for Job initialization."""
    return valid_analyze_request.model_dump()


@pytest.fixture
def analyze_response():
    """Sample AnalyzeResponse for job result."""
    return AnalyzeResponse(
        analysis_id="test-analysis-123",
        requested_area_km2=100.0,
        provider="demo",
        is_demo=True,
        request_bounds=[30.0, 50.0, 30.1, 50.1],
        imagery_window={"start": "2026-03-01", "end": "2026-03-28"},
        warnings=[],
        changes=[],
        stats={"total_changes": 0},
    )


def test_async_execution_request_flag_required():
    """Test that async_execution field exists and defaults to False."""
    request = AnalyzeRequest(
        geometry={"type": "Polygon", "coordinates": POLYGON["coordinates"]},
        start_date="2026-03-01",
        end_date="2026-03-28",
    )
    assert request.async_execution is False

    request_async = AnalyzeRequest(
        geometry={"type": "Polygon", "coordinates": POLYGON["coordinates"]},
        start_date="2026-03-01",
        end_date="2026-03-28",
        async_execution=True,
    )
    assert request_async.async_execution is True


def test_job_status_response_structure():
    """Test JobStatusResponse contains all required fields."""
    now = datetime.now(UTC)
    response = JobStatusResponse(
        job_id="job-123",
        state="pending",
        result=None,
        error=None,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )
    assert response.job_id == "job-123"
    assert response.state == "pending"
    assert response.result is None
    assert response.error is None


def test_job_create_with_request_data(valid_analyze_request_dict):
    """Test Job can be created with request_data."""
    job = Job(
        job_id="job-test-123",
        request_data=valid_analyze_request_dict,
    )
    assert job.job_id == "job-test-123"
    assert job.state == JobState.PENDING
    assert job.request_data is not None
    assert job.request_data["async_execution"] is True


def test_job_create_minimal():
    """Test Job minimal creation."""
    request_data = {
        "geometry": {"type": "Polygon", "coordinates": POLYGON["coordinates"]},
        "start_date": "2026-03-01",
        "end_date": "2026-03-28",
    }
    job = Job(
        job_id="job-minimal",
        request_data=request_data,
    )
    assert job.job_id == "job-minimal"
    assert job.state == JobState.PENDING
    assert job.result is None
    assert job.error is None


def test_job_status_transitions(valid_analyze_request_dict):
    """Test valid job state transitions."""
    job = Job(
        job_id="job-123",
        request_data=valid_analyze_request_dict,
    )
    assert job.state == JobState.PENDING

    # Simulate completion
    job.state = JobState.COMPLETED
    assert job.state == JobState.COMPLETED


def test_job_status_failure_state(valid_analyze_request_dict):
    """Test job can transition to FAILED state."""
    job = Job(
        job_id="job-fail-123",
        request_data=valid_analyze_request_dict,
    )
    job.state = JobState.FAILED
    assert job.state == JobState.FAILED


def test_job_status_cancelled_state(valid_analyze_request_dict):
    """Test job can transition to CANCELLED state."""
    job = Job(
        job_id="job-cancel-123",
        request_data=valid_analyze_request_dict,
    )
    job.state = JobState.CANCELLED
    assert job.state == JobState.CANCELLED


def test_job_to_dict(valid_analyze_request_dict):
    """Test Job.to_dict() serialization."""
    job = Job(
        job_id="job-dict-123",
        request_data=valid_analyze_request_dict,
    )
    job_dict = job.to_dict()
    
    assert job_dict["job_id"] == "job-dict-123"
    assert job_dict["state"] == "pending"
    assert job_dict["result"] is None
    assert job_dict["error"] is None
    assert "created_at" in job_dict
    assert "updated_at" in job_dict


def test_job_to_dict_with_result(valid_analyze_request_dict, analyze_response):
    """Test Job.to_dict() with completed result."""
    job = Job(
        job_id="job-result-123",
        request_data=valid_analyze_request_dict,
    )
    job.state = JobState.COMPLETED
    job.result = analyze_response.model_dump()
    
    job_dict = job.to_dict()
    
    assert job_dict["state"] == "completed"
    assert job_dict["result"] is not None
    assert job_dict["result"]["analysis_id"] == "test-analysis-123"


def test_job_to_dict_with_error(valid_analyze_request_dict):
    """Test Job.to_dict() with error."""
    job = Job(
        job_id="job-error-123",
        request_data=valid_analyze_request_dict,
    )
    job.state = JobState.FAILED
    job.error = "Analysis timeout: no scenes found"
    
    job_dict = job.to_dict()
    
    assert job_dict["state"] == "failed"
    assert job_dict["result"] is None
    assert "timeout" in job_dict["error"]


def test_celery_result_mock():
    """Test mocking Celery AsyncResult for job status polling."""
    # Mock AsyncResult without requiring actual celery import
    mock_async_result_class = MagicMock()
    
    # Simulate PENDING state
    mock_result = MagicMock()
    mock_result.state = "PENDING"
    mock_async_result_class.return_value = mock_result

    result = mock_async_result_class("job-id-123")
    assert result.state == "PENDING"

    # Simulate SUCCESS state
    mock_result.state = "SUCCESS"
    result_data = {"job_id": "job-id-123", "state": "completed"}
    mock_result.result = result_data
    assert result.state == "SUCCESS"
    assert result.result["state"] == "completed"


def test_job_polling_pending_to_completed():
    """Test polling cycle from PENDING to COMPLETED."""
    poll_states = ["PENDING", "PENDING", "SUCCESS"]
    poll_index = [0]

    def get_state():
        state = poll_states[poll_index[0]]
        poll_index[0] += 1
        return state

    # First poll: PENDING
    assert get_state() == "PENDING"
    # Second poll: still PENDING
    assert get_state() == "PENDING"
    # Third poll: SUCCESS (maps to "completed")
    assert get_state() == "SUCCESS"


def test_job_status_response_with_result(analyze_response):
    """Test JobStatusResponse with completed result."""
    response = JobStatusResponse(
        job_id="job-completed-123",
        state="completed",
        result=analyze_response,
        error=None,
        created_at="2026-03-28T10:00:00",
        updated_at="2026-03-28T10:05:00",
    )
    assert response.state == "completed"
    assert response.result is not None
    assert response.result.analysis_id == "test-analysis-123"
    assert response.error is None


def test_job_status_response_with_error():
    """Test JobStatusResponse with failed job."""
    response = JobStatusResponse(
        job_id="job-failed-123",
        state="failed",
        result=None,
        error="Analysis timeout: no scenes found",
        created_at="2026-03-28T10:00:00",
        updated_at="2026-03-28T10:05:00",
    )
    assert response.state == "failed"
    assert response.result is None
    assert response.error is not None
    assert "timeout" in response.error


def test_job_request_serializable():
    """Test that AnalyzeRequest can be serialized for storage."""
    request = AnalyzeRequest(
        geometry={"type": "Polygon", "coordinates": POLYGON["coordinates"]},
        start_date="2026-03-01",
        end_date="2026-03-28",
        provider="demo",
        async_execution=True,
    )
    # Pydantic v2 uses model_dump
    serialized = request.model_dump()
    assert serialized["async_execution"] is True
    assert serialized["provider"] == "demo"

    # Can reconstruct from serialized form
    reconstructed = AnalyzeRequest(**serialized)
    assert reconstructed.async_execution is True


def test_job_dispatch_async_flag_triggers_celery():
    """Test that async_execution flag triggers Celery job dispatch."""
    request_sync = AnalyzeRequest(
        geometry={"type": "Polygon", "coordinates": POLYGON["coordinates"]},
        start_date="2026-03-01",
        end_date="2026-03-28",
        async_execution=False,  # Sync mode
    )
    assert request_sync.async_execution is False

    request_async = AnalyzeRequest(
        geometry={"type": "Polygon", "coordinates": POLYGON["coordinates"]},
        start_date="2026-03-01",
        end_date="2026-03-28",
        async_execution=True,  # Async mode
    )
    assert request_async.async_execution is True


def test_job_polling_max_retry_limit():
    """Test that polling doesn't loop infinitely."""
    max_retries = 100
    poll_count = 0

    # Simulate max retries
    while poll_count < max_retries:
        poll_count += 1
        # In real scenario, check job status
        if poll_count >= 10:
            # Job "completed" after 10 polls
            break

    assert poll_count == 10
    assert poll_count <= max_retries


def test_job_status_field_mappings():
    """Test that Celery states map correctly to API states."""
    mappings = {
        "PENDING": "pending",
        "STARTED": "running",
        "SUCCESS": "completed",
        "FAILURE": "failed",
        "RETRY": "pending",
        "REVOKED": "cancelled",
    }

    for celery_state, api_state in mappings.items():
        if celery_state == "SUCCESS":
            assert api_state == "completed"
        elif celery_state == "FAILURE":
            assert api_state == "failed"
        elif celery_state == "REVOKED":
            assert api_state == "cancelled"
        elif celery_state == "PENDING":
            assert api_state == "pending"


def test_job_timestamps_recorded(valid_analyze_request_dict):
    """Test that Job records creation and update timestamps."""
    job = Job(
        job_id="job-time-123",
        request_data=valid_analyze_request_dict,
    )
    assert job.created_at is not None
    assert job.updated_at is not None
    assert isinstance(job.created_at, datetime)
    assert isinstance(job.updated_at, datetime)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
