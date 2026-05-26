from __future__ import annotations

import importlib.util
from typing import get_type_hints

from mcp_strava.types import ServiceEnvelope


def test_legacy_report_application_module_is_retired() -> None:
    assert importlib.util.find_spec("mcp_strava.application.reports") is None


def test_product_fact_report_services_are_current_application_surface() -> None:
    from mcp_strava.application.product_facts import (
        get_daily_brief_facts_service,
        get_historical_facts_service,
        get_weekly_digest_facts_service,
    )

    assert get_type_hints(get_daily_brief_facts_service)["return"] == ServiceEnvelope
    assert get_type_hints(get_weekly_digest_facts_service)["return"] == ServiceEnvelope
    assert get_type_hints(get_historical_facts_service)["return"] == ServiceEnvelope
