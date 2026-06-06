from __future__ import annotations

from dataclasses import dataclass, field


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

    data: list[object] = field(default_factory=list)
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
    shoes = [
        StravaShoe(
            id=s["id"],
            name=s.get("name", ""),
            distance=s.get("distance", 0),
            primary=s.get("primary", False),
            _raw=s,
        )
        for s in raw.get("shoes", [])
    ]
    return StravaAthlete(
        id=raw.get("id", 0),
        shoes=shoes,
        _raw=raw,
    )
