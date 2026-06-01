"""Runtime option parsing for deployed mcp-strava processes."""

from __future__ import annotations

import os
from pathlib import Path

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_DEFAULT_SUPERVISOR_STATE_PATH = Path("/tmp/mcp-strava-supervisor.json")


def refresh_worker_enabled() -> bool:
    raw_value = os.environ.get("MCP_STRAVA_REFRESH_WORKER_ENABLED")
    if raw_value is None:
        return True
    normalized = raw_value.strip().lower()
    if normalized in _FALSE_VALUES:
        return False
    return normalized in _TRUE_VALUES


def supervisor_state_path() -> Path:
    raw_path = os.environ.get("MCP_STRAVA_SUPERVISOR_STATE_PATH")
    return Path(raw_path) if raw_path else _DEFAULT_SUPERVISOR_STATE_PATH
