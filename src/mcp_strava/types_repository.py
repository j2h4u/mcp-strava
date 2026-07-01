from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ActivitySourceState:
    """Read-model provenance for one source activity."""

    activity_id: int
    activity_day: str
    source_hash: str
    source_revision: int
    changed_at: str
    summary_hash: str | None = None
    detail_hash: str | None = None
    streams_hash: str | None = None
    channels_hash: str | None = None


@dataclass
class MetricDirtyActivity:
    """Durable recompute queue row for one activity/day/metric version."""

    activity_id: int
    activity_day: str
    metric_version: int
    source_revision: int
    reason: str
    queued_at: str
    attempt_count: int = 0
    last_error: str | None = None


@dataclass
class ActivityMetricFact:
    """Materialized per-activity training metrics with provenance."""

    activity_id: int
    activity_day: str
    sport_type: str
    source_hash: str
    source_revision: int
    metric_version: int
    computed_at: str
    completeness_status: str
    missing_reasons_json: list[str] = field(default_factory=list)
    trimp: float | None = None
    zone1_seconds: int = 0
    zone2_seconds: int = 0
    zone3_seconds: int = 0
    zone4_seconds: int = 0
    zone5_seconds: int = 0
    hr_recovery_median_rate: float | None = None
    hr_recovery_best_rate: float | None = None
    hr_recovery_worst_rate: float | None = None
    hr_recovery_avg_rate: float | None = None
    vertical_speed_vmh: int | None = None
    vertical_speed_total_ascent_m: float | None = None
    vertical_speed_duration_hours: float | None = None
    cardiac_cost: float | None = None
    adjusted_cardiac_cost: float | None = None
    cardiac_drift_pct: float | None = None
    cardiac_drift_severity: str | None = None
    cardiac_drift_significant: bool = False
    cardiac_drift_quality: str | None = None
    hrr_pct: float | None = None
    hr_recovery_pause_count: int = 0
    hr_recovery_total_rest_sec: int = 0
    anomaly_count: int = 0
    distance_m: float | None = None
    moving_time_s: int | None = None
    elapsed_time_s: int | None = None
    elevation_gain_m: float | None = None
    heartrate_sample_count: int = 0
    stream_sample_count: int = 0


@dataclass
class DailyLoadFact:
    """Materialized daily load aggregate for a scope/sport."""

    day: str
    scope: str
    sport_type: str
    metric_version: int
    computed_at: str
    completeness_status: str
    missing_reasons_json: list[str] = field(default_factory=list)
    activity_count: int = 0
    stream_point_count: int = 0
    heartrate_point_count: int = 0
    observed_trimp: float | None = None
    effective_trimp: float = 0.0
    distance_m: float = 0.0
    moving_time_s: int = 0
    elevation_gain_m: float = 0.0
    zone4_seconds: int = 0
    zone5_seconds: int = 0
    high_zone_seconds: int = 0
    anomaly_count: int = 0


@dataclass
class TrainingModelDailyFact:
    """Materialized daily fitness/fatigue/form model state."""

    day: str
    scope: str
    sport_type: str
    metric_version: int
    computed_at: str
    completeness_status: str
    missing_reasons_json: list[str] = field(default_factory=list)
    effective_trimp: float = 0.0
    observed_trimp: float | None = None
    fitness: float | None = None
    fatigue: float | None = None
    form: float | None = None
    form_zone: str | None = None
    acwr_zone: str | None = None
    acwr: float | None = None
    load_7d: float | None = None
    load_28d: float | None = None
    load_42d: float | None = None
    input_days: int = 0
    missing_days: int = 0


@dataclass
class RollingPeriodFact:
    """Materialized fixed-window aggregate for MCP read paths."""

    as_of_day: str
    window_days: int
    scope: str
    sport_type: str
    metric_version: int
    computed_at: str
    completeness_status: str
    missing_reasons_json: list[str] = field(default_factory=list)
    activity_count: int = 0
    active_days: int = 0
    rest_days: int = 0
    observed_trimp: float | None = None
    effective_trimp: float = 0.0
    distance_m: float = 0.0
    moving_time_s: int = 0
    elevation_gain_m: float = 0.0
    high_zone_seconds: int = 0
    anomaly_count: int = 0
    fitness: float | None = None
    fatigue: float | None = None
    form: float | None = None
    form_zone: str | None = None
    acwr_zone: str | None = None
    acwr: float | None = None
    median_cardiac_cost: float | None = None
    median_adjusted_cardiac_cost: float | None = None
    median_hr_recovery: float | None = None
    median_cardiac_drift_pct: float | None = None


@dataclass
class ReadModelRefreshRun:
    """Audit/checkpoint row for a materialization run."""

    id: int | None
    started_at: str
    status: str
    metric_version: int
    finished_at: str | None = None
    trigger_reason: str | None = None
    lease_owner: str | None = None
    activities_considered: int = 0
    activities_materialized: int = 0
    daily_facts_materialized: int = 0
    model_facts_materialized: int = 0
    rolling_facts_materialized: int = 0
    dirty_rows_claimed: int = 0
    dirty_rows_cleared: int = 0
    checkpoint_cursor: str | None = None
    attempt_count: int = 0
    last_error: str | None = None


@dataclass
class RepositoryActivityRow:
    """Activity row exposed by repository methods."""

    id: int
    activity_day: str
    name: str
    sport_type: str
    distance: float
    moving_time: int
    elapsed_time: int
    total_elevation_gain: float
    summary_json: str | None
    detail_json: str | None
    synced_at: str | None


@dataclass
class RepositorySyncLogEntry:
    """Sync log entry returned by repository methods."""

    timestamp: str
    status: str
    activities_seen: int | None = None
    activities_new: int | None = None
    streams_fetched: int | None = None
    details_fetched: int | None = None
    api_calls: int | None = None
    error: str | None = None
    kudos_fetched: int | None = None


ALLOWED_REASON_CODES = frozenset(
    {
        "token_unavailable",
        "rate_limited",
        "network_unstable",
        "strava_application_inactive",
        "refresh_incomplete",
        "refresh_misconfigured",
        "sync_in_progress",
    }
)


@dataclass
class RefreshStateRow:
    """Singleton refresh state row used by refresh runtime and read paths."""

    id: int
    last_success_at: str | None = None
    last_attempt_at: str | None = None
    last_status: str | None = None
    last_error_code: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    backoff_until: str | None = None
    checkpoint_stage: str | None = None
    checkpoint_cursor: str | None = None


@dataclass
class RefreshRequestRow:
    """Pending or consumed local refresh signal."""

    id: int
    reason: str
    requested_for_day: str
    requested_at: str
    consumed_at: str | None = None


DailyLoadStatus = Literal["REST", "UNKNOWN", "PARTIAL", "OBSERVED"]


@dataclass
class DailyLoadPoint:
    """Repository daily load contract separating status vs numeric load input."""

    date: str
    status: DailyLoadStatus
    observed_trimp: float | None
    effective_trimp: float
    activity_count: int = 0
    stream_points: int = 0
    heartrate_points: int = 0
