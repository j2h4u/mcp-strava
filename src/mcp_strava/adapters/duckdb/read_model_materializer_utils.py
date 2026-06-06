"""Shared helpers for read-model materialization."""

from __future__ import annotations

import json
from datetime import date, timedelta
from statistics import median


def _date_range(start_day: str, end_day: str) -> list[str]:
    current = date.fromisoformat(start_day)
    end = date.fromisoformat(end_day)
    days: list[str] = []
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _json_list(values: list[str]) -> str:
    return json.dumps(sorted(set(values)), ensure_ascii=True)


def _median_or_none(values: list[float | None]) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return round(float(median(numeric)), 3) if numeric else None


_HR_REST_MISSING_MSG = (
    "MCP_STRAVA_HR_REST is not set — cannot compute HR zones. "
    "Set MCP_STRAVA_HR_REST to the athlete's resting heart rate."
)
