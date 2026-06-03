"""DuckDB schema inventory for the primary Strava mirror."""

from mcp_strava.metric_registry import (
    activity_metric_fact_add_column_sql,
    activity_metric_facts_table_sql,
    materialized_fact_column_definition,
)

DUCKDB_TABLES: tuple[str, ...] = (
    "activities",
    "streams",
    "stream_channels",
    "athlete_zones",
    "sync_log",
    "kudos",
    "refresh_state",
    "refresh_requests",
    "activity_source_state",
    "metric_dirty_activities",
    "activity_metric_facts",
    "daily_load_facts",
    "training_model_daily",
    "rolling_period_facts",
    "read_model_refresh_runs",
    "read_model_logic_version",
    "schema_migration_log",
)

DATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "activities": ("activity_day",),
    "activity_source_state": ("activity_day",),
    "metric_dirty_activities": ("activity_day",),
    "activity_metric_facts": ("activity_day",),
    "daily_load_facts": ("day",),
    "training_model_daily": ("day",),
    "rolling_period_facts": ("as_of_day",),
}

DUCKDB_SCHEMA_SQL = f"""
CREATE TABLE activities (
    id BIGINT PRIMARY KEY,
    activity_day DATE NOT NULL,
    date VARCHAR,
    name VARCHAR,
    sport_type VARCHAR,
    distance DOUBLE,
    moving_time BIGINT,
    elapsed_time BIGINT,
    total_elevation_gain DOUBLE,
    summary_json VARCHAR,
    detail_json VARCHAR,
    synced_at VARCHAR
);

CREATE TABLE streams (
    activity_id BIGINT NOT NULL,
    time_offset BIGINT NOT NULL,
    heartrate BIGINT,
    velocity DOUBLE,
    altitude DOUBLE,
    cadence BIGINT,
    lat DOUBLE,
    lng DOUBLE,
    grade DOUBLE,
    gap_speed DOUBLE,
    gap_distance DOUBLE,
    is_moving BIGINT,
    values_json VARCHAR,
    PRIMARY KEY (activity_id, time_offset)
);

CREATE TABLE stream_channels (
    activity_id BIGINT NOT NULL,
    channel_key VARCHAR NOT NULL,
    original_size BIGINT,
    resolution VARCHAR,
    series_type VARCHAR,
    fetched_at VARCHAR NOT NULL,
    batch_id VARCHAR,
    status VARCHAR NOT NULL,
    error VARCHAR,
    PRIMARY KEY (activity_id, channel_key)
);

CREATE TABLE athlete_zones (
    id BIGINT PRIMARY KEY,
    fetched_at VARCHAR,
    zones_json VARCHAR
);

CREATE TABLE sync_log (
    id BIGINT PRIMARY KEY,
    timestamp VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    activities_seen BIGINT,
    activities_new BIGINT,
    streams_fetched BIGINT,
    details_fetched BIGINT,
    api_calls BIGINT,
    error VARCHAR,
    kudos_fetched BIGINT
);

CREATE TABLE kudos (
    activity_id BIGINT NOT NULL,
    firstname VARCHAR NOT NULL DEFAULT '',
    lastname VARCHAR NOT NULL DEFAULT '',
    fetched_at VARCHAR NOT NULL,
    PRIMARY KEY (activity_id, firstname, lastname)
);

CREATE TABLE refresh_state (
    id BIGINT PRIMARY KEY,
    last_success_at VARCHAR,
    last_attempt_at VARCHAR,
    last_status VARCHAR,
    last_error_code VARCHAR,
    lease_owner VARCHAR,
    lease_expires_at VARCHAR,
    backoff_until VARCHAR,
    checkpoint_stage VARCHAR,
    checkpoint_cursor VARCHAR
);

CREATE TABLE refresh_requests (
    id BIGINT PRIMARY KEY,
    reason VARCHAR NOT NULL,
    requested_for_day VARCHAR NOT NULL,
    requested_at VARCHAR NOT NULL,
    consumed_at VARCHAR
);

CREATE TABLE activity_source_state (
    activity_id BIGINT PRIMARY KEY,
    activity_day DATE NOT NULL,
    summary_hash VARCHAR NOT NULL,
    detail_hash VARCHAR NOT NULL,
    streams_hash VARCHAR NOT NULL,
    channels_hash VARCHAR NOT NULL,
    source_hash VARCHAR NOT NULL,
    source_revision BIGINT NOT NULL,
    changed_at VARCHAR NOT NULL
);

CREATE TABLE metric_dirty_activities (
    activity_id BIGINT NOT NULL,
    activity_day DATE NOT NULL,
    metric_version BIGINT NOT NULL,
    source_revision BIGINT NOT NULL,
    reason VARCHAR NOT NULL,
    queued_at VARCHAR NOT NULL,
    attempt_count BIGINT NOT NULL DEFAULT 0,
    last_error VARCHAR,
    PRIMARY KEY (activity_id, metric_version)
);

{activity_metric_facts_table_sql()}

CREATE TABLE daily_load_facts (
    day DATE NOT NULL,
    scope VARCHAR NOT NULL,
    sport_type VARCHAR NOT NULL,
    metric_version BIGINT NOT NULL,
    computed_at VARCHAR NOT NULL,
    completeness_status VARCHAR NOT NULL,
    missing_reasons_json VARCHAR NOT NULL DEFAULT '[]',
    activity_count BIGINT NOT NULL DEFAULT 0,
    stream_point_count BIGINT NOT NULL DEFAULT 0,
    heartrate_point_count BIGINT NOT NULL DEFAULT 0,
    observed_trimp DOUBLE,
    effective_trimp DOUBLE NOT NULL DEFAULT 0.0,
    distance_m DOUBLE NOT NULL DEFAULT 0.0,
    moving_time_s BIGINT NOT NULL DEFAULT 0,
    elevation_gain_m DOUBLE NOT NULL DEFAULT 0.0,
    zone4_seconds BIGINT NOT NULL DEFAULT 0,
    zone5_seconds BIGINT NOT NULL DEFAULT 0,
    high_zone_seconds BIGINT NOT NULL DEFAULT 0,
    anomaly_count BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (day, scope, sport_type, metric_version)
);

CREATE TABLE training_model_daily (
    day DATE NOT NULL,
    scope VARCHAR NOT NULL,
    sport_type VARCHAR NOT NULL,
    metric_version BIGINT NOT NULL,
    computed_at VARCHAR NOT NULL,
    completeness_status VARCHAR NOT NULL,
    missing_reasons_json VARCHAR NOT NULL DEFAULT '[]',
    effective_trimp DOUBLE NOT NULL DEFAULT 0.0,
    observed_trimp DOUBLE,
    fitness DOUBLE,
    fatigue DOUBLE,
    form DOUBLE,
    form_zone VARCHAR,
    acwr_zone VARCHAR,
    acwr DOUBLE,
    load_7d DOUBLE,
    load_28d DOUBLE,
    load_42d DOUBLE,
    input_days BIGINT NOT NULL DEFAULT 0,
    missing_days BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (day, scope, sport_type, metric_version)
);

CREATE TABLE rolling_period_facts (
    as_of_day DATE NOT NULL,
    window_days BIGINT NOT NULL,
    scope VARCHAR NOT NULL,
    sport_type VARCHAR NOT NULL,
    metric_version BIGINT NOT NULL,
    computed_at VARCHAR NOT NULL,
    completeness_status VARCHAR NOT NULL,
    missing_reasons_json VARCHAR NOT NULL DEFAULT '[]',
    activity_count BIGINT NOT NULL DEFAULT 0,
    active_days BIGINT NOT NULL DEFAULT 0,
    rest_days BIGINT NOT NULL DEFAULT 0,
    observed_trimp DOUBLE,
    effective_trimp DOUBLE NOT NULL DEFAULT 0.0,
    distance_m DOUBLE NOT NULL DEFAULT 0.0,
    moving_time_s BIGINT NOT NULL DEFAULT 0,
    elevation_gain_m DOUBLE NOT NULL DEFAULT 0.0,
    high_zone_seconds BIGINT NOT NULL DEFAULT 0,
    anomaly_count BIGINT NOT NULL DEFAULT 0,
    fitness DOUBLE,
    fatigue DOUBLE,
    form DOUBLE,
    form_zone VARCHAR,
    acwr_zone VARCHAR,
    acwr DOUBLE,
    median_cardiac_cost DOUBLE,
    median_adjusted_cardiac_cost DOUBLE,
    median_hr_recovery DOUBLE,
    median_cardiac_drift_pct DOUBLE,
    PRIMARY KEY (as_of_day, window_days, scope, sport_type, metric_version)
);

CREATE TABLE read_model_refresh_runs (
    id BIGINT PRIMARY KEY,
    started_at VARCHAR NOT NULL,
    finished_at VARCHAR,
    status VARCHAR NOT NULL,
    metric_version BIGINT NOT NULL,
    trigger_reason VARCHAR,
    lease_owner VARCHAR,
    activities_considered BIGINT NOT NULL DEFAULT 0,
    activities_materialized BIGINT NOT NULL DEFAULT 0,
    daily_facts_materialized BIGINT NOT NULL DEFAULT 0,
    model_facts_materialized BIGINT NOT NULL DEFAULT 0,
    rolling_facts_materialized BIGINT NOT NULL DEFAULT 0,
    dirty_rows_claimed BIGINT NOT NULL DEFAULT 0,
    dirty_rows_cleared BIGINT NOT NULL DEFAULT 0,
    checkpoint_cursor VARCHAR,
    attempt_count BIGINT NOT NULL DEFAULT 0,
    last_error VARCHAR
);

-- Singleton (one row, id=1) sidecar that turns metric_version into a
-- system-managed monotonic counter sourced from the live logic fingerprint.
-- IF NOT EXISTS so this DDL and the repository seed path (which also creates
-- the table) are both idempotent and order-independent on live + fresh DBs.
CREATE TABLE IF NOT EXISTS read_model_logic_version (
    id BIGINT PRIMARY KEY,
    metric_version BIGINT NOT NULL,
    logic_fingerprint VARCHAR NOT NULL,
    changed_at VARCHAR NOT NULL
);

CREATE TABLE schema_migration_log (
    version BIGINT PRIMARY KEY,
    name VARCHAR NOT NULL,
    applied_at VARCHAR NOT NULL,
    checksum VARCHAR NOT NULL
);

CREATE INDEX idx_duckdb_activities_day_id ON activities(activity_day, id);
CREATE INDEX idx_duckdb_activity_metric_day_sport_version ON activity_metric_facts(activity_day, sport_type, metric_version);
CREATE INDEX idx_duckdb_daily_load_day_scope_sport_version ON daily_load_facts(day, scope, sport_type, metric_version);
CREATE INDEX idx_duckdb_training_model_day_scope_sport_version ON training_model_daily(day, scope, sport_type, metric_version);
CREATE INDEX idx_duckdb_rolling_period_asof_window_scope_sport_version
    ON rolling_period_facts(as_of_day, window_days, scope, sport_type, metric_version);
"""

DUCKDB_VIEWS: tuple[str, ...] = (
    "v_activity_aggregate_facts",
    "v_daily_aggregate_facts",
    "v_training_model_state_facts",
    "v_historical_context_facts",
    "v_rolling_aggregate_facts",
    "v_metric_version_status",
)

ACTIVITY_METRIC_FACT_LATE_COLUMNS: tuple[str, ...] = (
    "observed_min_hr",
    "observed_max_hr",
    "hr_zone_model",
    "hr_max_used",
    "hr_rest_used",
    "calories_kcal",
    "start_time_local",
)

DUCKDB_AGGREGATE_VIEW_SQL = """
CREATE OR REPLACE VIEW v_activity_aggregate_facts AS
SELECT
    f.activity_id,
    CAST(f.activity_day AS DATE) AS activity_day,
    f.sport_type,
    f.metric_version,
    f.computed_at,
    f.completeness_status,
    f.missing_reasons_json,
    1::BIGINT AS activity_count,
    CASE WHEN f.trimp IS NULL THEN 0 ELSE 1 END::BIGINT AS activity_sample_count,
    f.trimp,
    f.zone1_seconds,
    f.zone2_seconds,
    f.zone3_seconds,
    f.zone4_seconds,
    f.zone5_seconds,
    f.hr_recovery_pause_count,
    f.hr_recovery_total_rest_sec,
    f.hr_recovery_median_rate,
    f.hr_recovery_best_rate,
    f.hr_recovery_worst_rate,
    f.hr_recovery_avg_rate,
    f.vertical_speed_vmh,
    f.vertical_speed_total_ascent_m,
    f.vertical_speed_duration_hours,
    f.cardiac_cost,
    f.adjusted_cardiac_cost,
    f.cardiac_drift_pct,
    f.cardiac_drift_severity,
    f.cardiac_drift_significant,
    f.cardiac_drift_quality,
    f.hrr_pct,
    f.anomaly_count,
    f.distance_m,
    f.calories_kcal,  -- raw kcal; backs the `calories` sum metric
    f.moving_time_s,
    f.elapsed_time_s,
    f.elevation_gain_m,
    f.heartrate_sample_count,
    f.stream_sample_count,
    TRY_CAST(json_extract_string(a.summary_json, '$.average_heartrate') AS DOUBLE) AS avg_hr,
    TRY_CAST(json_extract_string(a.summary_json, '$.max_heartrate') AS DOUBLE) AS max_hr,
    COALESCE(TRY_CAST(json_extract_string(a.summary_json, '$.kudos_count') AS DOUBLE), 0.0) AS kudos_count
FROM activity_metric_facts f
LEFT JOIN activities a ON a.id = f.activity_id;

CREATE OR REPLACE VIEW v_daily_aggregate_facts AS
SELECT
    CAST(day AS DATE) AS day,
    scope,
    sport_type,
    metric_version,
    computed_at,
    completeness_status,
    missing_reasons_json,
    activity_count,
    stream_point_count,
    heartrate_point_count,
    observed_trimp,
    effective_trimp,
    distance_m,
    moving_time_s,
    elevation_gain_m,
    zone4_seconds,
    zone5_seconds,
    high_zone_seconds,
    anomaly_count,
    CASE WHEN activity_count > 0 THEN 1 ELSE 0 END::BIGINT AS active_day_count,
    CASE WHEN activity_count = 0 THEN 1 ELSE 0 END::BIGINT AS rest_day_count,
    1::BIGINT AS calendar_days,
    1::BIGINT AS calendar_day_count
FROM daily_load_facts;

CREATE OR REPLACE VIEW v_training_model_state_facts AS
SELECT
    CAST(day AS DATE) AS day,
    scope,
    sport_type,
    metric_version,
    computed_at,
    completeness_status,
    missing_reasons_json,
    effective_trimp,
    observed_trimp,
    fitness,
    fatigue,
    form,
    form_zone,
    acwr_zone,
    acwr,
    load_7d,
    load_28d,
    load_42d,
    input_days,
    missing_days,
    1::BIGINT AS model_day_count,
    0::BIGINT AS activity_count
FROM training_model_daily;

CREATE OR REPLACE VIEW v_historical_context_facts AS
WITH days AS (
    SELECT
        CAST(day AS DATE) AS day,
        metric_version,
        computed_at,
        completeness_status,
        missing_reasons_json,
        activity_count
    FROM daily_load_facts
    WHERE scope = 'all' AND sport_type = 'all'
),
last_hikes AS (
    SELECT
        d.day,
        MAX(CAST(a.activity_day AS DATE)) AS last_hike_day
    FROM days d
    LEFT JOIN activity_metric_facts a
        ON a.sport_type = 'Hike'
       AND CAST(a.activity_day AS DATE) <= d.day
    GROUP BY d.day
)
SELECT
    d.day,
    'all' AS scope,
    'all' AS sport_type,
    d.metric_version,
    d.computed_at,
    d.completeness_status,
    d.missing_reasons_json,
    d.activity_count,
    CASE
        WHEN d.activity_count <= 0 THEN 0
        ELSE (
            SELECT COUNT(*)
            FROM days recent
            WHERE recent.day <= d.day
              AND recent.activity_count > 0
              AND recent.day > COALESCE(
                    (
                        SELECT MAX(gap.day)
                        FROM days gap
                        WHERE gap.day <= d.day AND gap.activity_count = 0
                    ),
                    DATE '1900-01-01'
              )
        )
    END::BIGINT AS activity_streak_days,
    CASE
        WHEN d.activity_count > 0 THEN 0
        ELSE (
            SELECT COUNT(*)
            FROM days recent
            WHERE recent.day <= d.day
              AND recent.activity_count = 0
              AND recent.day > COALESCE(
                    (
                        SELECT MAX(gap.day)
                        FROM days gap
                        WHERE gap.day <= d.day AND gap.activity_count > 0
                    ),
                    DATE '1900-01-01'
              )
        )
    END::BIGINT AS rest_streak_days,
    CASE
        WHEN h.last_hike_day IS NULL THEN NULL
        ELSE date_diff('day', h.last_hike_day, d.day)
    END::BIGINT AS last_hike_days_ago,
    1::BIGINT AS calendar_days,
    1::BIGINT AS calendar_day_count
FROM days d
LEFT JOIN last_hikes h ON h.day = d.day;

CREATE OR REPLACE VIEW v_rolling_aggregate_facts AS
SELECT
    CAST(as_of_day AS DATE) AS as_of_day,
    window_days,
    scope,
    sport_type,
    metric_version,
    computed_at,
    completeness_status,
    missing_reasons_json,
    activity_count,
    active_days,
    rest_days,
    observed_trimp,
    effective_trimp,
    distance_m,
    moving_time_s,
    elevation_gain_m,
    high_zone_seconds,
    anomaly_count,
    fitness,
    fatigue,
    form,
    form_zone,
    acwr_zone,
    acwr,
    median_cardiac_cost,
    median_adjusted_cardiac_cost,
    median_hr_recovery,
    median_cardiac_drift_pct,
    window_days::BIGINT AS calendar_days,
    window_days::BIGINT AS calendar_day_count,
    activity_count::BIGINT AS rolling_sample_count,
    CASE WHEN window_days > 0 THEN effective_trimp / window_days ELSE NULL END AS daily_avg_trimp_7d,
    CASE WHEN window_days > 0 THEN effective_trimp / window_days ELSE NULL END AS daily_avg_trimp_28d,
    CASE WHEN window_days > 0 THEN effective_trimp / window_days ELSE NULL END AS daily_avg_trimp_90d
FROM rolling_period_facts;

CREATE OR REPLACE VIEW v_metric_version_status AS
SELECT metric_version, COUNT(*) AS fact_row_count, MAX(computed_at) AS last_materialized_at
FROM (
    SELECT metric_version, computed_at FROM activity_metric_facts
    UNION ALL
    SELECT metric_version, computed_at FROM daily_load_facts
    UNION ALL
    SELECT metric_version, computed_at FROM training_model_daily
    UNION ALL
    SELECT metric_version, computed_at FROM rolling_period_facts
)
GROUP BY metric_version;
"""


def ensure_provenance_columns(conn) -> None:
    """Additive migration: add later-introduced activity_metric_facts columns
    (HR provenance + calories) if they do not already exist. Safe to call on any
    existing DuckDB file; new columns are NULL on old rows until re-materialized."""
    for column_name in ACTIVITY_METRIC_FACT_LATE_COLUMNS:
        definition = materialized_fact_column_definition("activity_metric_facts", column_name)
        if not definition.nullable and definition.default_sql is None:
            raise RuntimeError(
                f"Unsafe additive migration for activity_metric_facts.{column_name}: NOT NULL without DEFAULT"
            )
        sql = activity_metric_fact_add_column_sql(column_name)
        conn.execute(sql)


def create_aggregate_views(conn) -> None:
    conn.execute(DUCKDB_AGGREGATE_VIEW_SQL)


def create_schema(conn) -> None:
    conn.execute(DUCKDB_SCHEMA_SQL)
    create_aggregate_views(conn)
