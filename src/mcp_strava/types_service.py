from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServiceWarning:
    """Factual product-service warning."""

    code: str
    severity: str
    message: str
    field: str | None = None
    evidence: dict[str, Any] | None = None


@dataclass
class ServiceRationale:
    """Short factual explanation for a computed service result."""

    code: str
    message: str


@dataclass
class FreshnessMetadata:
    """Local mirror freshness facts exposed to product consumers."""

    freshness_state: str
    checked_at: str
    last_successful_refresh_at: str | None
    refresh_age_seconds: int | None
    last_activity_at: str | None
    last_activity_age_seconds: int | None
    refresh_requested: bool = False
    refresh_request_reason: str | None = None
    last_error_code: str | None = None
    backoff_until: str | None = None


@dataclass
class CompletenessMetadata:
    """Factual completeness state for a service payload."""

    status: str
    missing: list[str] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReadModelMetadata:
    """Materialized read-model freshness and provenance state."""

    status: str
    last_materialized_at: str | None
    dirty_count: int
    oldest_dirty_day: str | None
    metric_versions_present: list[int] = field(default_factory=list)
    stale_reason: str | None = None


@dataclass
class ServiceEnvelope:
    """Shared product service response envelope."""

    data: object
    freshness: FreshnessMetadata
    completeness: CompletenessMetadata
    warnings: list[ServiceWarning] = field(default_factory=list)
    rationale: list[ServiceRationale] = field(default_factory=list)
