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
import sys
from datetime import datetime
from pathlib import Path
from typing import cast

_DEFAULT_PATH = Path("/tmp/mcp-strava-refresh-health.json")
DEFAULT_MAX_CONSECUTIVE_FAILURES = 3
DEFAULT_MAX_STALE_CYCLES = 5
# Floor so a short poll interval cannot flap health on a single slow cycle.
_MIN_STALENESS_LIMIT_SECONDS = 300


def health_path() -> Path:
    raw = os.environ.get("MCP_STRAVA_REFRESH_HEALTH_PATH")
    return Path(raw) if raw else _DEFAULT_PATH


def _now_iso() -> str:
    # Self-consistent local pair with the age read below (health file written + read on the
    # same host); WR-02 deliberately left this local since it never crosses the UTC boundary.
    return datetime.now().isoformat()  # noqa: DTZ005


def _read(path: Path) -> dict[str, object]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}  # no health file yet (cold start before the first cycle)
    # Corrupt JSON / non-object fails loud — the file is written atomically
    # (tmp + rename) by record_cycle, so corruption is a real bug, not a state
    # to silently paper over with an empty dict (which would read as "healthy").
    parsed = cast(object, json.loads(raw))
    if not isinstance(parsed, dict):
        raise ValueError(f"health file is not a JSON object: {path}")
    return parsed


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
        prev_failures = current.get("consecutive_failures", 0)
        failures = (int(prev_failures) if isinstance(prev_failures, (int, float, str)) else 0) + 1 if is_error else 0
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
    except Exception as exc:  # health recording must never break the worker loop
        print(
            f"refresh health recording failed: {type(exc).__name__}: {str(exc)[:200]}",
            file=sys.stderr,
            flush=True,
        )


def _max_consecutive_failures() -> int:
    raw = os.environ.get("MCP_STRAVA_REFRESH_MAX_CONSECUTIVE_FAILURES")
    if raw is None:
        return DEFAULT_MAX_CONSECUTIVE_FAILURES
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_CONSECUTIVE_FAILURES


def _poll_seconds() -> int:
    raw = os.environ.get("MCP_STRAVA_REFRESH_POLL_SECONDS")
    if raw is None:
        return 60
    try:
        return max(5, int(raw))
    except ValueError:
        return 60


def _max_stale_cycles() -> int:
    raw = os.environ.get("MCP_STRAVA_REFRESH_MAX_STALE_CYCLES")
    if raw is None:
        return DEFAULT_MAX_STALE_CYCLES
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_STALE_CYCLES


def _staleness_limit_seconds() -> int:
    """How old last_attempt_at may get before the worker is presumed dead."""
    return max(_poll_seconds() * _max_stale_cycles(), _MIN_STALENESS_LIMIT_SECONDS)


def check_refresh_health() -> None:
    """Raise RuntimeError when the refresh worker is persistently failing.

    No-op when the worker is disabled (read-only deployment) or when no health
    file exists yet (worker has not completed a first cycle — the Docker
    start-period covers that window). Does not open DuckDB.
    """
    from mcp_strava.deploy.runtime_options import refresh_worker_enabled

    if not refresh_worker_enabled():
        return
    path = health_path()
    if not path.exists():
        return
    data = _read(path)
    raw_failures = data.get("consecutive_failures", 0)
    failures = int(raw_failures) if isinstance(raw_failures, (int, float, str)) else 0
    threshold = _max_consecutive_failures()
    if failures >= threshold:
        raise RuntimeError(
            f"refresh worker failing: {failures} consecutive failures (>= {threshold}); "
            f"last_error_type={data.get('last_error_type')}; last_error={data.get('last_error')}"
        )

    # Silent-death guard: a live worker rewrites last_attempt_at every poll cycle
    # (even idle cycles record "ok"). If the refresh thread dies without raising
    # — killed by a signal, or it exits — the failure counter freezes below the
    # threshold above and never trips. Detect the frozen counter by the age of
    # last_attempt_at instead. Timestamps are naive-local on both sides (the
    # worker writes datetime.now().isoformat(); the healthcheck runs on the same
    # host), so the subtraction is consistent.
    last_attempt = data.get("last_attempt_at")
    if last_attempt:
        try:
            age = (datetime.now() - datetime.fromisoformat(str(last_attempt))).total_seconds()  # noqa: DTZ005 — local pair with _now_iso (same-host write/read)
        except TypeError, ValueError:
            age = None
        if age is not None:
            limit = _staleness_limit_seconds()
            if age > limit:
                raise RuntimeError(
                    f"refresh worker stale: last attempt {int(age)}s ago (> {limit}s); "
                    f"the worker thread may have died silently (last_outcome={data.get('last_outcome')})"
                )
