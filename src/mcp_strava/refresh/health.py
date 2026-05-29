"""Refresh-health status shared between the in-process worker and the healthcheck.

The Docker healthcheck runs as a separate process and must NOT open the DuckDB
file (single-owner contention — see deploy decisions). The in-process refresh
worker therefore persists its last-cycle outcome to a small JSON file that the
healthcheck reads. A recurring refresh failure (e.g. a DuckDB fatal that the
worker loop otherwise swallows and retries forever) accumulates consecutive
failures and turns the container unhealthy, instead of failing silently.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

_DEFAULT_PATH = Path("/tmp/mcp-strava-refresh-health.json")
DEFAULT_MAX_CONSECUTIVE_FAILURES = 3


def health_path() -> Path:
    raw = os.environ.get("MCP_STRAVA_REFRESH_HEALTH_PATH")
    return Path(raw) if raw else _DEFAULT_PATH


def _now_iso() -> str:
    return datetime.now().isoformat()


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def record_cycle(outcome: str, *, error_type: str | None = None, error: str | None = None) -> None:
    """Persist the outcome of one refresh cycle. Best-effort; never raises.

    ``outcome`` is "ok" (cycle completed without error, incl. idle/skipped) or
    "error" (the cycle failed or raised). Consecutive failures accumulate on
    "error" and reset on any non-error outcome, so a persistent fatal is visible
    while a single transient failure does not flap container health.
    """
    path = health_path()
    try:
        current = _read(path)
        is_error = outcome == "error"
        failures = int(current.get("consecutive_failures", 0)) + 1 if is_error else 0
        payload = {
            "last_attempt_at": _now_iso(),
            "last_outcome": outcome,
            "consecutive_failures": failures,
            "last_error_type": error_type if is_error else None,
            "last_error": (error[:300] if error else None) if is_error else None,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except Exception:  # noqa: BLE001 — health recording must never break the worker loop
        pass


def _max_consecutive_failures() -> int:
    raw = os.environ.get("MCP_STRAVA_REFRESH_MAX_CONSECUTIVE_FAILURES")
    if raw is None:
        return DEFAULT_MAX_CONSECUTIVE_FAILURES
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_CONSECUTIVE_FAILURES


def check_refresh_health() -> None:
    """Raise RuntimeError when the refresh worker is persistently failing.

    No-op when the worker is disabled (read-only deployment) or when no health
    file exists yet (worker has not completed a first cycle — the Docker
    start-period covers that window). Does not open DuckDB.
    """
    from mcp_strava.deploy.service import _refresh_worker_enabled

    if not _refresh_worker_enabled():
        return
    path = health_path()
    if not path.exists():
        return
    data = _read(path)
    failures = int(data.get("consecutive_failures", 0))
    threshold = _max_consecutive_failures()
    if failures >= threshold:
        raise RuntimeError(
            f"refresh worker failing: {failures} consecutive failures (>= {threshold}); "
            f"last_error_type={data.get('last_error_type')}; last_error={data.get('last_error')}"
        )
