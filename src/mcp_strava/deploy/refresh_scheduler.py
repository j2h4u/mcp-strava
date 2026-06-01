"""Refresh-worker lifecycle for the deployed owner process."""

from __future__ import annotations

import threading

import mcp_strava.settings as settings_module
from mcp_strava.deploy.runtime_options import refresh_worker_enabled
from mcp_strava.deploy.service_events import emit_service_event
from mcp_strava.refresh import worker as refresh_worker


def require_hr_config_for_worker() -> None:
    """Fail fast at startup if the refresh worker is enabled but HR_REST is unset.

    The in-process refresh worker materializes read-model facts, which computes
    HR zones and therefore requires MCP_STRAVA_HR_REST. Without this eager check
    the owner process starts healthy and only fails later, on the first refresh
    pass. A read-only deployment that disables the worker does not need HR_REST.
    """
    if not refresh_worker_enabled():
        return

    if settings_module.get_settings().athlete.hr_rest is None:
        emit_service_event("service_startup_aborted", reason="hr_rest_unset")
        raise RuntimeError(
            "MCP_STRAVA_HR_REST is not set — the in-process refresh worker "
            "cannot compute HR zones. Set MCP_STRAVA_HR_REST to the athlete's "
            "resting heart rate, or disable MCP_STRAVA_REFRESH_WORKER_ENABLED "
            "for a read-only runtime."
        )


def start_refresh_scheduler(stop_event: threading.Event) -> threading.Thread | None:
    if not refresh_worker_enabled():
        return None

    refresh_thread = threading.Thread(
        target=refresh_worker.run_forever,
        kwargs={"stop_event": stop_event, "emit_start": True},
        name="mcp-strava-refresh",
        daemon=True,
    )
    refresh_thread.start()
    emit_service_event("service_refresh_scheduler_started", mode="in-process")
    return refresh_thread
