from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from mcp_strava.adapters.sqlite.migrations import run_migrations
from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.application.metric_registry import MATERIALIZED_ROLLING_WINDOW_DAYS


READ_MODEL_METADATA_KEYS = {
    "status",
    "last_materialized_at",
    "dirty_count",
    "oldest_dirty_day",
    "metric_versions_present",
    "stale_reason",
}


def _create_base_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            date TEXT, name TEXT, sport_type TEXT,
            distance REAL, moving_time INTEGER, elapsed_time INTEGER,
            total_elevation_gain REAL,
            summary_json TEXT, detail_json TEXT, synced_at TEXT
        );
        CREATE TABLE streams (
            activity_id INTEGER, time_offset INTEGER,
            heartrate INTEGER, velocity REAL, altitude REAL,
            cadence INTEGER, lat REAL, lng REAL, grade REAL,
            gap_speed REAL, gap_distance REAL, is_moving INTEGER, latlng TEXT,
            PRIMARY KEY (activity_id, time_offset)
        );
        CREATE INDEX idx_streams_act ON streams(activity_id);
        CREATE TABLE athlete_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT, zones_json TEXT
        );
        CREATE TABLE sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            activities_seen INTEGER,
            activities_new INTEGER,
            streams_fetched INTEGER,
            details_fetched INTEGER,
            api_calls INTEGER,
            error TEXT,
            kudos_fetched INTEGER
        );
        CREATE TABLE kudos (
            activity_id INTEGER NOT NULL,
            firstname TEXT NOT NULL DEFAULT '',
            lastname TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (activity_id, firstname, lastname)
        );
        PRAGMA user_version=1;
        """
    )
    conn.commit()
    conn.close()
    run_migrations(path)
    opened = sqlite3.connect(path)
    opened.row_factory = sqlite3.Row
    return opened


def _insert_activity(conn: sqlite3.Connection, activity_id: int, day: str, *, sport_type: str, with_hr: bool) -> None:
    avg_hr = 145.0 if with_hr else None
    max_hr = 165.0 if with_hr else None
    summary = {
        "id": activity_id,
        "name": f"Workout {activity_id}",
        "sport_type": sport_type,
        "start_date_local": f"{day}T07:00:00",
        "distance": 5000.0,
        "moving_time": 1800,
        "elapsed_time": 1830,
        "total_elevation_gain": 30.0,
        "has_heartrate": with_hr,
        "average_heartrate": avg_hr,
        "max_heartrate": max_hr,
        "kudos_count": 2 if activity_id == 701 else 0,
    }
    conn.execute(
        """
        INSERT INTO activities (
            id, date, name, sport_type, distance, moving_time, elapsed_time,
            total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            activity_id,
            f"{day}T07:00:00",
            f"Workout {activity_id}",
            sport_type,
            5000.0,
            1800,
            1830,
            30.0,
            json.dumps(summary),
            None,
            f"{day}T08:00:00",
        ),
    )


def _repo_with_facts(path: Path) -> SQLiteRepository:
    conn = _create_base_db(path)
    _insert_activity(conn, 701, "2026-05-20", sport_type="Run", with_hr=True)
    _insert_activity(conn, 702, "2026-05-21", sport_type="Run", with_hr=True)
    _insert_activity(conn, 703, "2026-05-19", sport_type="Hike", with_hr=False)
    conn.executemany(
        "INSERT INTO kudos (activity_id, firstname, lastname, fetched_at) VALUES (?, ?, ?, ?)",
        [
            (701, "Ada", "Lovelace", "2026-05-21T06:01:00"),
            (701, "Grace", "Hopper", "2026-05-21T06:01:00"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO activity_metric_facts (
            activity_id, activity_day, sport_type, source_hash, source_revision,
            metric_version, computed_at, completeness_status, missing_reasons_json,
            trimp, zone1_seconds, zone2_seconds, zone3_seconds, zone4_seconds, zone5_seconds,
            hr_recovery_pause_count, hr_recovery_total_rest_sec,
            hr_recovery_median_rate, hr_recovery_best_rate, hr_recovery_worst_rate,
            hr_recovery_avg_rate, vertical_speed_vmh, vertical_speed_total_ascent_m,
            vertical_speed_duration_hours, cardiac_cost, cardiac_drift_pct,
            adjusted_cardiac_cost, cardiac_drift_severity, cardiac_drift_significant,
            cardiac_drift_quality, hrr_pct,
            anomaly_count, distance_m, moving_time_s, elapsed_time_s, elevation_gain_m,
            heartrate_sample_count, stream_sample_count
        ) VALUES (
            :activity_id, :activity_day, :sport_type, :source_hash, :source_revision,
            :metric_version, :computed_at, :completeness_status, :missing_reasons_json,
            :trimp, :zone1_seconds, :zone2_seconds, :zone3_seconds, :zone4_seconds, :zone5_seconds,
            :hr_recovery_pause_count, :hr_recovery_total_rest_sec,
            :hr_recovery_median_rate, :hr_recovery_best_rate, :hr_recovery_worst_rate,
            :hr_recovery_avg_rate, :vertical_speed_vmh, :vertical_speed_total_ascent_m,
            :vertical_speed_duration_hours, :cardiac_cost, :cardiac_drift_pct,
            :adjusted_cardiac_cost, :cardiac_drift_severity, :cardiac_drift_significant,
            :cardiac_drift_quality, :hrr_pct,
            :anomaly_count, :distance_m, :moving_time_s, :elapsed_time_s, :elevation_gain_m,
            :heartrate_sample_count, :stream_sample_count
        )
        """,
        [
            {
                "activity_id": 701,
                "activity_day": "2026-05-20",
                "sport_type": "Run",
                "source_hash": "hash-701",
                "source_revision": 1,
                "metric_version": 1,
                "computed_at": "2026-05-21T06:00:00",
                "completeness_status": "complete",
                "missing_reasons_json": "[]",
                "trimp": 105.0,
                "zone1_seconds": 120,
                "zone2_seconds": 240,
                "zone3_seconds": 360,
                "zone4_seconds": 180,
                "zone5_seconds": 30,
                "hr_recovery_pause_count": 1,
                "hr_recovery_total_rest_sec": 45,
                "hr_recovery_median_rate": 18.0,
                "hr_recovery_best_rate": 28.0,
                "hr_recovery_worst_rate": 8.0,
                "hr_recovery_avg_rate": 17.0,
                "vertical_speed_vmh": 420,
                "vertical_speed_total_ascent_m": 130.0,
                "vertical_speed_duration_hours": 0.6,
                "cardiac_cost": 44.0,
                "adjusted_cardiac_cost": 41.3,
                "cardiac_drift_pct": 2.5,
                "cardiac_drift_severity": "stable",
                "cardiac_drift_significant": 0,
                "cardiac_drift_quality": "good",
                "hrr_pct": 68.0,
                "anomaly_count": 0,
                "distance_m": 5000.0,
                "moving_time_s": 1800,
                "elapsed_time_s": 1830,
                "elevation_gain_m": 30.0,
                "heartrate_sample_count": 130,
                "stream_sample_count": 130,
            },
            {
                "activity_id": 702,
                "activity_day": "2026-05-21",
                "sport_type": "Run",
                "source_hash": "hash-702",
                "source_revision": 1,
                "metric_version": 1,
                "computed_at": "2026-05-21T06:05:00",
                "completeness_status": "partial",
                "missing_reasons_json": json.dumps(["missing_streams"]),
                "trimp": 88.0,
                "zone1_seconds": 100,
                "zone2_seconds": 200,
                "zone3_seconds": 300,
                "zone4_seconds": 120,
                "zone5_seconds": 0,
                "hr_recovery_pause_count": 0,
                "hr_recovery_total_rest_sec": 0,
                "hr_recovery_median_rate": None,
                "hr_recovery_best_rate": None,
                "hr_recovery_worst_rate": None,
                "hr_recovery_avg_rate": None,
                "vertical_speed_vmh": None,
                "vertical_speed_total_ascent_m": None,
                "vertical_speed_duration_hours": None,
                "cardiac_cost": None,
                "adjusted_cardiac_cost": None,
                "cardiac_drift_pct": None,
                "cardiac_drift_severity": None,
                "cardiac_drift_significant": 0,
                "cardiac_drift_quality": None,
                "hrr_pct": None,
                "anomaly_count": 1,
                "distance_m": 5000.0,
                "moving_time_s": 1800,
                "elapsed_time_s": 1830,
                "elevation_gain_m": 30.0,
                "heartrate_sample_count": 130,
                "stream_sample_count": 0,
            },
            {
                "activity_id": 703,
                "activity_day": "2026-05-19",
                "sport_type": "Hike",
                "source_hash": "hash-703",
                "source_revision": 1,
                "metric_version": 1,
                "computed_at": "2026-05-21T06:03:00",
                "completeness_status": "partial",
                "missing_reasons_json": json.dumps(["missing_hr"]),
                "trimp": 75.0,
                "zone1_seconds": 0,
                "zone2_seconds": 0,
                "zone3_seconds": 0,
                "zone4_seconds": 0,
                "zone5_seconds": 0,
                "hr_recovery_pause_count": 0,
                "hr_recovery_total_rest_sec": 0,
                "hr_recovery_median_rate": None,
                "hr_recovery_best_rate": None,
                "hr_recovery_worst_rate": None,
                "hr_recovery_avg_rate": None,
                "vertical_speed_vmh": 300,
                "vertical_speed_total_ascent_m": 500.0,
                "vertical_speed_duration_hours": 1.7,
                "cardiac_cost": None,
                "adjusted_cardiac_cost": None,
                "cardiac_drift_pct": None,
                "cardiac_drift_severity": None,
                "cardiac_drift_significant": 0,
                "cardiac_drift_quality": None,
                "hrr_pct": None,
                "anomaly_count": 0,
                "distance_m": 9000.0,
                "moving_time_s": 7200,
                "elapsed_time_s": 7500,
                "elevation_gain_m": 500.0,
                "heartrate_sample_count": 0,
                "stream_sample_count": 0,
            },
        ],
    )
    conn.executemany(
        """
        INSERT INTO daily_load_facts (
            day, scope, sport_type, metric_version, computed_at,
            completeness_status, missing_reasons_json, activity_count,
            stream_point_count, heartrate_point_count, observed_trimp,
            effective_trimp, distance_m, moving_time_s, elevation_gain_m,
            zone4_seconds, zone5_seconds, high_zone_seconds, anomaly_count
        ) VALUES (?, 'all', 'all', 1, '2026-05-21T06:10:00', 'complete', '[]', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("2026-05-19", 1, 0, 0, 75.0, 75.0, 9000.0, 7200, 500.0, 0, 0, 0, 0),
            ("2026-05-20", 1, 130, 130, 105.0, 105.0, 5000.0, 1800, 30.0, 180, 30, 210, 0),
            ("2026-05-21", 1, 0, 130, 88.0, 88.0, 5000.0, 1800, 30.0, 120, 0, 120, 1),
        ],
    )
    conn.execute(
        """
        INSERT INTO training_model_daily (
            day, scope, sport_type, metric_version, computed_at,
            completeness_status, missing_reasons_json, effective_trimp,
            observed_trimp, fitness, fatigue, form,
            form_zone, acwr_zone, acwr, load_7d, load_28d, load_42d, input_days, missing_days
        ) VALUES (
            '2026-05-21', 'all', 'all', 1, '2026-05-21T06:15:00',
            'complete', '[]', 88.0, 88.0, 42.0, 37.0, 5.0,
            'normal', 'sweet_spot', 0.881, 180.0, 268.0, 370.0, 3, 0
        )
        """
    )
    rolling_inputs = {
        7: (268.0, 3, 4),
        14: (268.0, 3, 11),
        28: (268.0, 3, 25),
        42: (268.0, 3, 39),
        90: (268.0, 3, 87),
    }
    for window in MATERIALIZED_ROLLING_WINDOW_DAYS:
        effective, active, rest = rolling_inputs[window]
        conn.execute(
            """
            INSERT INTO rolling_period_facts (
                as_of_day, window_days, scope, sport_type, metric_version,
                computed_at, completeness_status, missing_reasons_json,
                activity_count, active_days, rest_days, observed_trimp,
                effective_trimp, distance_m, moving_time_s, elevation_gain_m,
                high_zone_seconds, anomaly_count, fitness, fatigue, form, form_zone,
                acwr_zone, acwr, median_cardiac_cost, median_adjusted_cardiac_cost,
                median_hr_recovery, median_cardiac_drift_pct
            ) VALUES (
                '2026-05-21', ?, 'all', 'all', 1, '2026-05-21T06:20:00',
                'complete', '[]', 3, ?, ?, ?, ?, 19000.0, 10800,
                560.0, 330, 1, 42.0, 37.0, 5.0, 'normal',
                'sweet_spot', 0.881, 44.0, 41.3, 18.0, 2.5
            )
            """,
            (window, active, rest, effective, effective),
        )
    conn.execute(
        """
        INSERT INTO read_model_refresh_runs (
            started_at, finished_at, status, metric_version, trigger_reason,
            activities_considered, activities_materialized, daily_facts_materialized,
            model_facts_materialized, rolling_facts_materialized,
            dirty_rows_claimed, dirty_rows_cleared, attempt_count
        ) VALUES (
            '2026-05-21T06:00:00', '2026-05-21T06:20:00', 'ok', 1,
            'test', 3, 3, 3, 1, 4, 3, 3, 1
        )
        """
    )
    conn.execute(
        """
        UPDATE refresh_state
        SET last_success_at = '2026-05-21T06:30:00', last_attempt_at = '2026-05-21T06:30:00', last_status = 'ok'
        WHERE id = 1
        """
    )
    conn.commit()
    return SQLiteRepository.from_connection(conn)


def test_read_model_status_reports_metadata_fields(tmp_path: Path) -> None:
    repo = _repo_with_facts(tmp_path / "status.db")
    with repo:
        repo.enqueue_metric_dirty_activity(
            activity_id=702,
            activity_day="2026-05-21",
            metric_version=1,
            source_revision=2,
            reason="test_dirty",
            queued_at="2026-05-21T07:00:00",
        )
        status = repo.read_model_status(metric_version=1)

    assert READ_MODEL_METADATA_KEYS <= set(status)
    assert status["status"] == "stale"
    assert status["last_materialized_at"] == "2026-05-21T06:20:00"
    assert status["dirty_count"] == 1
    assert status["oldest_dirty_day"] == "2026-05-21"
    assert status["metric_versions_present"] == [1]
    assert status["stale_reason"] == "dirty_queue_not_empty"


def test_activity_fact_queries_use_half_open_ranges_and_sport_filter(tmp_path: Path) -> None:
    repo = _repo_with_facts(tmp_path / "activity-facts.db")
    with repo:
        rows = repo.fetch_activity_metric_facts(
            "2026-05-20",
            "2026-05-22",
            sport="Run",
            metric_version=1,
            limit=10,
        )
        hike_rows = repo.fetch_activity_metric_facts(
            "2026-05-19",
            "2026-05-20",
            sport="Hike",
            metric_version=1,
            limit=10,
        )

    assert [row["activity_id"] for row in rows] == [702, 701]
    assert [row["activity_id"] for row in hike_rows] == [703]


def test_fact_queries_cover_model_daily_load_rolling_and_detail(tmp_path: Path) -> None:
    repo = _repo_with_facts(tmp_path / "fact-tiers.db")
    with repo:
        latest_model = repo.fetch_latest_training_model_day(metric_version=1)
        detail = repo.fetch_activity_metric_fact(701, metric_version=1)
        daily = repo.fetch_daily_load_facts("2026-05-19", "2026-05-22", scope="all", metric_version=1)
        rolling = repo.fetch_rolling_period_facts("2026-05-21", 14, scope="all", metric_version=1)
        rolling_by_window = repo.fetch_rolling_period_facts_by_windows(
            "2026-05-21",
            MATERIALIZED_ROLLING_WINDOW_DAYS,
            scope="all",
            metric_version=1,
        )

    assert latest_model is not None
    assert latest_model["day"] == "2026-05-21"
    assert detail is not None
    assert detail["activity_id"] == 701
    assert [row["day"] for row in daily] == ["2026-05-19", "2026-05-20", "2026-05-21"]
    assert rolling is not None
    assert rolling["window_days"] == 14
    assert sorted(rolling_by_window) == list(MATERIALIZED_ROLLING_WINDOW_DAYS)
    assert rolling_by_window[14]["window_days"] == 14


def test_read_model_queries_fail_soft_when_schema_missing(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "v4.db")
    conn.row_factory = sqlite3.Row
    repo = SQLiteRepository.from_connection(conn)
    with repo:
        status = repo.read_model_status(metric_version=1)
        assert repo.fetch_activity_metric_facts("2026-05-01", "2026-05-02", metric_version=1) == []
        assert repo.fetch_activity_metric_fact(1, metric_version=1) is None
        assert repo.fetch_latest_training_model_day(metric_version=1) is None
        assert repo.fetch_daily_load_facts("2026-05-01", "2026-05-02", scope="all", metric_version=1) == []
        assert repo.fetch_rolling_period_facts("2026-05-01", 7, scope="all", metric_version=1) is None
        assert repo.fetch_rolling_period_facts_by_windows("2026-05-01", (7, 14), scope="all", metric_version=1) == {}

    assert status["status"] == "unavailable"
    assert status["stale_reason"] == "read_model_schema_missing"


def _query_plan_details(conn: sqlite3.Connection, sql: str, params: tuple[object, ...]) -> list[str]:
    rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
    return [str(row["detail"]) for row in rows]


def test_hot_read_model_query_plans_use_fact_indexes_and_never_scan_streams(tmp_path: Path) -> None:
    repo = _repo_with_facts(tmp_path / "query-plan.db")
    with repo:
        plan_groups = {
            "activity_metric_facts": _query_plan_details(
                repo.conn,
                """
                SELECT f.*, a.name AS activity_name, a.date AS activity_date, a.summary_json
                FROM activity_metric_facts f
                LEFT JOIN activities a ON a.id = f.activity_id
                WHERE f.activity_day >= ?
                  AND f.activity_day < ?
                  AND f.sport_type = ?
                  AND f.metric_version = ?
                ORDER BY f.activity_day DESC, f.activity_id DESC
                LIMIT ?
                """,
                ("2026-05-01", "2026-06-01", "Run", 1, 20),
            ),
            "daily_load_facts": _query_plan_details(
                repo.conn,
                """
                SELECT *
                FROM daily_load_facts
                WHERE day >= ?
                  AND day < ?
                  AND scope = ?
                  AND sport_type = ?
                  AND metric_version = ?
                ORDER BY day ASC
                """,
                ("2026-05-01", "2026-06-01", "all", "all", 1),
            ),
            "training_model_daily": _query_plan_details(
                repo.conn,
                """
                SELECT *
                FROM training_model_daily
                WHERE metric_version = ?
                  AND scope = ?
                  AND sport_type = ?
                  AND day <= ?
                ORDER BY day DESC
                LIMIT 1
                """,
                (1, "all", "all", "2026-05-24"),
            ),
            "rolling_period_facts": _query_plan_details(
                repo.conn,
                """
                SELECT *
                FROM rolling_period_facts
                WHERE as_of_day = ?
                  AND window_days = ?
                  AND scope = ?
                  AND sport_type = ?
                  AND metric_version = ?
                ORDER BY metric_version DESC
                LIMIT 1
                """,
                ("2026-05-21", 14, "all", "all", 1),
            ),
        }

    details = [detail for group in plan_groups.values() for detail in group]
    assert not any("SCAN streams" in detail for detail in details)
    expected_index_fragments = {
        "activity_metric_facts": "SEARCH f USING INDEX idx_activity_metric_day_sport_version",
        "daily_load_facts": "SEARCH daily_load_facts USING INDEX idx_daily_load_day_scope_sport_version",
        "training_model_daily": "SEARCH training_model_daily USING INDEX idx_training_model_day_scope_sport_version",
        "rolling_period_facts": "SEARCH rolling_period_facts USING INDEX sqlite_autoindex_rolling_period_facts_1",
    }
    assert all(
        any(expected_fragment in detail for detail in plan_groups[table])
        for table, expected_fragment in expected_index_fragments.items()
    )


def test_hot_read_model_repository_queries_do_not_use_substr_date_filters() -> None:
    source = Path("src/mcp_strava/adapters/sqlite/repository.py").read_text(encoding="utf-8")
    hot_methods = [
        "fetch_latest_training_model_day",
        "fetch_activity_metric_facts",
        "fetch_activity_metric_fact",
        "fetch_daily_load_facts",
        "fetch_rolling_period_facts",
    ]
    violations: list[str] = []
    for method in hot_methods:
        start = source.index(f"    def {method}")
        next_method = source.find("\n    def ", start + 1)
        segment = source[start:] if next_method == -1 else source[start:next_method]
        if "SUBSTR(" in segment.upper():
            violations.append(method)

    assert violations == []


def test_duckdb_aggregate_query_layer_uses_views_not_raw_streams_or_period_tables() -> None:
    from mcp_strava.adapters.duckdb.aggregate_queries import AggregateRequest

    query_source = Path("src/mcp_strava/adapters/duckdb/aggregate_queries.py").read_text(encoding="utf-8")
    schema_source = Path("src/mcp_strava/adapters/duckdb/schema.py").read_text(encoding="utf-8")
    lowered_query = query_source.lower()
    lowered_schema = schema_source.lower()

    for forbidden in (
        "from streams",
        "join streams",
        "from stream_channels",
        "join stream_channels",
        "raw_sql",
        "query_plan",
    ):
        assert forbidden not in lowered_query

    assert "time_bucket" in lowered_query
    assert "weighted_avg" in lowered_query
    assert "quantile_cont" in lowered_query
    assert "v_activity_aggregate_facts" in query_source
    assert "v_daily_aggregate_facts" in query_source
    assert "v_training_model_state_facts" in query_source
    assert "v_metric_version_status" in query_source
    assert "create table period" not in lowered_schema
    assert "period_aggregate" not in lowered_schema

    request_fields = set(AggregateRequest.__dataclass_fields__)
    assert {"sql", "raw_sql", "table", "table_name", "column", "column_name", "query_plan", "gear_id"}.isdisjoint(
        request_fields
    )
