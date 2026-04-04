"""HTTP retry helper using tenacity with exponential backoff + jitter.

Confirmed pattern from tenacity docs:
    wait_random_exponential(multiplier=1, max=60) is the recommended
    strategy for distributed services to avoid synchronized retries.
"""
from __future__ import annotations

import logging
from typing import Callable, Tuple, Type

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
    before_sleep_log,
)

log = logging.getLogger(__name__)


def with_retry(
    max_attempts: int = 3,
    max_wait_s: float = 60.0,
    retry_on: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator factory for retrying functions with full jitter backoff.

    Args:
        max_attempts:  Maximum number of total attempts (including first).
        max_wait_s:    Maximum wait seconds between retries.
        retry_on:      Exception types that trigger a retry.

    Usage::

        @with_retry(max_attempts=3)
        def call_external_api():
            ...
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_random_exponential(multiplier=1, max=max_wait_s),
        retry=retry_if_exception_type(retry_on),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
