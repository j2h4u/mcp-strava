"""Refresh-health status file + healthcheck integration.

The Docker healthcheck runs as a separate process and must not open DuckDB, so
the in-process worker persists its per-cycle outcome to a small JSON file that
the healthcheck reads. A recurring refresh failure (e.g. the DuckDB ART fatal
the worker loop swallows) must turn the container unhealthy instead of passing
silently.
"""

import json
from datetime import datetime, timedelta

import pytest

from mcp_strava.refresh import health


@pytest.fixture(autouse=True)
def _isolate_health_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_STRAVA_REFRESH_HEALTH_PATH", str(tmp_path / "refresh-health.json"))
    monkeypatch.setenv("MCP_STRAVA_REFRESH_WORKER_ENABLED", "true")
    # default threshold unless a test overrides it
    monkeypatch.delenv("MCP_STRAVA_REFRESH_MAX_CONSECUTIVE_FAILURES", raising=False)


def test_record_cycle_accumulates_failures_and_resets_on_ok():
    health.record_cycle("error", error_type="FatalException", error="boom")
    health.record_cycle("error", error_type="FatalException", error="boom")
    data = json.loads(health.health_path().read_text())
    assert data["consecutive_failures"] == 2
    assert data["last_outcome"] == "error"
    assert data["last_error_type"] == "FatalException"

    health.record_cycle("ok")
    data = json.loads(health.health_path().read_text())
    assert data["consecutive_failures"] == 0
    assert data["last_outcome"] == "ok"
    assert data["last_error_type"] is None


def test_idle_cycle_counts_as_healthy_and_resets_failures():
    health.record_cycle("error", error_type="X", error="x")
    health.record_cycle("idle")
    data = json.loads(health.health_path().read_text())
    assert data["consecutive_failures"] == 0


def test_check_refresh_health_passes_below_threshold():
    health.record_cycle("error", error_type="X", error="x")
    health.record_cycle("error", error_type="X", error="x")
    health.check_refresh_health()  # 2 < default threshold 3 -> no raise


def test_check_refresh_health_fails_at_threshold():
    for _ in range(3):
        health.record_cycle("error", error_type="FatalException", error="index corrupt")
    with pytest.raises(RuntimeError, match="consecutive failures"):
        health.check_refresh_health()


def test_check_refresh_health_noop_when_no_file_yet():
    # worker has not recorded a cycle; healthcheck must not flap during start-up
    health.check_refresh_health()


def test_check_refresh_health_noop_when_worker_disabled(monkeypatch):
    monkeypatch.setenv("MCP_STRAVA_REFRESH_WORKER_ENABLED", "false")
    for _ in range(5):
        health.record_cycle("error", error_type="X", error="x")
    health.check_refresh_health()  # disabled worker -> refresh health is not a container concern


def test_threshold_is_configurable(monkeypatch):
    monkeypatch.setenv("MCP_STRAVA_REFRESH_MAX_CONSECUTIVE_FAILURES", "1")
    health.record_cycle("error", error_type="X", error="x")
    with pytest.raises(RuntimeError):
        health.check_refresh_health()


def test_check_refresh_health_fails_when_last_attempt_is_stale():
    # A silently-dead worker: the health file exists with no failures recorded,
    # but last_attempt_at is far older than the staleness limit because the
    # thread stopped rewriting it. The failure counter never trips, so the age
    # check is the only thing that catches this.
    stale = (datetime.now() - timedelta(seconds=10_000)).isoformat()
    health.health_path().write_text(
        json.dumps({"last_attempt_at": stale, "last_outcome": "ok", "consecutive_failures": 0})
    )
    with pytest.raises(RuntimeError, match="stale"):
        health.check_refresh_health()


def test_check_refresh_health_passes_when_recently_attempted():
    # A live worker rewrites last_attempt_at every cycle; a fresh timestamp with
    # no failures must not trip the staleness guard.
    health.record_cycle("ok")
    health.check_refresh_health()  # no raise


def test_staleness_limit_respects_poll_and_cycles(monkeypatch):
    monkeypatch.setenv("MCP_STRAVA_REFRESH_POLL_SECONDS", "120")
    monkeypatch.setenv("MCP_STRAVA_REFRESH_MAX_STALE_CYCLES", "4")
    # 120 * 4 = 480 > floor 300
    assert health._staleness_limit_seconds() == 480
    # Floor wins for short poll intervals.
    monkeypatch.setenv("MCP_STRAVA_REFRESH_POLL_SECONDS", "10")
    monkeypatch.setenv("MCP_STRAVA_REFRESH_MAX_STALE_CYCLES", "5")
    assert health._staleness_limit_seconds() == health._MIN_STALENESS_LIMIT_SECONDS
