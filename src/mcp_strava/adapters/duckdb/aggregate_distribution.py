"""Distribution aggregate row grouping helpers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _DistributionGroup:
    """Typed accumulator for one (bucket_start, sport_type) distribution group.

    Replaces an ad-hoc ``dict[str, Any]`` accumulator: the per-group running
    counts/lists are now precisely typed (so ``+=``/``.extend`` are checked), and
    ``as_row()`` projects back to the ``dict[str, object]`` row contract that
    ``aggregate_row_from_group`` consumes — keeping the public grouping shape
    unchanged while removing the ``Any``."""

    bucket_start: object
    output_sport_type: str | None
    distribution: dict[str, int] = field(default_factory=dict)
    activity_count: int = 0
    sample_size: int = 0
    null_count: int = 0
    excluded_count: int = 0
    metric_version_count: int = 0
    materialized_at: str | None = None
    completeness_statuses: list[object] = field(default_factory=list)
    missing_reason_payloads: list[object] = field(default_factory=list)

    def as_row(self) -> dict[str, object]:
        return {
            "bucket_start": self.bucket_start,
            "output_sport_type": self.output_sport_type,
            "distribution": self.distribution,
            "activity_count": self.activity_count,
            "sample_size": self.sample_size,
            "null_count": self.null_count,
            "excluded_count": self.excluded_count,
            "metric_version_count": self.metric_version_count,
            "materialized_at": self.materialized_at,
            "completeness_statuses": self.completeness_statuses,
            "missing_reason_payloads": self.missing_reason_payloads,
        }
