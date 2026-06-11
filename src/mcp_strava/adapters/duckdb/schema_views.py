"""DuckDB aggregate/read-model view DDL."""

from __future__ import annotations

DUCKDB_AGGREGATE_VIEW_SQL = """
CREATE OR REPLACE VIEW v_activity_aggregate_facts AS
SELECT
    f.activity_id,
    f.activity_day,
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
    day,
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
    day,
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
        day,
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
        MAX(a.activity_day) AS last_hike_day
    FROM days d
    LEFT JOIN activity_metric_facts a
        ON a.sport_type = 'Hike'
       AND a.activity_day <= d.day
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
    as_of_day,
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


def create_aggregate_views(conn) -> None:
    conn.execute(DUCKDB_AGGREGATE_VIEW_SQL)
