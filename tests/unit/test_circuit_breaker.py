"""Unit tests for CircuitBreaker (P2-2 — state transitions & resilience)."""
from __future__ import annotations

import time

import pytest

from app.resilience.circuit_breaker import CBState, CircuitBreaker


@pytest.fixture
def breaker():
    """Fresh circuit breaker instance with threshold=3, timeout=1 second."""
    return CircuitBreaker(failure_threshold=3, recovery_timeout=1)


def test_circuit_breaker_init_closed(breaker):
    """Test circuit breaker initializes in CLOSED state."""
    assert breaker.status("test_provider") == CBState.CLOSED
    assert breaker.is_open("test_provider") is False


def test_circuit_breaker_success_keeps_closed(breaker):
    """Test successful operation keeps breaker CLOSED."""
    breaker.record_success("test_provider")
    assert breaker.status("test_provider") == CBState.CLOSED
    assert breaker.is_open("test_provider") is False


def test_circuit_breaker_failure_increments_count(breaker):
    """Test failures increment internal counter but don't open immediately."""
    breaker.record_failure("test_provider")
    assert breaker.status("test_provider") == CBState.CLOSED
    assert breaker.is_open("test_provider") is False

    breaker.record_failure("test_provider")
    assert breaker.status("test_provider") == CBState.CLOSED
    assert breaker.is_open("test_provider") is False


def test_circuit_breaker_opens_after_threshold(breaker):
    """Test breaker OPENS after failure threshold exceeded."""
    # Trigger 2 failures
    breaker.record_failure("test_provider")
    breaker.record_failure("test_provider")
    assert breaker.status("test_provider") == CBState.CLOSED

    # Third failure should OPEN the breaker
    breaker.record_failure("test_provider")
    assert breaker.status("test_provider") == CBState.OPEN
    assert breaker.is_open("test_provider") is True


def test_circuit_breaker_open_blocks_requests(breaker):
    """Test is_open() returns True when OPEN."""
    # Open the breaker
    for _ in range(3):
        breaker.record_failure("test_provider")

    assert breaker.is_open("test_provider") is True
    assert breaker.status("test_provider") == CBState.OPEN


def test_circuit_breaker_success_resets_in_closed(breaker):
    """Test success in CLOSED state resets failure count."""
    breaker.record_failure("test_provider")
    breaker.record_failure("test_provider")
    assert breaker.status("test_provider") == CBState.CLOSED

    # Success should reset counter
    breaker.record_success("test_provider")
    assert breaker.status("test_provider") == CBState.CLOSED
    assert breaker.is_open("test_provider") is False


def test_circuit_breaker_transitions_to_half_open_after_timeout(breaker):
    """Test breaker transitions to HALF_OPEN after recovery timeout."""
    # Open the breaker
    for _ in range(3):
        breaker.record_failure("test_provider")
    assert breaker.status("test_provider") == CBState.OPEN

    # Wait for recovery timeout and check is_open (which should transition to HALF_OPEN)
    time.sleep(1.1)  # Slightly longer than recovery_timeout=1
    assert breaker.is_open("test_provider") is False  # HALF_OPEN allows probe
    assert breaker.status("test_provider") == CBState.HALF_OPEN


def test_circuit_breaker_closes_on_half_open_success(breaker):
    """Test breaker CLOSES after successful request in HALF_OPEN state."""
    # Open and wait for timeout
    for _ in range(3):
        breaker.record_failure("test_provider")
    assert breaker.status("test_provider") == CBState.OPEN

    time.sleep(1.1)
    # Transition to HALF_OPEN via is_open check
    assert breaker.is_open("test_provider") is False
    assert breaker.status("test_provider") == CBState.HALF_OPEN

    # Success in HALF_OPEN should close breaker
    breaker.record_success("test_provider")
    assert breaker.status("test_provider") == CBState.CLOSED
    assert breaker.is_open("test_provider") is False


def test_circuit_breaker_reopens_on_half_open_failure(breaker):
    """Test breaker OPENS again if failure during HALF_OPEN."""
    # Open and wait
    for _ in range(3):
        breaker.record_failure("test_provider")
    time.sleep(1.1)
    # Transition to HALF_OPEN
    assert breaker.is_open("test_provider") is False
    assert breaker.status("test_provider") == CBState.HALF_OPEN

    # Failure in HALF_OPEN should reopen
    breaker.record_failure("test_provider")
    assert breaker.status("test_provider") == CBState.OPEN
    assert breaker.is_open("test_provider") is True


def test_circuit_breaker_multiple_cycles(breaker):
    """Test multiple open/close cycles."""
    # Cycle 1: CLOSED → OPEN
    for _ in range(3):
        breaker.record_failure("test_provider")
    assert breaker.status("test_provider") == CBState.OPEN

    # Wait and transition to HALF_OPEN
    time.sleep(1.1)
    assert breaker.is_open("test_provider") is False
    assert breaker.status("test_provider") == CBState.HALF_OPEN

    # Success → CLOSED
    breaker.record_success("test_provider")
    assert breaker.status("test_provider") == CBState.CLOSED

    # Cycle 2: CLOSED → OPEN again
    for _ in range(3):
        breaker.record_failure("test_provider")
    assert breaker.status("test_provider") == CBState.OPEN

    # Wait and transition to HALF_OPEN
    time.sleep(1.1)
    assert breaker.is_open("test_provider") is False
    assert breaker.status("test_provider") == CBState.HALF_OPEN

    # Success → CLOSED
    breaker.record_success("test_provider")
    assert breaker.status("test_provider") == CBState.CLOSED


def test_circuit_breaker_custom_threshold(breaker):
    """Test custom failure threshold."""
    custom_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=1)

    # Should remain CLOSED until 5 failures
    for i in range(1, 5):
        custom_breaker.record_failure("test_provider")
        assert (
            custom_breaker.status("test_provider") == CBState.CLOSED
        ), f"Failed at iteration {i}"

    # 5th failure should open
    custom_breaker.record_failure("test_provider")
    assert custom_breaker.status("test_provider") == CBState.OPEN


def test_circuit_breaker_per_provider_isolation(breaker):
    """Test that circuit breaker tracks state per provider separately."""
    # Provider A fails 3 times → OPEN
    for _ in range(3):
        breaker.record_failure("provider_a")
    assert breaker.status("provider_a") == CBState.OPEN

    # Provider B should be CLOSED independently
    assert breaker.status("provider_b") == CBState.CLOSED

    # Success on provider B should have no effect on provider A
    breaker.record_success("provider_b")
    assert breaker.status("provider_a") == CBState.OPEN
    assert breaker.status("provider_b") == CBState.CLOSED


def test_circuit_breaker_sentinel2_success(breaker):
    """Test Sentinel-2 provider state: success keeps breaker CLOSED."""
    breaker.record_success("sentinel2")
    assert breaker.status("sentinel2") == CBState.CLOSED
    assert breaker.is_open("sentinel2") is False


def test_circuit_breaker_sentinel2_open_after_failures(breaker):
    """Test Sentinel-2 provider state: OPEN after failures."""
    for _ in range(3):
        breaker.record_failure("sentinel2")
    assert breaker.status("sentinel2") == CBState.OPEN
    assert breaker.is_open("sentinel2") is True


def test_circuit_breaker_landsat_state_independent(breaker):
    """Test Landsat provider state independent of Sentinel-2."""
    # Sentinel-2 fails
    for _ in range(3):
        breaker.record_failure("sentinel2")
    assert breaker.status("sentinel2") == CBState.OPEN
    
    # Landsat should still be CLOSED
    assert breaker.status("landsat") == CBState.CLOSED
    
    # Landsat success should not affect Sentinel-2
    breaker.record_success("landsat")
    assert breaker.status("sentinel2") == CBState.OPEN
    assert breaker.status("landsat") == CBState.CLOSED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
