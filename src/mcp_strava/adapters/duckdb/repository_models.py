"""Typed row contracts for the DuckDB repository boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from mcp_strava.types import RepositoryActivityRow


class DirtyActivityRow(TypedDict):
    """A row of ``metric_dirty_activities`` joined with source state."""

    activity_id: int
    activity_day: object
    metric_version: int
    source_revision: int
    reason: str
    queued_at: object
    attempt_count: int
    last_error: str | None
    source_hash: str


class SourceStateRow(TypedDict):
    activity_id: int
    activity_day: object
    summary_hash: str
    detail_hash: str
    streams_hash: str
    channels_hash: str
    source_hash: str
    source_revision: int
    changed_at: object


class SourceRevisionRow(TypedDict):
    source_hash: str
    source_revision: int


class SourceComponents(TypedDict):
    """Computed provenance hashes for one activity."""

    activity_day: str
    summary_hash: str
    detail_hash: str
    streams_hash: str
    channels_hash: str
    source_hash: str


class ActivitySourcePayloadRow(TypedDict):
    activity_id: object
    activity_day: object
    payload_kind: object
    endpoint: object
    fetched_at: object
    payload_json: object
    raw_hash: object
    modeled_projection_hash: object
    schema_status: object
    drift_fingerprint: object
    migrated_from_legacy: object


class AthleteProfilePayloadRow(TypedDict):
    profile_key: object
    payload_kind: object
    endpoint: object
    fetched_at: object
    payload_json: object
    raw_hash: object
    schema_status: object
    drift_fingerprint: object


class LogicVersionRow(TypedDict):
    metric_version: int
    logic_fingerprint: str
    changed_at: object


@dataclass(frozen=True, slots=True, kw_only=True)
class ActivitySummaryRecord:
    activity_id: int
    date: str
    name: str
    sport_type: str
    distance: float
    moving_time: int
    elapsed_time: int
    total_elevation_gain: float
    summary_json: str
    synced_at: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ActivitySourcePayload:
    activity_id: int
    activity_day: str | None
    payload_kind: str
    endpoint: str
    fetched_at: str
    payload_json: str
    raw_hash: str
    modeled_projection_hash: str | None
    schema_status: str
    drift_fingerprint: str | None = None
    migrated_from_legacy: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class AthleteProfilePayload:
    profile_key: str
    payload_kind: str
    endpoint: str
    fetched_at: str
    payload_json: str
    raw_hash: str
    schema_status: str
    drift_fingerprint: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StreamChannelRecord:
    activity_id: int
    channel_key: str
    original_size: int | None
    resolution: str | None
    series_type: str | None
    fetched_at: str | None
    batch_id: str | None
    status: str
    error: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SyncLogRecord:
    timestamp: str
    status: str
    activities_seen: int | None
    activities_new: int | None
    streams_fetched: int | None
    details_fetched: int | None
    api_calls: int | None
    error: str | None
    kudos_fetched: int | None


@dataclass(frozen=True)
class ActivityMaterializationSource:
    activity: RepositoryActivityRow
    source_hash: str
    source_revision: int


@dataclass(frozen=True)
class ActivityStreamScalars:
    stream_count: int
    hr_count: int
    min_hr: int | None
    max_hr: int | None
    cardiac_cost: float | None
    median_hr: float | None


@dataclass(frozen=True)
class ActivityZoneTrimp:
    zone1_seconds: int
    zone2_seconds: int
    zone3_seconds: int
    zone4_seconds: int
    zone5_seconds: int
    trimp: float


class ActivityMetricFactRow(TypedDict):
    """Row returned by ``fetch_activity_metric_facts`` / ``fetch_activity_metric_fact``."""

    activity_id: object
    activity_day: object
    metric_version: object
    completeness_status: object
    missing_reasons_json: object
    source_revision: object
    computed_at: object
    trimp: object
    distance_m: object
    moving_time_s: object
    elapsed_time_s: object
    elevation_gain_m: object
    zone1_seconds: object
    zone2_seconds: object
    zone3_seconds: object
    zone4_seconds: object
    zone5_seconds: object
    hr_recovery_pause_count: object
    hr_recovery_total_rest_sec: object
    hr_recovery_median_rate: object
    hr_recovery_best_rate: object
    hr_recovery_worst_rate: object
    hr_recovery_avg_rate: object
    vertical_speed_vmh: object
    vertical_speed_total_ascent_m: object
    vertical_speed_duration_hours: object
    cardiac_cost: object
    adjusted_cardiac_cost: object
    cardiac_drift_pct: object
    cardiac_drift_significant: object
    cardiac_drift_severity: object
    cardiac_drift_quality: object
    hrr_pct: object
    anomaly_count: object
    start_time_local: object
    sport_type: object
    activity_name: object
    activity_date: object
    summary_json: object
    detail_json: object


class DailyLoadFactRow(TypedDict):
    """Row returned by ``fetch_daily_load_facts``."""

    day: object
    scope: object
    sport_type: object
    metric_version: object
    computed_at: object
    completeness_status: object
    missing_reasons_json: object
    activity_count: object
    stream_point_count: object
    heartrate_point_count: object
    observed_trimp: object
    effective_trimp: object
    distance_m: object
    moving_time_s: object
    elevation_gain_m: object
    zone4_seconds: object
    zone5_seconds: object
    high_zone_seconds: object
    anomaly_count: object


class TrainingModelDayRow(TypedDict):
    """Row returned by ``fetch_latest_training_model_day``."""

    day: object
    scope: object
    sport_type: object
    metric_version: object
    computed_at: object
    completeness_status: object
    missing_reasons_json: object
    effective_trimp: object
    observed_trimp: object
    fitness: object
    fatigue: object
    form: object
    form_zone: object
    acwr_zone: object
    acwr: object
    load_7d: object
    load_28d: object
    load_42d: object
    input_days: object
    missing_days: object


class RollingPeriodFactRow(TypedDict):
    """Row returned by rolling period fact read methods."""

    as_of_day: object
    window_days: object
    scope: object
    sport_type: object
    metric_version: object
    computed_at: object
    completeness_status: object
    missing_reasons_json: object
    activity_count: object
    active_days: object
    rest_days: object
    observed_trimp: object
    effective_trimp: object
    distance_m: object
    moving_time_s: object
    elevation_gain_m: object
    high_zone_seconds: object
    anomaly_count: object
    fitness: object
    fatigue: object
    form: object
    form_zone: object
    acwr_zone: object
    acwr: object
    median_cardiac_cost: object
    median_adjusted_cardiac_cost: object
    median_hr_recovery: object
    median_cardiac_drift_pct: object
