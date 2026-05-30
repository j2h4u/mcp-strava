"""Data contracts shared across Strava mirror, metrics, refresh, and services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ─── Strava API Response Contracts ───


@dataclass
class StravaActivity:
    """Strava API response — covers both SummaryActivity (resource_state=2)
    from GET /athlete/activities and DetailedActivity (resource_state=3)
    from GET /activities/{id}.

    Fields marked [summary] are in both responses.
    Fields marked [detailed] only appear in GET /activities/{id}.
    """

    # ─── Core (always present) [summary+detailed] ───
    id: int
    name: str
    sport_type: str  # "Run", "Walk", "Hike", "TrailRun", etc.
    start_date_local: str  # ISO 8601 local time
    distance: float  # metres
    moving_time: int  # seconds
    elapsed_time: int  # seconds
    total_elevation_gain: float  # metres

    # ─── Speed/Cadence [summary+detailed] ───
    average_speed: float | None = None  # m/s
    max_speed: float | None = None  # m/s
    average_cadence: float | None = None  # steps/min (run) or rpm (ride)

    # ─── Heart Rate [summary+detailed] ───
    has_heartrate: bool = False
    average_heartrate: float | None = None  # bpm
    max_heartrate: float | None = None  # bpm

    # ─── Device/Source [summary+detailed] ───
    device_name: str | None = None
    gear_id: str | None = None
    workout_type: int | None = None  # 0=race, 1=long, 2=workout, 3=easy, 11=hill

    # ─── Elevation [summary+detailed] ───
    elev_high: float | None = None  # metres
    elev_low: float | None = None  # metres

    # ─── Location [summary+detailed] ───
    start_latlng: list | None = None  # [lat, lng]
    end_latlng: list | None = None  # [lat, lng]
    timezone: str | None = None
    utc_offset: float | None = None

    # ─── DetailedActivity only [detailed] ───
    calories: float | None = None  # kcal
    description: str | None = None
    perceived_exertion: int | None = None  # 1-10 RPE (💰 Summit)
    prefer_perceived_exertion: bool | None = None  # 💰 Summit
    hide_from_home: bool = False
    # Nested collections (only from GET /activities/{id})
    splits_metric: list | None = None  # [{distance, average_speed, average_grade_adjusted_speed, ...}]
    splits_standard: list | None = None
    laps: list | None = None  # [{elapsed_time, distance, average_speed, ...}]
    best_efforts: list | None = None  # [{name, elapsed_time, distance, pr_rank}]
    segment_efforts: list | None = None
    gear_detail: dict | None = None  # {id, name, nickname, primary, retired, distance}
    similar_activities: dict | None = None  # {effort_count, trend: {direction, speeds}}

    # ─── Raw payload preserved ───
    _raw: dict | None = field(default=None, repr=False)


@dataclass
class StravaStreamChannel:
    """One channel from Strava streams response (e.g. time, heartrate)."""

    data: list = field(default_factory=list)
    original_size: int | None = None
    resolution: str | None = None
    series_type: str | None = None


@dataclass
class StravaStreams:
    """Strava API response: GET /activities/{id}/streams.
    Keys: time, heartrate, velocity_smooth, altitude, cadence, latlng, grade_smooth.
    Run-only: grade_adjusted_speed (GAP), grade_adjusted_distance.
    """

    time: StravaStreamChannel = field(default_factory=StravaStreamChannel)
    heartrate: StravaStreamChannel | None = None
    velocity_smooth: StravaStreamChannel | None = None
    altitude: StravaStreamChannel | None = None
    cadence: StravaStreamChannel | None = None
    latlng: StravaStreamChannel | None = None
    grade_smooth: StravaStreamChannel | None = None
    moving: StravaStreamChannel | None = None
    # Run ONLY — not available for Walk/Hike
    grade_adjusted_speed: StravaStreamChannel | None = None  # GAP in m/s
    grade_adjusted_distance: StravaStreamChannel | None = None  # cumulative GAP metres


@dataclass
class StreamChannelMetadata:
    """Repository contract for persisted stream-channel metadata."""

    activity_id: int
    channel_key: str
    original_size: int | None = None
    resolution: str | None = None
    series_type: str | None = None
    fetched_at: str | None = None
    batch_id: str | None = None
    status: str = "available"
    error: str | None = None


@dataclass
class StravaShoe:
    """One shoe from GET /athlete response."""

    id: int
    name: str
    distance: float  # metres
    primary: bool = False
    _raw: dict | None = field(default=None, repr=False)


@dataclass
class StravaAthlete:
    """Strava API response: GET /athlete (partial — only what we use)."""

    id: int
    shoes: list[StravaShoe] = field(default_factory=list)
    _raw: dict | None = field(default=None, repr=False)


# ─── Strava API → Dataclass Adapters ───


def parse_strava_activity(raw: dict) -> StravaActivity:
    """Parse a raw Strava activity dict into a typed dataclass.
    Works with both SummaryActivity (resource_state=2, from list endpoint)
    and DetailedActivity (resource_state=3, from GET /activities/{id}).
    Unknown fields are preserved in _raw.
    """
    return StravaActivity(
        # Core
        id=raw["id"],
        name=raw.get("name", ""),
        sport_type=raw.get("sport_type", "Unknown"),
        start_date_local=raw.get("start_date_local", ""),
        distance=raw.get("distance", 0),
        moving_time=raw.get("moving_time", 0),
        elapsed_time=raw.get("elapsed_time", 0),
        total_elevation_gain=raw.get("total_elevation_gain", 0),
        # Speed/Cadence
        average_speed=raw.get("average_speed"),
        max_speed=raw.get("max_speed"),
        average_cadence=raw.get("average_cadence"),
        # Heart Rate
        has_heartrate=raw.get("has_heartrate", False),
        average_heartrate=raw.get("average_heartrate"),
        max_heartrate=raw.get("max_heartrate"),
        # Device/Source
        device_name=raw.get("device_name"),
        gear_id=raw.get("gear_id"),
        workout_type=raw.get("workout_type"),
        # Elevation
        elev_high=raw.get("elev_high"),
        elev_low=raw.get("elev_low"),
        # Location
        start_latlng=raw.get("start_latlng"),
        end_latlng=raw.get("end_latlng"),
        timezone=raw.get("timezone"),
        utc_offset=raw.get("utc_offset"),
        # DetailedActivity fields (None for summary)
        calories=raw.get("calories"),
        description=raw.get("description"),
        perceived_exertion=raw.get("perceived_exertion"),
        prefer_perceived_exertion=raw.get("prefer_perceived_exertion"),
        hide_from_home=raw.get("hide_from_home", False),
        splits_metric=raw.get("splits_metric"),
        splits_standard=raw.get("splits_standard"),
        laps=raw.get("laps"),
        best_efforts=raw.get("best_efforts"),
        segment_efforts=raw.get("segment_efforts"),
        gear_detail=raw.get("gear"),
        similar_activities=raw.get("similar_activities"),
        # Raw
        _raw=raw,
    )


def parse_strava_streams(raw: dict) -> StravaStreams:
    """Parse raw Strava streams response into typed dataclass.
    Each key in raw maps to a StravaStreamChannel with .data list.
    """

    def _ch(key: str) -> StravaStreamChannel | None:
        if key not in raw:
            return None
        d = raw[key]
        return StravaStreamChannel(
            data=d.get("data", []),
            original_size=d.get("original_size"),
            resolution=d.get("resolution"),
            series_type=d.get("series_type"),
        )

    return StravaStreams(
        time=_ch("time") or StravaStreamChannel(),
        heartrate=_ch("heartrate"),
        velocity_smooth=_ch("velocity_smooth"),
        altitude=_ch("altitude"),
        cadence=_ch("cadence"),
        latlng=_ch("latlng"),
        grade_smooth=_ch("grade_smooth"),
        moving=_ch("moving"),
        grade_adjusted_speed=_ch("grade_adjusted_speed"),  # Run ONLY
        grade_adjusted_distance=_ch("grade_adjusted_distance"),  # Run ONLY
    )


def parse_strava_stream_channels(raw: dict[str, Any]) -> dict[str, StravaStreamChannel]:
    """Parse raw keyed stream response and preserve every returned channel."""
    channels: dict[str, StravaStreamChannel] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        data = value.get("data")
        if not isinstance(data, list):
            continue
        channels[key] = StravaStreamChannel(
            data=data,
            original_size=value.get("original_size"),
            resolution=value.get("resolution"),
            series_type=value.get("series_type"),
        )
    return channels


def parse_strava_athlete(raw: dict) -> StravaAthlete:
    """Parse raw Strava athlete response into typed dataclass."""
    shoes = []
    for s in raw.get("shoes", []):
        shoes.append(
            StravaShoe(
                id=s["id"],
                name=s.get("name", ""),
                distance=s.get("distance", 0),
                primary=s.get("primary", False),
                _raw=s,
            )
        )
    return StravaAthlete(
        id=raw.get("id", 0),
        shoes=shoes,
        _raw=raw,
    )


# ─── Per-Activity Metrics ───


@dataclass
class HrRecovery:
    """HR recovery analysis from pauses during an activity.

    median_rate is the primary metric (bpm/min).
    """

    pauses_found: int
    total_rest_sec: int
    median_rate: float | None  # bpm/min — main metric
    best_rate: float | None
    worst_rate: float | None
    avg_rate: float | None


@dataclass
class VerticalSpeed:
    """Vertical ascent speed."""

    vmh: int  # metres per hour of ascent
    total_ascent_m: float
    duration_hours: float


@dataclass
class DecouplingResult:
    """Heart-rate drift between first and second half of activity.

    decoupling_pct is None when:
    - Not enough data (<120 stream points)
    - Pace too variable (CV > PACE_CV_MAX) — decoupling requires steady effort
    """

    decoupling_pct: float | None
    pace_too_variable: bool = False


@dataclass
class CardiacDriftResult:
    """Intra-activity cardiac drift via Jenks pace clustering.

    Compares median HR in early vs late temporal segments within each
    auto-detected pace cluster (Jenks natural breaks).

    drift_pct is None when:
    - <120 stream points
    - No clusters with ≥2 temporal segments
    - No HR/velocity data available
    """

    drift_pct: float | None  # weighted drift % across clusters
    severity: str | None  # 'stable' | 'borderline' | 'moderate' |
    # 'significant' | 'severe'
    quality: str = "low"  # 'good' (≥10min data) | 'fair' (≥5min) | 'low'
    is_significant: bool = False  # True if drift ≥ threshold AND consistency ≥ 0.6
    n_clusters: int = 0  # number of pace clusters (Jenks k)
    gvf: float = 0.0  # Goodness of Variance Fit
    cluster_count: int = 0  # clusters with valid early/late comparison
    error: str | None = None  # reason when drift can't be computed


@dataclass
class EnrichedActivity:
    """Full enriched activity with computed metrics."""

    id: int
    date: str
    name: str
    sport_type: str
    distance_km: float
    moving_time_min: float
    elapsed_time_min: float
    elevation_m: float | None
    trimp: float
    avg_hr: float | None
    max_hr: int | None
    zone_minutes: list[float] = field(default_factory=lambda: [0.0] * 5)
    hr_recovery: HrRecovery | None = None
    vertical_speed: VerticalSpeed | None = None
    cc: float | None = None  # Cardiac Cost = avg_hr / avg_vel
    cardiac_drift: CardiacDriftResult | None = None  # intra-activity drift
    hrr_pct: float | None = None  # avg %HRR = (avg_hr − HRrest) / (HRmax − HRrest) × 100
    start_time: str | None = None  # "HH:MM" local (from start_date_local)


# ─── Training Model Results ───


@dataclass
class BanisterResult:
    """Fitness-Fatigue-Form from EWMA model."""

    fitness: float
    fatigue: float
    form: float
    form_zone: str  # tired / normal / fresh


@dataclass
class SimDay:
    """One simulated day in a Banister forward projection (pure model output)."""

    date: str
    trimp: float
    fitness: float
    fatigue: float
    form: float
    weekday: str = ""


# ─── Repository Contracts ───


@dataclass(frozen=True)
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


@dataclass(frozen=True)
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


@dataclass(frozen=True)
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
    missing_reasons_json: str = "[]"
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
    cardiac_drift_significant: int = 0
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


@dataclass(frozen=True)
class DailyLoadFact:
    """Materialized daily load aggregate for a scope/sport."""

    day: str
    scope: str
    sport_type: str
    metric_version: int
    computed_at: str
    completeness_status: str
    missing_reasons_json: str = "[]"
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


@dataclass(frozen=True)
class TrainingModelDailyFact:
    """Materialized daily fitness/fatigue/form model state."""

    day: str
    scope: str
    sport_type: str
    metric_version: int
    computed_at: str
    completeness_status: str
    missing_reasons_json: str = "[]"
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


@dataclass(frozen=True)
class RollingPeriodFact:
    """Materialized fixed-window aggregate for MCP read paths."""

    as_of_day: str
    window_days: int
    scope: str
    sport_type: str
    metric_version: int
    computed_at: str
    completeness_status: str
    missing_reasons_json: str = "[]"
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


@dataclass(frozen=True)
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
    date: str
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
        "refresh_incomplete",
        "refresh_misconfigured",
        "sync_in_progress",
    }
)


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class RefreshRequestRow:
    """Pending or consumed local refresh signal."""

    id: int
    reason: str
    requested_for_day: str
    requested_at: str
    consumed_at: str | None = None


@dataclass
class RepositoryDailyLoadStatus:
    """Daily load status split between observed/effective values."""

    day: str
    status: str  # REST | UNKNOWN | PARTIAL | OBSERVED
    observed_trimp: float
    effective_trimp: float
    activity_count: int = 0
    stream_points: int = 0
    heartrate_points: int = 0


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


# ─── Application Service Contracts ───


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


@dataclass(frozen=True)
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

    data: Any
    freshness: FreshnessMetadata
    completeness: CompletenessMetadata
    warnings: list[ServiceWarning] = field(default_factory=list)
    rationale: list[ServiceRationale] = field(default_factory=list)


# ─── Metric Registry Contracts ───


@dataclass(frozen=True)
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


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class ExcludedInterpretation:
    field: str
    reason: str
    preserved_metric_ids: list[str]


# ─── Helpers ───


def smart_round(value: float) -> int | float:
    """Round numeric facts for presentation without hiding small signals."""
    if value == 0:
        return 0
    magnitude = abs(value)
    if magnitude >= 10:
        return round(value)
    if magnitude >= 1:
        return round(value, 1)
    if magnitude >= 0.1:
        return round(value, 2)
    if magnitude >= 0.01:
        return round(value, 3)
    return round(value, 4)


def dc_to_dict(obj: Any, *, round_floats: bool = False) -> Any:
    """Recursively convert dataclass (or list/dict of dataclasses) to plain dict.
    Safe for json.dumps()."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: dc_to_dict(v, round_floats=round_floats) for k, v in obj.__dict__.items() if k != "_raw"}
    if isinstance(obj, list):
        return [dc_to_dict(v, round_floats=round_floats) for v in obj]
    if isinstance(obj, dict):
        return {k: dc_to_dict(v, round_floats=round_floats) for k, v in obj.items()}
    if round_floats and isinstance(obj, float):
        return smart_round(obj)
    return obj
