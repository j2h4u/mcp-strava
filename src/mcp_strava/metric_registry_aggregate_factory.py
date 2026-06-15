"""Aggregate metadata factory."""

from __future__ import annotations

from typing import Any

from mcp_strava.metric_registry_shared import (
    AGGREGATE_MODES,
    SUPPORTED_AGGREGATE_BUCKETS,
    SUPPORTED_AGGREGATE_SCOPES,
    SUPPORTED_ROLLING_WINDOW_DAYS,
)
from mcp_strava.metric_registry_specs import AggSpec


def _agg(mode: str, source: str, spec: AggSpec = AggSpec()) -> dict[str, Any]:  # noqa: B008
    if mode not in AGGREGATE_MODES:
        raise ValueError(f"Unknown aggregate mode: {mode}")
    unknown_buckets = set(spec.supported_buckets) - set(SUPPORTED_AGGREGATE_BUCKETS)
    if unknown_buckets:
        raise ValueError(f"Unknown aggregate buckets: {sorted(unknown_buckets)}")
    unknown_scopes = set(spec.supported_scopes) - set(SUPPORTED_AGGREGATE_SCOPES)
    if unknown_scopes:
        raise ValueError(f"Unknown aggregate scopes: {sorted(unknown_scopes)}")
    if spec.rolling_window_days is not None and spec.rolling_window_days not in SUPPORTED_ROLLING_WINDOW_DAYS:
        raise ValueError(f"Unknown rolling window days: {spec.rolling_window_days}")
    return {
        "aggregate_mode": mode,
        "aggregate_source": source,
        "denominator": spec.denominator,
        "weight_column": spec.weight_column,
        "numerator_column": spec.numerator_column,
        "denominator_column": spec.denominator_column,
        "value_column": spec.value_column,
        "sample_size_column": spec.sample_size_column,
        "supported_buckets": list(spec.supported_buckets),
        "supported_scopes": list(spec.supported_scopes),
        "quantiles": list(spec.quantiles),
        "metric_version_policy": spec.metric_version_policy,
        "rolling_window_days": spec.rolling_window_days,
        "fixed_rolling_window": spec.fixed_rolling_window,
    }
