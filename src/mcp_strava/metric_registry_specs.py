"""Spec dataclasses for aggregate, metric, and status-fact factories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp_strava.metric_registry_shared import SUPPORTED_AGGREGATE_BUCKETS


@dataclass(frozen=True, slots=True, kw_only=True)
class AggSpec:
    denominator: str | None = None
    weight_column: str | None = None
    numerator_column: str | None = None
    denominator_column: str | None = None
    value_column: str | None = None
    sample_size_column: str = "activity_count"
    supported_buckets: tuple[str, ...] = SUPPORTED_AGGREGATE_BUCKETS
    supported_scopes: tuple[str, ...] = ("both",)
    quantiles: tuple[str, ...] = ()
    metric_version_policy: str = "mixed_degraded"
    rolling_window_days: int | None = None
    fixed_rolling_window: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class MetricSpec:
    label: str
    unit: str
    source: str
    scope: str
    sport_scope: str
    comparison_mode: str
    directionality: str


@dataclass(frozen=True, slots=True, kw_only=True)
class StatusFactSpec:
    threshold: dict[str, Any] = field(default_factory=dict)
    window: dict[str, Any] = field(default_factory=dict)
    evidence_keys: list[str] = field(default_factory=list)
    completeness_reasons: list[str] = field(default_factory=list)
    calculation: str = ""
    materialized_from: str = ""
