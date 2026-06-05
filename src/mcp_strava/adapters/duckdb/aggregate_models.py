"""Typed contracts for DuckDB aggregate query results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AggregateRequest:
    metric_ids: tuple[str, ...]
    bucket: str
    start_day: str | None
    end_day_exclusive: str
    bundle_id: str | None = None
    scope: str = "global"
    sport_filter: str | None = None
    include_empty_buckets: bool = False
    as_of_day: str | None = None
    window_days: int | None = None


@dataclass(frozen=True)
class AggregateQuery:
    statement: str
    params: tuple[object, ...]
    metric_id: str
    bucket: str


@dataclass
class AggregateRow:
    bucket_start: str
    bucket_end: str
    bucket_width: str
    metric_id: str
    unit: str
    calculation: str
    aggregation_mode: str
    denominator: str | None
    value: float | int | str | None
    quantiles: dict[str, float] | None
    distribution: dict[str, float | int] | None
    sample_size: int
    activity_count: int
    null_count: int
    excluded_count: int
    completeness_status: str
    missing_reasons: list[str] = field(default_factory=list)
    metric_version_status: str = "unavailable"
    materialized_at: str | None = None
    mirror_freshness: dict[str, Any] | None = None
    read_model_freshness: dict[str, Any] | None = None
    scope: str = "global"
    sport_type: str | None = None
