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
