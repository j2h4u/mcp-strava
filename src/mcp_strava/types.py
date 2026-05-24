"""Data contracts — all dataclass definitions for inter-module communication.

Every dict returned from metrics/training/analytics/report is typed here.
Strava API responses are also described as dataclasses for type safety.
Import this module instead of passing raw dicts.
+ dc_to_dict() — serialize dataclass tree to JSON-safe dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Literal


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
    sport_type: str              # "Run", "Walk", "Hike", "TrailRun", etc.
    start_date_local: str        # ISO 8601 local time
    distance: float              # metres
    moving_time: int             # seconds
    elapsed_time: int            # seconds
    total_elevation_gain: float  # metres

    # ─── Speed/Cadence [summary+detailed] ───
    average_speed: Optional[float] = None      # m/s
    max_speed: Optional[float] = None          # m/s
    average_cadence: Optional[float] = None    # steps/min (run) or rpm (ride)

    # ─── Heart Rate [summary+detailed] ───
    has_heartrate: bool = False
    average_heartrate: Optional[float] = None  # bpm
    max_heartrate: Optional[float] = None      # bpm

    # ─── Device/Source [summary+detailed] ───
    device_name: Optional[str] = None
    gear_id: Optional[str] = None
    workout_type: Optional[int] = None         # 0=race, 1=long, 2=workout, 3=easy, 11=hill

    # ─── Elevation [summary+detailed] ───
    elev_high: Optional[float] = None          # metres
    elev_low: Optional[float] = None           # metres

    # ─── Location [summary+detailed] ───
    start_latlng: Optional[list] = None        # [lat, lng]
    end_latlng: Optional[list] = None          # [lat, lng]
    timezone: Optional[str] = None
    utc_offset: Optional[float] = None

    # ─── DetailedActivity only [detailed] ───
    calories: Optional[float] = None           # kcal
    description: Optional[str] = None
    perceived_exertion: Optional[int] = None   # 1-10 RPE (💰 Summit)
    prefer_perceived_exertion: Optional[bool] = None  # 💰 Summit
    hide_from_home: bool = False
    # Nested collections (only from GET /activities/{id})
    splits_metric: Optional[list] = None       # [{distance, average_speed, average_grade_adjusted_speed, ...}]
    splits_standard: Optional[list] = None
    laps: Optional[list] = None                # [{elapsed_time, distance, average_speed, ...}]
    best_efforts: Optional[list] = None        # [{name, elapsed_time, distance, pr_rank}]
    segment_efforts: Optional[list] = None
    gear_detail: Optional[dict] = None         # {id, name, nickname, primary, retired, distance}
    similar_activities: Optional[dict] = None  # {effort_count, trend: {direction, speeds}}

    # ─── Raw payload preserved ───
    _raw: Optional[dict] = field(default=None, repr=False)


@dataclass
class StravaStreamChannel:
    """One channel from Strava streams response (e.g. time, heartrate)."""
    data: list = field(default_factory=list)
    original_size: Optional[int] = None
    resolution: Optional[str] = None
    series_type: Optional[str] = None


@dataclass
class StravaStreams:
    """Strava API response: GET /activities/{id}/streams.
    Keys: time, heartrate, velocity_smooth, altitude, cadence, latlng, grade_smooth.
    Run-only: grade_adjusted_speed (GAP), grade_adjusted_distance.
    """
    time: StravaStreamChannel = field(default_factory=StravaStreamChannel)
    heartrate: Optional[StravaStreamChannel] = None
    velocity_smooth: Optional[StravaStreamChannel] = None
    altitude: Optional[StravaStreamChannel] = None
    cadence: Optional[StravaStreamChannel] = None
    latlng: Optional[StravaStreamChannel] = None
    grade_smooth: Optional[StravaStreamChannel] = None
    moving: Optional[StravaStreamChannel] = None
    # Run ONLY — not available for Walk/Hike
    grade_adjusted_speed: Optional[StravaStreamChannel] = None     # GAP in m/s
    grade_adjusted_distance: Optional[StravaStreamChannel] = None  # cumulative GAP metres


@dataclass
class StreamChannelMetadata:
    """Repository contract for persisted stream-channel metadata."""

    activity_id: int
    channel_key: str
    original_size: Optional[int] = None
    resolution: Optional[str] = None
    series_type: Optional[str] = None
    fetched_at: Optional[str] = None
    batch_id: Optional[str] = None
    status: str = "available"
    error: Optional[str] = None


@dataclass
class StravaShoe:
    """One shoe from GET /athlete response."""
    id: int
    name: str
    distance: float             # metres
    primary: bool = False
    _raw: Optional[dict] = field(default=None, repr=False)


@dataclass
class StravaAthlete:
    """Strava API response: GET /athlete (partial — only what we use)."""
    id: int
    shoes: list[StravaShoe] = field(default_factory=list)
    _raw: Optional[dict] = field(default=None, repr=False)


# ─── Strava API → Dataclass Adapters ───


def parse_strava_activity(raw: dict) -> StravaActivity:
    """Parse a raw Strava activity dict into a typed dataclass.
    Works with both SummaryActivity (resource_state=2, from list endpoint)
    and DetailedActivity (resource_state=3, from GET /activities/{id}).
    Unknown fields are preserved in _raw.
    """
    return StravaActivity(
        # Core
        id=raw['id'],
        name=raw.get('name', ''),
        sport_type=raw.get('sport_type', 'Unknown'),
        start_date_local=raw.get('start_date_local', ''),
        distance=raw.get('distance', 0),
        moving_time=raw.get('moving_time', 0),
        elapsed_time=raw.get('elapsed_time', 0),
        total_elevation_gain=raw.get('total_elevation_gain', 0),
        # Speed/Cadence
        average_speed=raw.get('average_speed'),
        max_speed=raw.get('max_speed'),
        average_cadence=raw.get('average_cadence'),
        # Heart Rate
        has_heartrate=raw.get('has_heartrate', False),
        average_heartrate=raw.get('average_heartrate'),
        max_heartrate=raw.get('max_heartrate'),
        # Device/Source
        device_name=raw.get('device_name'),
        gear_id=raw.get('gear_id'),
        workout_type=raw.get('workout_type'),
        # Elevation
        elev_high=raw.get('elev_high'),
        elev_low=raw.get('elev_low'),
        # Location
        start_latlng=raw.get('start_latlng'),
        end_latlng=raw.get('end_latlng'),
        timezone=raw.get('timezone'),
        utc_offset=raw.get('utc_offset'),
        # DetailedActivity fields (None for summary)
        calories=raw.get('calories'),
        description=raw.get('description'),
        perceived_exertion=raw.get('perceived_exertion'),
        prefer_perceived_exertion=raw.get('prefer_perceived_exertion'),
        hide_from_home=raw.get('hide_from_home', False),
        splits_metric=raw.get('splits_metric'),
        splits_standard=raw.get('splits_standard'),
        laps=raw.get('laps'),
        best_efforts=raw.get('best_efforts'),
        segment_efforts=raw.get('segment_efforts'),
        gear_detail=raw.get('gear'),
        similar_activities=raw.get('similar_activities'),
        # Raw
        _raw=raw,
    )


def parse_strava_streams(raw: dict) -> StravaStreams:
    """Parse raw Strava streams response into typed dataclass.
    Each key in raw maps to a StravaStreamChannel with .data list.
    """
    def _ch(key: str) -> Optional[StravaStreamChannel]:
        if key not in raw:
            return None
        d = raw[key]
        return StravaStreamChannel(
            data=d.get('data', []),
            original_size=d.get('original_size'),
            resolution=d.get('resolution'),
            series_type=d.get('series_type'),
        )

    return StravaStreams(
        time=_ch('time') or StravaStreamChannel(),
        heartrate=_ch('heartrate'),
        velocity_smooth=_ch('velocity_smooth'),
        altitude=_ch('altitude'),
        cadence=_ch('cadence'),
        latlng=_ch('latlng'),
        grade_smooth=_ch('grade_smooth'),
        moving=_ch('moving'),
        grade_adjusted_speed=_ch('grade_adjusted_speed'),       # Run ONLY
        grade_adjusted_distance=_ch('grade_adjusted_distance'),  # Run ONLY
    )


def parse_strava_stream_channels(raw: dict[str, object]) -> dict[str, StravaStreamChannel]:
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
    for s in raw.get('shoes', []):
        shoes.append(StravaShoe(
            id=s['id'],
            name=s.get('name', ''),
            distance=s.get('distance', 0),
            primary=s.get('primary', False),
            _raw=s,
        ))
    return StravaAthlete(
        id=raw.get('id', 0),
        shoes=shoes,
        _raw=raw,
    )


# ─── Per-Activity Metrics ───


@dataclass
class HrRecovery:
    """HR recovery analysis from pauses during an activity.
    
    median_rate is the primary metric (bpm/min). May 2026: bpm_per_min
    duplicate removed (coach review #10).
    """
    pauses_found: int
    total_rest_sec: int
    median_rate: Optional[float]   # bpm/min — main metric
    best_rate: Optional[float]
    worst_rate: Optional[float]
    avg_rate: Optional[float]


@dataclass
class VerticalSpeed:
    """Vertical ascent speed."""
    vmh: int             # metres per hour of ascent
    total_ascent_m: float
    duration_hours: float


@dataclass
class DecouplingResult:
    """Heart-rate drift between first and second half of activity.
    
    decoupling_pct is None when:
    - Not enough data (<120 stream points)
    - Pace too variable (CV > PACE_CV_MAX) — decoupling requires steady effort
    """
    decoupling_pct: Optional[float]
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
    drift_pct: Optional[float]       # weighted drift % across clusters
    severity: Optional[str]          # 'stable' | 'borderline' | 'moderate' |
                                     # 'significant' | 'severe'
    quality: str = 'low'             # 'good' (≥10min data) | 'fair' (≥5min) | 'low'
    is_significant: bool = False     # True if drift ≥ threshold AND consistency ≥ 0.6
    n_clusters: int = 0              # number of pace clusters (Jenks k)
    gvf: float = 0.0                 # Goodness of Variance Fit
    cluster_count: int = 0           # clusters with valid early/late comparison
    error: Optional[str] = None      # reason when drift can't be computed


@dataclass
class EnrichedActivity:
    """Full enriched activity with computed metrics.
    
    May 2026 cleanup: decoupling_pct, decoupling_result, efficiency_factor removed —
    decoupling almost always N/A for this athlete, EF replaced by CC in progressive signal.
    """
    id: int
    date: str
    name: str
    sport_type: str
    distance_km: float
    moving_time_min: float
    elapsed_time_min: float
    elevation_m: Optional[float]
    trimp: float
    avg_hr: Optional[float]
    max_hr: Optional[int]
    zone_minutes: list[float] = field(default_factory=lambda: [0.0] * 5)
    hr_recovery: Optional[HrRecovery] = None
    vertical_speed: Optional[VerticalSpeed] = None
    cc: Optional[float] = None                          # Cardiac Cost = avg_hr / avg_vel
    cardiac_drift: Optional[CardiacDriftResult] = None  # intra-activity drift
    hrr_pct: Optional[float] = None                     # avg %HRR = (avg_hr − HRrest) / (HRmax − HRrest) × 100
    start_time: Optional[str] = None                    # "HH:MM" local (from start_date_local)


# ─── Training Model Results ───


@dataclass
class BanisterResult:
    """Fitness-Fatigue-Form from EWMA model."""
    fitness: float
    fatigue: float
    form: float
    form_zone: str       # tired / normal / fresh (simplified to 3, May 2026)


@dataclass
class ProgressiveSignal:
    """Whether load should grow, hold, or reduce."""
    load_bonus: float    # -0.20 .. +0.20
    signal: str          # 'grow' / 'hold' / 'reduce'
    ef_trend: Optional[str]
    cc_trend: Optional[str]              # combined CC trend (for backward compat)
    cc_trends: dict[str, Optional[str]] = field(default_factory=dict)  # per-sport: {'Run': '↓-5%', 'Hike': None}
    reasons: list[str] = field(default_factory=list)


@dataclass
class PlanDay:
    """One day in the weekly plan projection."""
    date: str
    weekday: str
    trimp: float
    activity: str        # 'rest' / 'easy_run' / 'tempo_run' / 'long_run' / 'walk' etc.
    form: float
    form_zone: str
    is_rest: bool = False
    is_target: bool = False


@dataclass
class SimDay:
    """One simulated day in a Banister forward projection (pure model output)."""
    date: str
    trimp: float
    fitness: float
    fatigue: float
    form: float
    weekday: str = ""


@dataclass
class WeeklyPlan:
    """Adaptive weekly plan targeting Saturday peak form."""
    target_day: str
    target_weekday: str
    days_to_target: int
    current_form: float
    current_form_zone: str
    completed_days: list['CompletedDay'] = field(default_factory=list)
    plan_days: list[PlanDay] = field(default_factory=list)
    saturday_form: float = 0.0
    on_track: bool = False
    post_weekend: list['PostWeekendSim'] = field(default_factory=list)
    sparkline: list['SparklineBar'] = field(default_factory=list)
    load_bonus: float = 0.0
    activity_templates: dict[str, float] = field(default_factory=dict)


@dataclass
class CompletedDay:
    """A day in the past (Mon-today) with known TRIMP."""
    date: str
    weekday: str
    trimp: float
    type: str       # 'rest' | 'walk' | 'run' | 'hard'
    is_past: bool = True


@dataclass
class PostWeekendSim:
    """Projected Monday form after weekend hiking scenarios."""
    hikes: int           # 0, 1, or 2
    monday_form: float
    note: str


@dataclass
class SparklineBar:
    """Single bar in centered-on-zero form sparkline."""
    form: float
    label: str = ''
    bar: str = ''     # ASCII bar: ▓▓┃··
    zone: str = ''    # short zone label: 🟢 🟡 etc.


@dataclass
class BySportBreakdown:
    """Aggregate metrics for a single sport type in the report window."""
    count: int = 0
    trimp: float = 0.0
    distance_km: float = 0.0
    time_min: float = 0.0
    elevation_m: float = 0.0


@dataclass
class AcwrPoint:
    """ACWR snapshot for a single day."""
    date: str
    acwr: float
    atl: float
    ctl: float


@dataclass
class BanisterPoint:
    """Banister form/fatigue snapshot for a single day."""
    date: str
    form: float
    fatigue: float


# ─── Analytics / Rolling Efficiency ───


@dataclass
class ActivityMetrics:
    """Per-activity efficiency computed from streams (CC, EF, VO2max)."""
    date: str
    sport: str
    cc: float            # cardiac cost = avg_hr / avg_vel
    cc_adj: float        # elevation-adjusted cardiac cost
    bkm: Optional[float] # beats per km
    ef: Optional[float]  # efficiency factor
    vo2max_est: Optional[float]
    dist_km: float
    time_min: float
    elev: float
    epkm: float          # elevation gain per km


@dataclass
class RollingEfficiency:
    """Median efficiency over a rolling window for one sport.
    
    CC-only output (May 2026 cleanup): EF, bkm, VO2max removed.
    CC and CC_adj remain as sole cardiac efficiency metrics.
    """
    count: int
    active_days: int
    total_km: float
    total_time_h: float
    total_elev_m: float
    median_epkm: Optional[float]
    median_cc: float
    median_cc_adj: float


@dataclass
class WeeklyDigest:
    """Full weekly analytics digest."""
    period: dict         # today, weekday, data_days, first_activity
    current_state: dict   # load, efficiency per sport, volume per sport
    trends: dict          # pct changes
    yoy: dict             # year-over-year comparisons
    context: dict         # season, streaks, last hike
    this_week: list[dict] # activities this week


# ─── Repository Contracts ───


@dataclass
class RepositoryActivityRow:
    """SQLite activity row exposed by repository methods."""

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
class RepositoryPreflightResult:
    """Repository-level preflight summary shape."""

    user_version: int
    row_counts: dict[str, int] = field(default_factory=dict)
    integrity_result: str = "unknown"


@dataclass
class RepositoryMigrationResult:
    """Repository-level migration status shape."""

    applied: bool
    from_version: int
    to_version: int
    backup_path: str | None = None


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
    description: str = ""


@dataclass(frozen=True)
class ExcludedInterpretation:
    field: str
    reason: str
    preserved_metric_ids: list[str]


# ─── Report ───


@dataclass
class Recommendation:
    """Training recommendation for today."""
    action: str          # 'rest' / 'easy' / 'train'
    intensity: str       # 'low' / 'normal' / 'high'
    reasons: list[str] = field(default_factory=list)
    confidence: str = 'high'


@dataclass
class DailyReport:
    """Full daily training report."""
    today: str
    yesterday: str
    window_days: int
    window_start: str

    yesterday_activities: list[EnrichedActivity] = field(default_factory=list)
    yesterday_trimp: float = 0.0

    activities_14d: list[EnrichedActivity] = field(default_factory=list)
    daily_trimp_14d: dict[str, float] = field(default_factory=dict)
    total_trimp_14d: float = 0.0
    avg_trimp_per_day: float = 0.0
    active_days: int = 0
    rest_days: int = 0
    by_sport: dict[str, BySportBreakdown] = field(default_factory=dict)

    trend_decoupling: Optional[str] = None
    trend_ef: Optional[str] = None
    trend_hr_recovery: Optional[str] = None
    trend_vertical_speed: Optional[str] = None
    median_decoupling: Optional[float] = None
    median_ef: Optional[float] = None
    median_hr_recovery: Optional[float] = None

    banister: Optional[BanisterResult] = None
    banister_history: list[BanisterPoint] = field(default_factory=list)
    weekly_trimp: float = 0.0

    acwr: Optional[float] = None
    acwr_zone: str = 'unknown'
    acwr_atl: float = 0.0
    acwr_ctl: float = 0.0
    acwr_history: list[AcwrPoint] = field(default_factory=list)

    recommendation: Optional[Recommendation] = None
    progressive_signal: Optional[ProgressiveSignal] = None
    weekly_plan: Optional[WeeklyPlan] = None
    safety_warnings: list[str] = field(default_factory=list)  # Z5 alerts, etc.


# ─── Helpers ───

def dc_to_dict(obj):
    """Recursively convert dataclass (or list/dict of dataclasses) to plain dict.
    Safe for json.dumps()."""
    if hasattr(obj, '__dataclass_fields__'):
        return {k: dc_to_dict(v) for k, v in obj.__dict__.items()
                if k != '_raw'}
    if isinstance(obj, list):
        return [dc_to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: dc_to_dict(v) for k, v in obj.items()}
    return obj
