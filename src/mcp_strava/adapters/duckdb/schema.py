"""DuckDB schema inventory for the primary Strava mirror."""

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

DUCKDB_SCHEMA_SQL = """
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

CREATE TABLE activity_metric_facts (
    activity_id BIGINT NOT NULL,
    activity_day DATE NOT NULL,
    sport_type VARCHAR NOT NULL,
    source_hash VARCHAR NOT NULL,
    source_revision BIGINT NOT NULL,
    metric_version BIGINT NOT NULL,
    computed_at VARCHAR NOT NULL,
    completeness_status VARCHAR NOT NULL,
    missing_reasons_json VARCHAR NOT NULL DEFAULT '[]',
    trimp DOUBLE,
    zone1_seconds BIGINT NOT NULL DEFAULT 0,
    zone2_seconds BIGINT NOT NULL DEFAULT 0,
    zone3_seconds BIGINT NOT NULL DEFAULT 0,
    zone4_seconds BIGINT NOT NULL DEFAULT 0,
    zone5_seconds BIGINT NOT NULL DEFAULT 0,
    hr_recovery_pause_count BIGINT NOT NULL DEFAULT 0,
    hr_recovery_total_rest_sec BIGINT NOT NULL DEFAULT 0,
    hr_recovery_median_rate DOUBLE,
    hr_recovery_best_rate DOUBLE,
    hr_recovery_worst_rate DOUBLE,
    hr_recovery_avg_rate DOUBLE,
    vertical_speed_vmh BIGINT,
    vertical_speed_total_ascent_m DOUBLE,
    vertical_speed_duration_hours DOUBLE,
    cardiac_cost DOUBLE,
    adjusted_cardiac_cost DOUBLE,
    cardiac_drift_pct DOUBLE,
    cardiac_drift_severity VARCHAR,
    cardiac_drift_significant BIGINT NOT NULL DEFAULT 0,
    cardiac_drift_quality VARCHAR,
    hrr_pct DOUBLE,
    anomaly_count BIGINT NOT NULL DEFAULT 0,
    distance_m DOUBLE,
    moving_time_s BIGINT,
    elapsed_time_s BIGINT,
    elevation_gain_m DOUBLE,
    heartrate_sample_count BIGINT NOT NULL DEFAULT 0,
    stream_sample_count BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (activity_id, metric_version)
);

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

DUCKDB_VIEWS: tuple[str, ...] = ()


def create_schema(conn) -> None:
    conn.execute(DUCKDB_SCHEMA_SQL)
