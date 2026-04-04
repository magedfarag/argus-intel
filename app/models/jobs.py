"""Async job state models."""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class JobState(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class Job:
    """Mutable job record stored in Redis hash or in-memory dict."""

    def __init__(self, job_id: str, request_data: Dict[str, Any]) -> None:
        self.job_id       = job_id
        self.state        = JobState.PENDING
        self.request_data = request_data
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at   = datetime.now(timezone.utc)
        self.updated_at   = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id":     self.job_id,
            "state":      self.state.value,
            "result":     self.result,
            "error":      self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
