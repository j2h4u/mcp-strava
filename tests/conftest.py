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
def reset_read_connections():
    """Close thread-local read connections around each test.

    Read services reuse a connection per (thread, db path). Tests use a fresh
    tmp_path DB each, so a cached connection from a prior test must not leak
    into the next. Tests passing an explicit ``connection=`` are unaffected.
    """
    from mcp_strava.db import reset_thread_connections

    reset_thread_connections()
    yield
    reset_thread_connections()
