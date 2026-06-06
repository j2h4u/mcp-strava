"""Aggregate metadata factory."""

from __future__ import annotations

from typing import Any

from mcp_strava.metric_registry_shared import (
    AGGREGATE_MODES,
    SUPPORTED_AGGREGATE_BUCKETS,
    SUPPORTED_AGGREGATE_SCOPES,
    SUPPORTED_ROLLING_WINDOW_DAYS,
)


def _agg(
    mode: str,
    source: str,
    *,
    denominator: str | None = None,
    weight_column: str | None = None,
    numerator_column: str | None = None,
    denominator_column: str | None = None,
    value_column: str | None = None,
    sample_size_column: str = "activity_count",
    supported_buckets: tuple[str, ...] = SUPPORTED_AGGREGATE_BUCKETS,
    supported_scopes: tuple[str, ...] = ("both",),
    quantiles: tuple[str, ...] = (),
    metric_version_policy: str = "mixed_degraded",
    rolling_window_days: int | None = None,
    fixed_rolling_window: bool = False,
) -> dict[str, Any]:
    if mode not in AGGREGATE_MODES:
        raise ValueError(f"Unknown aggregate mode: {mode}")
    unknown_buckets = set(supported_buckets) - set(SUPPORTED_AGGREGATE_BUCKETS)
    if unknown_buckets:
        raise ValueError(f"Unknown aggregate buckets: {sorted(unknown_buckets)}")
    unknown_scopes = set(supported_scopes) - set(SUPPORTED_AGGREGATE_SCOPES)
    if unknown_scopes:
        raise ValueError(f"Unknown aggregate scopes: {sorted(unknown_scopes)}")
    if rolling_window_days is not None and rolling_window_days not in SUPPORTED_ROLLING_WINDOW_DAYS:
        raise ValueError(f"Unknown rolling window days: {rolling_window_days}")
    return {
        "aggregate_mode": mode,
        "aggregate_source": source,
        "denominator": denominator,
        "weight_column": weight_column,
        "numerator_column": numerator_column,
        "denominator_column": denominator_column,
        "value_column": value_column,
        "sample_size_column": sample_size_column,
        "supported_buckets": list(supported_buckets),
        "supported_scopes": list(supported_scopes),
        "quantiles": list(quantiles),
        "metric_version_policy": metric_version_policy,
        "rolling_window_days": rolling_window_days,
        "fixed_rolling_window": fixed_rolling_window,
    }
