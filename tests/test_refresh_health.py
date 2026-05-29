"""Refresh-health status file + healthcheck integration.

The Docker healthcheck runs as a separate process and must not open DuckDB, so
the in-process worker persists its per-cycle outcome to a small JSON file that
the healthcheck reads. A recurring refresh failure (e.g. the DuckDB ART fatal
the worker loop swallows) must turn the container unhealthy instead of passing
silently.
"""

import json

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
