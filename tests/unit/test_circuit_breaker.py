"""Unit tests for CircuitBreaker (P2-2 — state transitions & resilience)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.app.resilience.circuit_breaker import CircuitBreaker


@pytest.fixture
def breaker():
    """Fresh circuit breaker instance."""
    return CircuitBreaker(
        failure_threshold=3,
        recovery_timeout_seconds=1,
        expected_exception=Exception,
    )


def test_circuit_breaker_init_closed(breaker):
    """Test circular breaker initializes in CLOSED state."""
    assert breaker.state == "CLOSED"
    assert breaker.failure_count == 0
    assert breaker.last_failure_time is None


def test_circuit_breaker_success_keeps_closed(breaker):
    """Test successful operation keeps breaker CLOSED."""
    breaker.record_success()
    assert breaker.state == "CLOSED"
    assert breaker.failure_count == 0


def test_circuit_breaker_failure_increments_count(breaker):
    """Test failures increment counter."""
    breaker.record_failure()
    assert breaker.failure_count == 1
    assert breaker.state == "CLOSED"

    breaker.record_failure()
    assert breaker.failure_count == 2
    assert breaker.state == "CLOSED"


def test_circuit_breaker_opens_after_threshold(breaker):
    """Test breaker OPENS after failure threshold exceeded."""
    # Trigger 2 failures
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "CLOSED"

    # Third failure should OPEN the breaker
    breaker.record_failure()
    assert breaker.failure_count == 3
    assert breaker.state == "OPEN"


def test_circuit_breaker_open_blocks_requests(breaker):
    """Test is_open() returns True when OPEN."""
    # Open the breaker
    for _ in range(3):
        breaker.record_failure()

    assert breaker.is_open() is True


def test_circuit_breaker_success_resets_in_closed(breaker):
    """Test success in CLOSED state resets failure count."""
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.failure_count == 2

    # Success should reset counter
    breaker.record_success()
    assert breaker.failure_count == 0
    assert breaker.state == "CLOSED"


def test_circuit_breaker_transitions_to_half_open_after_timeout(breaker):
    """Test breaker transitions to HALF_OPEN after recovery timeout."""
    # Open the breaker
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == "OPEN"

    # Wait for recovery timeout
    time.sleep(1.1)  # Slightly longer than recovery_timeout_seconds=1

    # Breaker should allow one test request (HALF_OPEN)
    assert breaker.state == "HALF_OPEN"


def test_circuit_breaker_closes_on_half_open_success(breaker):
    """Test breaker CLOSES after successful request in HALF_OPEN state."""
    # Open and wait for timeout
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == "OPEN"

    time.sleep(1.1)
    assert breaker.state == "HALF_OPEN"

    # Success in HALF_OPEN should close breaker
    breaker.record_success()
    assert breaker.state == "CLOSED"
    assert breaker.failure_count == 0


def test_circuit_breaker_reopens_on_half_open_failure(breaker):
    """Test breaker OPENS again if failure during HALF_OPEN."""
    # Open and wait
    for _ in range(3):
        breaker.record_failure()
    time.sleep(1.1)
    assert breaker.state == "HALF_OPEN"

    # Failure in HALF_OPEN should reopen
    breaker.record_failure()
    assert breaker.state == "OPEN"


def test_circuit_breaker_multiple_cycles(breaker):
    """Test multiple open/close cycles."""
    # Cycle 1: CLOSED → OPEN
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == "OPEN"

    # Wait and transition to HALF_OPEN
    time.sleep(1.1)
    assert breaker.state == "HALF_OPEN"

    # Success → CLOSED
    breaker.record_success()
    assert breaker.state == "CLOSED"

    # Cycle 2: CLOSED → OPEN again
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == "OPEN"

    # Wait and transition to HALF_OPEN
    time.sleep(1.1)
    assert breaker.state == "HALF_OPEN"

    # Success → CLOSED
    breaker.record_success()
    assert breaker.state == "CLOSED"


def test_circuit_breaker_custom_threshold(breaker):
    """Test custom failure threshold."""
    custom_breaker = CircuitBreaker(
        failure_threshold=5,
        recovery_timeout_seconds=1,
        expected_exception=Exception,
    )

    # Should remain CLOSED until 5 failures
    for i in range(1, 5):
        custom_breaker.record_failure()
        assert custom_breaker.state == "CLOSED", f"Failed at iteration {i}"

    # 5th failure should open
    custom_breaker.record_failure()
    assert custom_breaker.state == "OPEN"


def test_circuit_breaker_state_persistence(breaker):
    """Test state information persists across operations."""
    # Open the breaker
    for _ in range(3):
        breaker.record_failure()

    first_open_time = breaker.last_failure_time
    assert breaker.is_open() is True

    time.sleep(0.5)  # Less than recovery timeout

    # Should still be OPEN
    assert breaker.is_open() is True
    assert breaker.last_failure_time == first_open_time  # Time unchanged


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
