"""Structured logging configuration.

Call configure_logging() once during application startup.
All subsequent loggers created with logging.getLogger(__name__)
will emit JSON lines in production or coloured text in development.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Dict


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON object.

    Enriched fields bound via ``logging.LoggerAdapter`` or the ``extra=``
    keyword are automatically promoted to the top-level JSON object so
    log aggregation systems can index them without parsing the message string.
    """

    # All context keys we promote to the top level (P0-5.2)
    _CONTEXT_KEYS = frozenset({
        "request_id",
        "job_id",
        "provider",
        "aoi_id",
        "aoi_hash",
        "connector",
        "source",
        "event_id",
        "session_id",
        "duration_ms",
    })

    def format(self, record: logging.LogRecord) -> str:  # noqa: D102
        payload: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in self._CONTEXT_KEYS:
            if key in record.__dict__:
                payload[key] = record.__dict__[key]

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class _TextFormatter(logging.Formatter):
    _COLOURS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self._COLOURS.get(record.levelname, "")
        ts = time.strftime("%H:%M:%S", time.gmtime(record.created))
        msg = record.getMessage()
        return f"{colour}{ts} [{record.levelname:<8}] {record.name}: {msg}{self._RESET}"


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure root logger with the chosen level and format.

    Args:
        level: Python log level string (DEBUG, INFO, WARNING, ERROR).
        fmt:   "json" for structured JSON logs, "text" for human-readable.
    """
    formatter: logging.Formatter
    if fmt == "json":
        formatter = _JsonFormatter()
    else:
        formatter = _TextFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # Quieten noisy third-party loggers
    for lib in ("uvicorn.access", "celery.app.trace", "httpx"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str, **context: Any) -> logging.LoggerAdapter:  # type: ignore[type-arg]
    """Return a LoggerAdapter that injects structured context into every record.

    Usage (P0-5.2)::

        log = get_logger(__name__, connector="connector.cdse.stac", aoi_id="abc123")
        log.info("Scene ingested", extra={"event_id": evt.event_id})

    The merged context is emitted as top-level JSON keys by ``_JsonFormatter``.
    """
    base = logging.getLogger(name)
    return logging.LoggerAdapter(base, context)
