from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricDefinition:
    metric_id: str
    label: str
    unit: str
    source: str
    scope: str
    sport_scope: str
    comparison_mode: str
    directionality: str
    requirements: list[str]
    missing_reasons: list[str]
    exposed_in: list[str]
    calculation: str
    description: str = ""
    aggregate_mode: str | None = None
    aggregate_source: str | None = None
    denominator: str | None = None
    weight_column: str | None = None
    numerator_column: str | None = None
    denominator_column: str | None = None
    value_column: str | None = None
    sample_size_column: str | None = None
    supported_buckets: list[str] = field(default_factory=list)
    supported_scopes: list[str] = field(default_factory=list)
    bundle_ids: list[str] = field(default_factory=list)
    quantiles: list[str] = field(default_factory=list)
    metric_version_policy: str | None = None
    rolling_window_days: int | None = None
    fixed_rolling_window: bool = False


@dataclass
class StatusFactDefinition:
    code: str
    metric_id: str
    threshold: dict[str, Any]
    window: dict[str, Any]
    evidence_keys: list[str]
    completeness_reasons: list[str]
    calculation: str
    materialized_from: str


@dataclass
class StatusFact:
    code: str
    metric_id: str
    status: str
    threshold: dict[str, Any]
    window: dict[str, Any]
    evidence: dict[str, Any]
    completeness: dict[str, Any]
    calculation: str
    materialized_from: str


@dataclass
class ExcludedInterpretation:
    field: str
    reason: str
    preserved_metric_ids: list[str]
