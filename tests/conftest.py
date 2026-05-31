"""Shared pytest fixtures for the mcp_strava test suite."""

import os

import pytest

from mcp_strava.settings import reset_settings_cache


@pytest.fixture(autouse=True, scope="session")
def set_hr_rest_env():
    """Ensure MCP_STRAVA_HR_REST=53 is set for the entire test session.

    This fixture sets the environment variable if it is not already set,
    guaranteeing that all tests that exercise HR-zone computation have a
    valid resting HR without requiring a .env file or external configuration.
    """
    os.environ.setdefault("MCP_STRAVA_HR_REST", "53")
    yield
    # leave set — the test process exits anyway


@pytest.fixture(autouse=True)
def reset_settings():
    """Reset the settings cache before and after each test.

    This prevents settings loaded (or not loaded) in one test from leaking
    into the next, particularly important for tests that temporarily modify
    MCP_STRAVA_* environment variables.
    """
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture(autouse=True)
def isolate_refresh_health_path(tmp_path, monkeypatch):
    """Isolate the refresh-health status file per test.

    The in-process worker records each cycle's outcome to a global default file
    (/tmp/mcp-strava-refresh-health.json) that the container healthcheck reads.
    Without isolation, a test that simulates a worker fatal would pollute that
    shared file and fail unrelated healthcheck tests downstream. Give each test
    its own path; tests that exercise the health behaviour override it.
    """
    monkeypatch.setenv("MCP_STRAVA_REFRESH_HEALTH_PATH", str(tmp_path / "refresh-health.json"))
    yield


@pytest.fixture(autouse=True)
def reset_read_connections():
    """Close thread-local read connections around each test.

    Read services reuse a connection per (thread, db path). Tests use a fresh
    tmp_path DB each, so a cached connection from a prior test must not leak
    into the next. Tests passing an explicit ``connection=`` are unaffected.
    """
    from mcp_strava.adapters.duckdb.connection import reset_thread_connections

    reset_thread_connections()
    yield
    reset_thread_connections()


@pytest.fixture(autouse=True)
def reset_tool_response_cache():
    """Clear the MCP tool-response cache around each test.

    interfaces.mcp_http._TOOL_RESPONSE_CACHE is a module-level singleton that
    survives between tests. Without isolation, a test exercising a cached tool
    can inherit or leak entries to/from whichever test ran before it in the
    collection order. This replaces per-test manual .clear() calls that a new
    test author could easily forget.
    """
    from mcp_strava.interfaces.mcp_http import _TOOL_RESPONSE_CACHE

    _TOOL_RESPONSE_CACHE.clear()
    yield
    _TOOL_RESPONSE_CACHE.clear()
