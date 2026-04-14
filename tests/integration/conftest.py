"""Integration test conftest — restores real credentials from .env for integration tests.

The root tests/conftest.py blanks all credentials for unit test isolation.
This conftest runs directly after it (pytest loads conftests root→leaf) and
restores DATABASE_URL and API keys before any integration test module is
imported, so module-level skip guards like ``_SKIP = not _DB_URL`` evaluate
correctly.
"""
from __future__ import annotations

import os
from pathlib import Path

# Load .env values into the environment before integration test modules import
_env_file = Path(__file__).parents[2] / ".env"
if _env_file.exists():
    with _env_file.open() as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _val = _line.partition("=")
            _key = _key.strip()
            _val = _val.strip()
            # Only restore if not already set by a higher-priority source
            if _key and _key not in os.environ or not os.environ.get(_key):
                os.environ[_key] = _val
