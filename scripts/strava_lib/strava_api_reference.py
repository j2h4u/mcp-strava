"""
Strava API Reference — complete map of what's available.

This file documents EVERY field, endpoint, and data model the Strava API offers.
Fields we currently USE are marked with ✅.
Fields that require Summit (paid) are marked with 💰.
Fields we COULD use are marked with 🔵.
Fields we DON'T need are marked with ⬜.

Machine-readable version: strava_lib/api_schema.py (FieldSchema/EndpointSchema dataclasses).
Used by cmd_sync Phase 4 for automatic schema validation + Summit detection.

Last updated: 2026-05-05, verified against live API.
"""

# ══════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════

# ─── Activities ───

# GET /athlete/activities?before=&after=&page=&per_page=
#   Returns: list of SummaryActivity (resource_state=2)
#   Scope: activity:read (or activity:read_all for "Only Me")
#   ✅ WE USE: sync Phase 1, fetches pages of 100

# GET /activities/{id}?include_all_efforts=true
#   Returns: DetailedActivity (resource_state=3)
#   Scope: activity:read
#   🔵 COULD USE: splits_metric (GAP!), laps, best_efforts, segment_efforts, calories, similar_activities.trend
#   NOTE: Currently we DON'T fetch this — we only have SummaryActivity from list endpoint.
#         To get GAP/laps/splits we'd need to fetch each activity individually.

# GET /activities/{id}/zones
#   Returns: list of ActivityZone (heartrate zones, pace zones)
#   💰 Summit REQUIRED (returns 402 without)
#   NOTE: We compute our own zones from streams, so not critical.

# GET /activities/{id}/laps
#   Returns: list of Lap objects
#   Scope: activity:read

# GET /activities/{id}/comments
# GET /activities/{id}/kudos

# ─── Athlete ───

# GET /athlete
#   Returns: DetailedAthlete
#   ✅ WE USE: cmd_gear (extracts shoes list)

# GET /athlete/zones
#   Returns: heart rate zones, power zones
#   ✅ WE USE: get_zones() → stored in DB, used for TRIMP

# GET /athletes/{id}/stats
#   Returns: recent_run_totals, ytd_run_totals, all_run_totals, etc.
#   ✅ WE USE: cmd_stats

# PUT /athlete  (body: {weight: kg})
#   ⬜ Not used

# ─── Streams ───

# GET /activities/{id}/streams?keys=...&key_by_type=true
#   Available keys:
#     ✅ time          — seconds from start
#     ✅ heartrate     — bpm
#     ✅ velocity_smooth — m/s (smoothed)
#     ✅ altitude      — metres
#     ✅ cadence       — steps/min or rpm
#     ✅ latlng        — [lat, lng] pairs
#     ✅ grade_smooth  — percent grade (smoothed)
#     ✅ distance      — cumulative metres
#     ✅ moving        — boolean per point (is the athlete moving?)
#     🔵 grade_adjusted_speed   — m/s GAP (Run ONLY! Not Walk/Hike)
#     🔵 grade_adjusted_distance — cumulative GAP metres (Run ONLY!)
#     ❌ temp          — NOT available from Samsung Health
#     ❌ watts         — power (cycling only)
#     ❌ velocity      — raw (not smoothed), not always available
#   Resolution: "high" = every second, "medium" = ~every 4s, "low" = ~every 10s
#   series_type: usually "distance" (indexed by distance, not time)
#
#   ⚠️ GAP (grade_adjusted_speed) is only returned for Run sport_type.
#   Walk and Hike do NOT get it from Strava. But we have grade_smooth
#   for all types, so we can compute Minetti GAP ourselves.
#   ⚠️ Strava GAP ≠ Minetti GAP: on 5% grade, Strava is ~15-18% higher.
#   On flat (<2% grade), they match within ~1%. Strava uses a proprietary
#   formula (likely optimized for race-day pace prediction), Minetti is
#   from lab metabolic data.

# ─── Gear ───

# GET /gear/{id}
#   Returns: gear object (id, name, distance, primary, retired, nickname, converted_distance)
#   🔵 COULD USE: track shoe retirement status

# ─── Routes ───

# GET /athletes/{id}/routes
# GET /routes/{id}
# GET /routes/{id}/export_gpx
# GET /routes/{id}/export_tcx
#   ⬜ Not used — could be useful for planning routes

# ─── Segments ───

# GET /segments/explore?bounds=&activity_type=
# GET /segments/{id}
# GET /segment_efforts?segment_id=&start_date_local=&end_date_local=  (subscription required)
#   ⬜ Not used — segment tracking could be interesting for tracking local hill times


# ══════════════════════════════════════════════
# DATA MODELS
# ══════════════════════════════════════════════

# ─── SummaryActivity (resource_state=2) ───
# From GET /athlete/activities (list endpoint) — THIS IS WHAT WE SYNC

SUMMARY_ACTIVITY_FIELDS = """
    id                          int     ✅ primary key
    name                        str     ✅ stored
    sport_type                  str     ✅ "Run", "Walk", "Hike", etc.
    start_date                  str     ✅ UTC ISO 8601
    start_date_local            str     ✅ local ISO 8601 — stored as `date`
    distance                    float   ✅ metres
    moving_time                 int     ✅ seconds
    elapsed_time                int     ✅ seconds
    total_elevation_gain        float   ✅ metres
    type                        str     ⬜ deprecated alias for sport_type
    workout_type                int?    ⬜ 0=race, 1=long, 2=workout, 3=low, 11=hill, 12=progression
    resource_state              int     ⬜ always 2 for summary
    athlete                     dict    ⬜ {id, resource_state}
    map                         dict    ⬜ {id, polyline, summary_polyline}
    device_name                 str?    ⬜ "Samsung Health"
    external_id                 str?    ⬜ source file id
    upload_id                   int?    ⬜
    start_latlng                list?   ⬜ [lat, lng]
    end_latlng                  list?   ⬜ [lat, lng]
    average_speed               float?  🔵 m/s — useful for pace calc
    max_speed                   float?  🔵 m/s — sprint speed
    average_cadence             float?  🔵 steps/min
    has_heartrate               bool    ✅
    average_heartrate           float?  ✅ bpm
    max_heartrate               float?  ✅ bpm
    elev_high                   float?  ⬜ metres
    elev_low                    float?  ⬜ metres
    trainer                     bool    ⬜ indoor flag
    commute                     bool    ⬜
    manual                      bool    ⬜
    private                     bool    ⬜
    visibility                  str     ⬜ "everyone", "followers_only", "only_me"
    flagged                     bool    ⬜
    gear_id                     str?    🔵 shoe id
    timezone                    str     ⬜ "(GMT+05:00) Asia/[REDACTED-LOCATION]"
    utc_offset                  float   ⬜
    location_city               str?    ⬜
    location_state              str?    ⬜
    location_country            str?    ⬜
    achievement_count           int     ⬜
    kudos_count                 int     ⬜
    comment_count               int     ⬜
    athlete_count               int     ⬜
    photo_count                 int     ⬜
    total_photo_count           int     ⬜
    pr_count                    int     ⬜ personal records
    has_kudoed                  bool    ⬜
    heartrate_opt_out           bool    ⬜
    display_hide_heartrate_option bool  ⬜
    from_accepted_tag           bool    ⬜
"""

# ─── DetailedActivity (resource_state=3) ───
# From GET /activities/{id} — WE DON'T CURRENTLY FETCH THIS
# Contains everything in SummaryActivity PLUS:

DETAILED_ACTIVITY_EXTRA_FIELDS = """
    description                 str?    ⬜ user-entered description
    calories                    float?  🔵 kcal — energy expenditure
    perceived_exertion          int?    💰 1-10 RPE scale (Summit)
    prefer_perceived_exertion   bool?   💰 (Summit)
    hide_from_home              bool    ⬜
    embed_token                 str     ⬜ for embedding
    photos                      dict    ⬜ {primary, count, use_primary_photo}
    stats_visibility            list    ⬜ per-field visibility
    available_zones             list    💰 empty for free users

    # Nested collections — all from GET /activities/{id}?include_all_efforts=true
    best_efforts                list    🔵 [RunningEffort] — best times per standard distance (400m, 1km, 5km, etc.)
    splits_metric               list    🔵 [Split] — per-km splits with GAP!
    splits_standard             list    🔵 [Split] — per-mile splits
    laps                        list    🔵 [Lap] — auto-detected laps
    segment_efforts             list    🔵 [SegmentEffort] — segments hit during activity
    gear                        dict    🔵 {id, name, nickname, primary, retired, distance, converted_distance}
    similar_activities          dict    🔵 trend analysis (see below)
"""

# ─── Split (from splits_metric / splits_standard) ───
# 🔵 HIGH VALUE — contains GAP!

SPLIT_FIELDS = """
    distance                    float   🔵 metres (≈1000 for metric splits)
    elapsed_time                int     🔵 seconds
    moving_time                 int     🔵 seconds
    elevation_difference        float   🔵 metres (net)
    average_speed               float   🔵 m/s
    average_grade_adjusted_speed float  🔵 m/s — THIS IS GAP (Grade Adjusted Pace)!
    average_heartrate           float?  🔵 bpm
    pace_zone                   int?    🔵 Strava's pace zone (1-6)
    split                       int     🔵 split number
"""

# ─── Lap ───

LAP_FIELDS = """
    id                          int     ⬜
    name                        str     ⬜ "Lap 1"
    elapsed_time                int     🔵 seconds
    moving_time                 int     🔵 seconds
    distance                    float   🔵 metres
    average_speed               float   🔵 m/s
    max_speed                   float   🔵 m/s
    lap_index                   int     ⬜
    split                       int     ⬜
    start_index                 int     🔵 stream index start
    end_index                   int     🔵 stream index end
    start_date                  str     ⬜
    start_date_local            str     ⬜
    average_cadence             float?  ⬜
    device_watts                bool?   ⬜
"""

# ─── RunningEffort (best_efforts) ───

BEST_EFFORT_FIELDS = """
    id                          int     ⬜
    name                        str     🔵 "400m", "1km", "5km", etc.
    elapsed_time                int     🔵 seconds
    moving_time                 int     🔵 seconds
    distance                    float   🔵 metres
    pr_rank                     int?    🔵 personal record rank (null if not PR)
    start_index                 int     🔵 stream index start
    end_index                   int     🔵 stream index end
"""

# ─── Similar Activities (trend) ───

SIMILAR_ACTIVITIES_FIELDS = """
    effort_count                int     🔵 number of comparable activities
    average_speed               float   🔵 m/s — your average for this type
    min_average_speed           float   🔵
    mid_average_speed           float   🔵 median
    max_average_speed           float   🔵
    pr_rank                     int?    🔵
    frequency_milestone         dict?   🔵
    trend                       dict    🔵 {
        speeds: [float]           last 5 activities' speeds
        current_activity_index: int  your position in the list
        min_speed: float
        mid_speed: float
        max_speed: float
        direction: int            -1 = slowing, 0 = flat, 1 = speeding up
    }
"""

# ─── Activity Zones (💰 Summit) ───

ACTIVITY_ZONE_FIELDS = """
    💰 Requires Summit subscription (402 without)
    Returns list of zones, each:
    {
        score: float              suffer_score for HR zones
        distribution_buckets: [{min, max, time}]  time in each zone
        type: "heartrate" | "pace" | "power"
        sensor_based: bool
    }
    NOTE: We compute our own zones from raw streams. This endpoint would
    give us Strava's official zone distribution + suffer_score.
"""

# ─── Gear ───

GEAR_FIELDS = """
    id                          str     ✅ gear_id
    name                        str     ✅
    nickname                    str?    🔵 "joma black"
    primary                     bool    ✅
    retired                     bool    🔵 useful for tracking when to replace
    distance                    float   ✅ total metres on this shoe
    converted_distance          float   ✅ km
    resource_state              int     ⬜
"""

# ─── Athlete Stats ───

ATHLETE_STATS_FIELDS = """
    recent_run_totals: {count, distance, moving_time, elapsed_time, elevation_gain}
    recent_swim_totals: {...}
    recent_ride_totals: {...}
    ytd_run_totals: {...}
    ytd_swim_totals: {...}
    ytd_ride_totals: {...}
    all_run_totals: {...}
    all_swim_totals: {...}
    all_ride_totals: {...}
    biggest_ride_distance: float
    biggest_climb_elevation_gain: float
    ⬜ We fetch via cmd_stats but don't use much
"""

# ─── HR Zones (GET /athlete/zones) ───

HR_ZONES_FIELDS = """
    Returns: {
        heart_rate: {
            custom_zones: bool,
            zones: [{min, max}]  — 5 zones
        },
        power: {...}  (cycling)
    }
    ✅ We store this and use it for TRIMP calculation
"""


# ══════════════════════════════════════════════
# WHAT WE'RE MISSING (ranked by value)
# ══════════════════════════════════════════════

# 🔵 HIGH VALUE — fetch via GET /activities/{id}
#   1. splits_metric[].average_grade_adjusted_speed  → GAP per km!
#      This is Strava's Grade Adjusted Pace — normalises for hills.
#      We currently compute our own decoupling, but GAP would give us
#      per-km adjusted pace FOR FREE without our custom math.
#
#   2. similar_activities.trend.direction + speeds
#      Strava's built-in trend: are you getting faster or slower for
#      similar runs? Covers ~5 last comparable activities.
#      Complements our own trend analysis.
#
#   3. calories  → energy expenditure (kcal)
#      Samsung Health estimates this, Strava estimates it too.
#      Could cross-validate.
#
#   4. splits_metric[].average_heartrate  → per-km heart rate
#      Much cheaper than computing from raw streams (our current approach).
#
#   5. best_efforts  → PR tracking per distance (400m, 1km, 5km)
#      Auto-detected, useful for fitness benchmarks.
#
#   6. gear.retired  → know when shoes are done
#
#   7. workout_type  → run category (race, long, workout, easy)
#      We don't currently track this.

# 💰 SUMMIT ONLY
#   - Activity zones (suffer_score, zone time distribution)
#   - perceived_exertion (RPE 1-10)
#   - Segment efforts history (subscription required)
#   Max currently does NOT have Summit.

# ⬜ NOT INTERESTING
#   - Comments, kudos, photos, social features
#   - Route planning
#   - Club data
