from __future__ import annotations

import ast
import json
import sqlite3
import urllib.request
from datetime import datetime
from pathlib import Path

import pytest

from mcp_strava.adapters.duckdb.connection import open_fixture_db
from mcp_strava.adapters.sqlite.migrations import run_migrations
from mcp_strava.application.metric_registry import METRIC_REGISTRY, metrics_for_aggregate_bundle
from mcp_strava.types import (
    CompletenessMetadata,
    FreshnessMetadata,
    ServiceEnvelope,
    ServiceRationale,
    ServiceWarning,
    dc_to_dict,
)
from tests.test_read_model_queries import READ_MODEL_METADATA_KEYS, _repo_with_facts
from tests.test_training_aggregates import _aggregate_fixture

FORBIDDEN_KEYS = {
    "recommendation",
    "action",
    "intensity",
    "on_track",
    "should",
    "ready",
    "best_scenario",
    "sync_log",
    "sql",
    "token",
    "raw_strava",
}

SAFETY_WARNING_CODES = {
    "z5_excessive",
    "hike_load_consecutive_high",
    "running_volume_jump_high",
    "cardiac_drift_severe_yesterday",
    "hr_anomaly_burst",
    "low_hr_data",
    "insufficient_history",
}

ENVELOPE_KEYS = {"data", "freshness", "completeness", "warnings", "rationale"}


@pytest.fixture(autouse=True)
def forbid_live_network_and_reset_cache(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError("live network forbidden")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)

    import mcp_strava.metrics as metrics

    metrics._hr_max_cache = None
    yield
    metrics._hr_max_cache = None


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


def _insert_activity(conn: sqlite3.Connection, activity_id: int, day: str, *, sport_type: str = "Run", with_hr: bool = True) -> None:
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


def _insert_streams(conn: sqlite3.Connection, activity_id: int, *, with_hr: bool = True) -> None:
    for second in range(130):
        conn.execute(
            """
            INSERT INTO streams (
                activity_id, time_offset, heartrate, velocity, altitude,
                cadence, lat, lng, grade, gap_speed, gap_distance, is_moving
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity_id,
                second,
                145 if with_hr else None,
                3.0,
                100.0 + second * 0.01,
                85,
                43.2,
                76.9,
                0.0,
                3.0,
                float(second),
                1,
            ),
        )


def _fixture_conn(path: Path) -> sqlite3.Connection:
    conn = _create_base_db(path)
    _insert_activity(conn, 701, "2026-05-20", sport_type="Run", with_hr=True)
    _insert_streams(conn, 701, with_hr=True)
    _insert_activity(conn, 702, "2026-05-21", sport_type="Run", with_hr=True)
    _insert_streams(conn, 702, with_hr=True)
    _insert_activity(conn, 703, "2026-05-19", sport_type="Hike", with_hr=False)
    conn.execute(
        """
        UPDATE refresh_state
        SET last_success_at = ?, last_attempt_at = ?, last_status = 'ok'
        WHERE id = 1
        """,
        ("2026-05-21T06:00:00", "2026-05-21T06:00:00"),
    )
    conn.commit()
    return conn


def _fixture_conn_compare(path: Path) -> sqlite3.Connection:
    conn = _create_base_db(path)
    # Period A: run + hike baseline
    _insert_activity(conn, 801, "2026-05-01", sport_type="Run", with_hr=True)
    _insert_streams(conn, 801, with_hr=True)
    _insert_activity(conn, 802, "2026-05-03", sport_type="Run", with_hr=True)
    _insert_streams(conn, 802, with_hr=True)
    _insert_activity(conn, 803, "2026-05-05", sport_type="Hike", with_hr=False)
    # Period B: run-heavy with higher volume and another hike
    _insert_activity(conn, 811, "2026-05-08", sport_type="Run", with_hr=True)
    _insert_streams(conn, 811, with_hr=True)
    _insert_activity(conn, 812, "2026-05-10", sport_type="Run", with_hr=True)
    _insert_streams(conn, 812, with_hr=True)
    _insert_activity(conn, 813, "2026-05-12", sport_type="Run", with_hr=True)
    _insert_streams(conn, 813, with_hr=True)
    _insert_activity(conn, 814, "2026-05-13", sport_type="Hike", with_hr=False)
    conn.execute(
        """
        UPDATE refresh_state
        SET last_success_at = ?, last_attempt_at = ?, last_status = 'ok'
        WHERE id = 1
        """,
        ("2026-05-14T06:00:00", "2026-05-14T06:00:00"),
    )
    conn.commit()
    return conn


def _walk_no_forbidden_keys(obj) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = str(key).lower()
            assert lowered not in FORBIDDEN_KEYS
            _walk_no_forbidden_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            _walk_no_forbidden_keys(item)


def _walk_no_cyrillic_or_coaching_text(obj) -> None:
    coaching_markers = ("should", "ready", "rest day", "easy run", "weekly plan", "recommended")
    if isinstance(obj, dict):
        for value in obj.values():
            _walk_no_cyrillic_or_coaching_text(value)
    elif isinstance(obj, list):
        for item in obj:
            _walk_no_cyrillic_or_coaching_text(item)
    elif isinstance(obj, str):
        assert not any("\u0400" <= ch <= "\u04FF" for ch in obj)
        lowered = obj.lower()
        assert not any(marker in lowered for marker in coaching_markers)


def _assert_metric_ids_exist(metric_ids: set[str]) -> None:
    for metric_id in metric_ids:
        assert metric_id in METRIC_REGISTRY


def _repo_metric_ids_for_tool(tool_id: str) -> set[str]:
    return {metric_id for metric_id, definition in METRIC_REGISTRY.items() if tool_id in definition.exposed_in}


def _assert_read_model_metadata(payload: dict) -> None:
    metadata = payload["completeness"]["coverage"].get("read_model")
    assert isinstance(metadata, dict)
    assert READ_MODEL_METADATA_KEYS <= set(metadata)
    assert metadata["last_materialized_at"] == "2026-05-21T06:20:00"
    assert metadata["metric_versions_present"] == [1]


def _read_model_current() -> dict[str, object]:
    return {
        "status": "current",
        "last_materialized_at": "2026-05-21T06:20:00",
        "dirty_count": 0,
        "oldest_dirty_day": None,
        "metric_versions_present": [1],
        "stale_reason": None,
    }


def _block_legacy_recompute(monkeypatch: pytest.MonkeyPatch) -> None:
    import mcp_strava.application.metric_services as metric_services

    def _blocked(*_args, **_kwargs):
        raise AssertionError("MCP metric service must not recompute from raw mirror data")

    for name in (
        "enrich_activity",
        "daily_report_from_connection",
        "weekly_digest",
        "check_z5_minutes",
        "check_hr_anomalies",
        "calc_banister",
    ):
        if hasattr(metric_services, name):
            monkeypatch.setattr(metric_services, name, _blocked, raising=False)


def test_get_fitness_state_service_returns_metric_bundle_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.application.metric_services import get_fitness_state_service

    _block_legacy_recompute(monkeypatch)
    repo = _repo_with_facts(tmp_path / "fitness.db")
    try:
        envelope = get_fitness_state_service(
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=repo.conn,
        )
    finally:
        repo.close()

    payload = dc_to_dict(envelope)
    assert isinstance(envelope, ServiceEnvelope)
    assert set(payload) == ENVELOPE_KEYS
    _assert_read_model_metadata(payload)

    expected_metrics = {
        "fitness",
        "fatigue",
        "form",
        "form_zone",
        "acwr",
        "acwr_zone",
        "weekly_trimp",
        "total_trimp_14d",
        "avg_trimp_per_day",
        "active_days",
        "rest_days",
        "daily_avg_trimp_7d",
        "daily_avg_trimp_28d",
        "daily_avg_trimp_90d",
        "rolling_median_cc",
        "rolling_median_cc_adj",
        "rolling_median_hr_recovery",
        "rolling_median_cardiac_drift_pct",
        "volume_7d",
        "volume_28d",
    }
    assert expected_metrics.issubset(set(payload["data"]))
    _assert_metric_ids_exist(set(payload["data"]).intersection(_repo_metric_ids_for_tool("get_fitness_state")))

    _walk_no_forbidden_keys(payload)
    _walk_no_cyrillic_or_coaching_text(payload["data"])


def test_list_workouts_service_respects_filters_and_returns_compact_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.application.metric_services import list_workouts_service

    _block_legacy_recompute(monkeypatch)
    repo = _repo_with_facts(tmp_path / "workouts.db")
    try:
        envelope = list_workouts_service(
            limit=2,
            start_date="2026-05-20",
            end_date="2026-05-21",
            sport="Run",
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=repo.conn,
        )
    finally:
        repo.close()

    payload = dc_to_dict(envelope)
    assert isinstance(envelope, ServiceEnvelope)
    assert set(payload) == ENVELOPE_KEYS
    _assert_read_model_metadata(payload)
    assert [row["activity_id"] for row in payload["data"]] == [702, 701]

    required_row_keys = {
        "activity_id",
        "activity_date",
        "sport_type",
        "activity_name",
        "distance_km",
        "moving_time_min",
        "elevation_m",
        "trimp",
        "avg_hr",
        "max_hr",
        "kudos_count",
        "completeness",
    }
    for row in payload["data"]:
        assert required_row_keys.issubset(set(row))
        assert row["sport_type"] == "Run"
        assert "2026-05-20" <= row["activity_date"] <= "2026-05-21"

    _assert_metric_ids_exist(required_row_keys - {"completeness"})
    _walk_no_forbidden_keys(payload)


def test_get_workout_detail_service_returns_full_metric_bundle_and_missing_reasons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.application.metric_services import get_workout_detail_service

    _block_legacy_recompute(monkeypatch)
    repo = _repo_with_facts(tmp_path / "detail.db")
    try:
        full = get_workout_detail_service(
            activity_id=701,
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=repo.conn,
        )
        partial = get_workout_detail_service(
            activity_id=702,
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=repo.conn,
        )
    finally:
        repo.close()

    full_payload = dc_to_dict(full)
    partial_payload = dc_to_dict(partial)
    _assert_read_model_metadata(full_payload)
    _assert_read_model_metadata(partial_payload)

    required_detail_keys = {
        "time_in_hr_zones_min",
        "hr_recovery_median_bpm_per_min",
        "vertical_speed_m_per_h",
        "cardiac_cost",
        "cardiac_cost_adjusted",
        "cardiac_drift_pct",
        "cardiac_drift_severity",
        "cardiac_drift_significant",
        "cardiac_drift_quality",
        "hrr_pct",
        "kudos_count",
        "kudos_names",
    }
    assert required_detail_keys.issubset(set(full_payload["data"]))
    _assert_metric_ids_exist(required_detail_keys)
    assert full_payload["data"]["kudos_count"] == 2
    assert full_payload["data"]["kudos_names"] == ["Ada Lovelace", "Grace Hopper"]

    assert partial_payload["completeness"]["status"] == "partial"
    assert set(partial_payload["completeness"]["missing"]) & {"missing_hr", "missing_streams", "metric_unavailable"}

    for warning in full_payload["warnings"] + partial_payload["warnings"]:
        assert warning["code"] in SAFETY_WARNING_CODES | {"mirror_stale", "missing_hr", "missing_streams", "metric_unavailable"}
        if warning["code"] in SAFETY_WARNING_CODES:
            evidence = warning.get("evidence") or {}
            if evidence:
                assert isinstance(evidence, dict)


def test_metric_services_source_does_not_serialize_then_filter_daily_report() -> None:
    source_path = Path("src/mcp_strava/application/metric_services.py")
    text = source_path.read_text(encoding="utf-8")
    lowered = text.lower()

    forbidden_patterns = [
        "dc_to_dict(report)",
        "asdict(report)",
        "dataclasses.asdict(report)",
        "dailyreport",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in lowered

    module = ast.parse(text)
    has_projection = any(
        isinstance(node, ast.FunctionDef) and node.name == "_project_fitness_state_metrics"
        for node in module.body
    )
    assert has_projection


def test_compare_periods_service_includes_global_and_per_sport_comparisons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.application.metric_services import compare_periods_service

    _block_legacy_recompute(monkeypatch)
    db_path = _aggregate_fixture(tmp_path / "compare.duckdb")
    conn = open_fixture_db(db_path)
    try:
        envelope = compare_periods_service(
            period_a_start="2026-05-05",
            period_a_end="2026-05-13",
            period_b_start="2026-05-13",
            period_b_end="2026-06-01",
            sport=None,
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    payload = dc_to_dict(envelope)
    assert set(payload) == ENVELOPE_KEYS
    metadata = payload["completeness"]["coverage"].get("read_model")
    assert isinstance(metadata, dict)
    assert READ_MODEL_METADATA_KEYS <= set(metadata)
    assert metadata["status"] == "current"
    assert "global" in payload["data"]
    assert "per_sport" in payload["data"]

    global_metrics = payload["data"]["global"]["metrics"]
    per_sport = payload["data"]["per_sport"]
    required = {
        "trimp",
        "distance_km",
        "moving_time_min",
        "elevation_m",
        "fitness",
        "fatigue",
        "form",
        "acwr",
        "cardiac_cost",
        "cardiac_cost_adjusted",
        "cardiac_drift_pct",
        "cardiac_drift_significant",
        "avg_hr",
        "max_hr",
        "hr_recovery_median_bpm_per_min",
        "hrr_pct",
        "vertical_speed_m_per_h",
        "time_in_hr_zones_min",
    }
    for metric_id in required:
        assert metric_id in global_metrics or any(metric_id in values["metrics"] for values in per_sport.values())

    scalar_record = global_metrics["trimp"]
    for field in ("period_a", "period_b", "delta", "delta_pct", "trend_direction", "sample_size", "coverage", "missing_reasons"):
        assert field in scalar_record
    assert scalar_record["trend_direction"] in {"up", "down", "flat", "unavailable"}

    run_metrics = per_sport["Run"]["metrics"]
    assert "cardiac_cost" in run_metrics
    assert "metric_id" not in run_metrics["cardiac_cost"]
    assert run_metrics["cardiac_cost"]["metric_version_status"] in {"single", "unavailable", "mixed_degraded"}

    dist = global_metrics["time_in_hr_zones_min"]
    assert "buckets" in dist["period_a"]
    assert "buckets" in dist["period_b"]
    assert "bucket_deltas" in dist
    assert "bucket_delta_pct" in dist
    assert "distribution_overlap_pct" in dist
    if dist["distribution_overlap_pct"] is None:
        assert dist["missing_reasons"]

    serialized = json.dumps(payload).lower()
    for forbidden in ("heart_improved", "vessels_improved", "ready", "should", "recommendation"):
        assert forbidden not in serialized


def test_compare_periods_service_delegates_to_bounded_all_time_aggregates(monkeypatch: pytest.MonkeyPatch) -> None:
    import mcp_strava.application.metric_services as metric_services

    calls: list[object] = []

    class FakeRepo:
        def read_model_status(self, *_args, **_kwargs) -> dict[str, object]:
            return _read_model_current()

        def get_refresh_state(self):
            return None

        def latest_activity_timestamp(self):
            return None

        def fetch_activity_metric_facts(self, *_args, **_kwargs) -> list:
            return []

        def fetch_latest_training_model_day(self, *_args, **_kwargs):
            return None

        def fetch_rolling_period_facts(self, *_args, **_kwargs):
            return None

    def fake_aggregate_service(request, **kwargs):
        calls.append(request)
        value = 100.0 if len(calls) == 1 else 70.0
        missing = [] if len(calls) == 1 else ["missing_hr"]
        return ServiceEnvelope(
            data={
                "request": {
                    "bucket": request.bucket,
                    "start_day": request.start_day,
                    "end_day_exclusive": request.end_day_exclusive,
                    "scope": request.scope,
                },
                "metrics": ["trimp"],
                "rows": [
                    {
                        "bucket_start": request.start_day,
                        "bucket_end": request.end_day_exclusive,
                        "bucket_width": "all_time",
                        "metric_id": "trimp",
                        "unit": "trimp",
                        "calculation": "Prepared aggregate TRIMP fact sum.",
                        "aggregation_mode": "sum",
                        "denominator": "trimp",
                        "value": value,
                        "quantiles": None,
                        "distribution": None,
                        "sample_size": 3 if len(calls) == 1 else 2,
                        "activity_count": 3 if len(calls) == 1 else 2,
                        "null_count": 0,
                        "excluded_count": 0,
                        "completeness_status": "complete" if len(calls) == 1 else "partial",
                        "missing_reasons": missing,
                        "metric_version_status": "single",
                        "materialized_at": "2026-05-21T06:20:00",
                        "mirror_freshness": {},
                        "read_model_freshness": _read_model_current(),
                        "scope": "global",
                        "sport_type": None,
                    }
                ],
            },
            freshness=FreshnessMetadata(
                freshness_state="fresh",
                checked_at="2026-05-21T09:00:00",
                last_successful_refresh_at="2026-05-21T06:00:00",
                refresh_age_seconds=10800,
                last_activity_at="2026-05-21T06:20:00",
                last_activity_age_seconds=9600,
            ),
            completeness=CompletenessMetadata(
                status="complete" if len(calls) == 1 else "partial",
                missing=missing,
                coverage={"read_model": _read_model_current(), "row_count": 1},
            ),
            warnings=[
                ServiceWarning(
                    code="aggregate_rows_incomplete",
                    severity="warning",
                    message="Some aggregate rows have incomplete source coverage.",
                    field="rows",
                )
            ],
            rationale=[ServiceRationale(code="aggregate_layer", message="Prepared aggregate rows.")],
        )

    monkeypatch.setattr(metric_services, "repository_from_connection", lambda _conn: FakeRepo())
    monkeypatch.setattr(
        metric_services,
        "build_freshness_metadata",
        lambda *_args, **_kwargs: FreshnessMetadata(
            freshness_state="fresh",
            checked_at="2026-05-21T09:00:00",
            last_successful_refresh_at="2026-05-21T06:00:00",
            refresh_age_seconds=10800,
            last_activity_at="2026-05-21T06:20:00",
            last_activity_age_seconds=9600,
        ),
    )
    monkeypatch.setattr(metric_services, "get_training_aggregates_service", fake_aggregate_service, raising=False)

    envelope = metric_services.compare_periods_service(
        period_a_start="2026-05-01",
        period_a_end="2026-05-08",
        period_b_start="2026-05-08",
        period_b_end="2026-05-15",
        sport=None,
        now=datetime.fromisoformat("2026-05-21T09:00:00"),
        signal_first_use=False,
        connection=object(),
    )
    payload = dc_to_dict(envelope)

    assert len(calls) == 2
    assert [(call.bucket, call.start_day, call.end_day_exclusive) for call in calls] == [
        ("all_time", "2026-05-01", "2026-05-08"),
        ("all_time", "2026-05-08", "2026-05-15"),
    ]
    metric = payload["data"]["global"]["metrics"]["trimp"]
    assert metric["period_a"]["value"] == 100.0
    assert metric["period_b"]["value"] == 70.0
    assert metric["delta"] == 30.0
    assert metric["delta_pct"] == pytest.approx(42.86)
    assert metric["trend_direction"] == "up"
    assert metric["sample_size"] == {"period_a": 3, "period_b": 2}
    assert "missing_hr" in metric["missing_reasons"]
    assert metric["metric_version_status"] == "single"
    assert payload["completeness"]["status"] == "partial"
    assert "missing_hr" in payload["completeness"]["missing"]
    assert "missing_denominator" in payload["completeness"]["coverage"]["supported_missing_reasons"]
    assert [warning["code"] for warning in payload["warnings"]] == ["aggregate_rows_incomplete"]


def test_compare_periods_service_with_sport_filter_uses_only_filtered_sport(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.application.metric_services import compare_periods_service

    _block_legacy_recompute(monkeypatch)
    db_path = _aggregate_fixture(tmp_path / "compare-run.duckdb")
    conn = open_fixture_db(db_path)
    try:
        envelope = compare_periods_service(
            period_a_start="2026-05-05",
            period_a_end="2026-05-13",
            period_b_start="2026-05-13",
            period_b_end="2026-06-01",
            sport="Run",
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    payload = dc_to_dict(envelope)
    assert payload["data"]["global"]["scope_filter"] == "sport"
    assert set(payload["data"]["per_sport"]) == {"Run"}
    trimp = payload["data"]["global"]["metrics"]["trimp"]
    assert trimp["period_a"]["sample_size"] == 2
    assert trimp["period_b"]["sample_size"] == 1


def test_project_fitness_state_service_supports_standard_scenarios(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.application.metric_services import project_fitness_state_service

    _block_legacy_recompute(monkeypatch)
    repo = _repo_with_facts(tmp_path / "project.db")
    try:
        envelope = project_fitness_state_service(
            target_date="2026-05-25",
            scenarios=["rest", "easy", "maintain"],
            custom_daily_trimp=None,
            now=datetime.fromisoformat("2026-05-22T09:00:00"),
            signal_first_use=False,
            connection=repo.conn,
        )
    finally:
        repo.close()

    payload = dc_to_dict(envelope)
    assert set(payload) == ENVELOPE_KEYS
    _assert_read_model_metadata(payload)
    for scenario in ("rest", "easy", "maintain"):
        assert scenario in payload["data"]["scenarios"]
        item = payload["data"]["scenarios"][scenario]
        assert "daily_rows" in item
        assert item["daily_rows"]
        row = item["daily_rows"][0]
        for key in ("projected_daily_trimp", "projected_fitness", "projected_fatigue", "projected_form"):
            assert key in row
        assert "target_date_form" in item
        assert "model_assumptions" in item

    serialized = json.dumps(payload).lower()
    for forbidden in ("best_scenario", "recommended_scenario", "should_train", "ready", "on_track"):
        assert forbidden not in serialized


def test_tool_metric_payloads_match_registry_exposure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.application.metric_services import (
        compare_periods_service,
        get_fitness_state_service,
        get_workout_detail_service,
        list_workouts_service,
        project_fitness_state_service,
    )

    _block_legacy_recompute(monkeypatch)
    repo = _repo_with_facts(tmp_path / "registry-match.db")
    try:
        now = datetime.fromisoformat("2026-05-21T09:00:00")
        fitness = dc_to_dict(get_fitness_state_service(now=now, signal_first_use=False, connection=repo.conn))
        workouts = dc_to_dict(list_workouts_service(limit=1, now=now, signal_first_use=False, connection=repo.conn))
        detail = dc_to_dict(get_workout_detail_service(701, now=now, signal_first_use=False, connection=repo.conn))
        projection = dc_to_dict(
            project_fitness_state_service(
                target_date="2026-05-23",
                scenarios=["easy"],
                now=now,
                signal_first_use=False,
                connection=repo.conn,
            )
        )
    finally:
        repo.close()

    compare_conn = open_fixture_db(_aggregate_fixture(tmp_path / "registry-compare.duckdb"))
    try:
        compare = dc_to_dict(
            compare_periods_service(
                period_a_start="2026-05-05",
                period_a_end="2026-05-13",
                period_b_start="2026-05-13",
                period_b_end="2026-06-01",
                now=now,
                signal_first_use=False,
                connection=compare_conn,
            )
        )
    finally:
        compare_conn.close()

    assert set(fitness["data"]) == _repo_metric_ids_for_tool("get_fitness_state")
    assert all(value is not None for value in fitness["data"].values())

    assert set(workouts["data"][0]) - {"completeness"} == _repo_metric_ids_for_tool("list_workouts")
    assert set(detail["data"]) - {"completeness"} == _repo_metric_ids_for_tool("get_workout_detail")
    assert detail["data"]["hr_recovery_pauses"] is not None
    assert detail["data"]["hr_recovery_total_rest_sec"] is not None
    assert detail["data"]["cardiac_drift_severity"] is not None
    assert detail["data"]["cardiac_drift_significant"] is not None
    assert detail["data"]["cardiac_drift_quality"] is not None

    compare_metric_ids = set(compare["data"]["global"]["metrics"])
    for sport_payload in compare["data"]["per_sport"].values():
        compare_metric_ids.update(sport_payload["metrics"])
    assert compare_metric_ids == set(metrics_for_aggregate_bundle("period_comparison"))

    easy = projection["data"]["scenarios"]["easy"]
    projection_metric_ids = {"target_date_form", "post_weekend_monday_form", "activity_template_trimp"}
    projection_metric_ids.update(easy["daily_rows"][0].keys() - {"date"})
    assert projection_metric_ids == _repo_metric_ids_for_tool("project_fitness_state")
    assert easy["post_weekend_monday_form"] is not None


def test_metric_services_use_duckdb_repository_for_duckdb_connections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp_strava.adapters.duckdb.connection import open_expected_mirror_db
    from mcp_strava.application.metric_services import get_fitness_state_service, list_workouts_service
    from tests.test_training_aggregates import _aggregate_fixture

    _block_legacy_recompute(monkeypatch)
    db_path = _aggregate_fixture(tmp_path / "primary.duckdb")
    conn = open_expected_mirror_db(db_path)
    try:
        workouts = dc_to_dict(
            list_workouts_service(
                limit=1,
                now=datetime.fromisoformat("2026-05-21T14:00:00"),
                signal_first_use=False,
                connection=conn,
            )
        )
        fitness = dc_to_dict(
            get_fitness_state_service(
                now=datetime.fromisoformat("2026-05-21T14:00:00"),
                signal_first_use=False,
                connection=conn,
            )
        )
    finally:
        conn.close()

    assert workouts["data"][0]["activity_id"] == 105
    assert workouts["data"][0]["activity_date"] == "2026-06-01"
    assert workouts["data"][0]["trimp"] == 999.0
    assert fitness["data"]["fitness"] == 40.0


def test_project_fitness_state_service_validates_custom_rows(tmp_path: Path) -> None:
    from mcp_strava.application.metric_services import project_fitness_state_service

    conn = _fixture_conn_compare(tmp_path / "project-custom.db")
    try:
        envelope = project_fitness_state_service(
            target_date="2026-05-25",
            scenarios=["custom"],
            custom_daily_trimp=[
                {"date": "2026-05-22", "trimp": 40.0},
                {"date": "2026-05-24", "trimp": 55.0},
            ],
            now=datetime.fromisoformat("2026-05-22T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()
    payload = dc_to_dict(envelope)
    custom = payload["data"]["scenarios"]["custom"]
    assert custom["daily_rows"][-1]["date"] == "2026-05-25"
    assert custom["daily_rows"][1]["projected_daily_trimp"] == 0.0

    conn_invalid = _fixture_conn_compare(tmp_path / "project-invalid.db")
    with pytest.raises(ValueError):
        project_fitness_state_service(
            target_date="2026-05-25",
            scenarios=["custom"],
            custom_daily_trimp=[{"date": "2026/05/22", "trimp": 40.0}],
            now=datetime.fromisoformat("2026-05-22T09:00:00"),
            signal_first_use=False,
            connection=conn_invalid,
        )
    with pytest.raises(ValueError):
        project_fitness_state_service(
            target_date="2026-05-25",
            scenarios=["custom"],
            custom_daily_trimp=[{"date": "2026-05-21", "trimp": 40.0}],
            now=datetime.fromisoformat("2026-05-22T09:00:00"),
            signal_first_use=False,
            connection=conn_invalid,
        )
    with pytest.raises(ValueError):
        project_fitness_state_service(
            target_date="2026-05-25",
            scenarios=["custom"],
            custom_daily_trimp=[{"date": "2026-05-22", "trimp": -1.0}],
            now=datetime.fromisoformat("2026-05-22T09:00:00"),
            signal_first_use=False,
            connection=conn_invalid,
        )
    with pytest.raises(ValueError, match="rows must include date and trimp"):
        project_fitness_state_service(
            target_date="2026-05-25",
            scenarios=["custom"],
            custom_daily_trimp=[{"trimp": 40.0}],
            now=datetime.fromisoformat("2026-05-22T09:00:00"),
            signal_first_use=False,
            connection=conn_invalid,
        )
    with pytest.raises(ValueError, match="rows must include date and trimp"):
        project_fitness_state_service(
            target_date="2026-05-25",
            scenarios=["custom"],
            custom_daily_trimp=["2026-05-22"],
            now=datetime.fromisoformat("2026-05-22T09:00:00"),
            signal_first_use=False,
            connection=conn_invalid,
        )
    conn_invalid.close()


def test_list_workouts_service_validates_limit(tmp_path: Path) -> None:
    from mcp_strava.application.metric_services import list_workouts_service

    conn = _fixture_conn(tmp_path / "limit.db")
    try:
        for limit in (0, -1, 201):
            with pytest.raises(ValueError, match="limit must be between 1 and 200"):
                list_workouts_service(
                    limit=limit,
                    now=datetime.fromisoformat("2026-05-22T09:00:00"),
                    signal_first_use=False,
                    connection=conn,
                )
        with pytest.raises(ValueError, match="limit must be an integer"):
            list_workouts_service(
                limit=1.5,
                now=datetime.fromisoformat("2026-05-22T09:00:00"),
                signal_first_use=False,
                connection=conn,
            )
    finally:
        conn.close()
