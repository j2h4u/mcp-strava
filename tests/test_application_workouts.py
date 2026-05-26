from __future__ import annotations

import importlib.util
from typing import get_type_hints

from mcp_strava.types import ServiceEnvelope


def test_legacy_workouts_application_module_is_retired() -> None:
    assert importlib.util.find_spec("mcp_strava.application.workouts") is None


def test_metric_services_are_current_workout_application_surface() -> None:
    from mcp_strava.application.metric_services import get_workout_detail_service, list_workouts_service

    assert get_type_hints(list_workouts_service)["return"] == ServiceEnvelope
    assert get_type_hints(get_workout_detail_service)["return"] == ServiceEnvelope
