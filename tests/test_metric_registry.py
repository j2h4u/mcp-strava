"""Metric registry contract tests for Phase 05 plan 05-01."""

import duckdb
import pytest

from mcp_strava.adapters.duckdb import schema
from mcp_strava.adapters.duckdb.schema import DUCKDB_TABLES, DUCKDB_VIEWS, create_schema
from mcp_strava.metric_registry import (
    AGGREGATE_BUCKET_INTERVALS,
    AGGREGATE_METRIC_BUNDLES,
    AGGREGATE_MODES,
    EXCLUDED_INTERPRETATIONS,
    MATERIALIZED_FACT_COLUMN_REGISTRY,
    MATERIALIZED_FACT_TABLES,
    MATERIALIZED_ROLLING_WINDOW_DAYS,
    MCP_TOOL_IDS,
    METRIC_REGISTRY,
    SUPPORTED_AGGREGATE_BUCKETS,
    SUPPORTED_AGGREGATE_SCOPES,
    SUPPORTED_ROLLING_WINDOW_DAYS,
    aggregate_query_allowed_columns,
    materialized_fact_column_names,
    metric_catalog_payload,
    metrics_for_aggregate_bundle,
    metrics_for_tool,
)

REQUIRED_METRIC_IDS = {
    "activity_id",
    "activity_date",
    "sport_type",
    "activity_name",
    "kudos_count",
    "kudos_names",
    "gear_id",
    "gear_name",
    "gear_distance_km",
    "gear_primary",
    "distance_km",
    "moving_time_min",
    "elapsed_time_min",
    "elevation_m",
    "start_time_local",
    "relative_time",
    "trimp",
    "avg_hr",
    "max_hr",
    "time_in_hr_zones_min",
    "hr_recovery_pauses",
    "hr_recovery_total_rest_sec",
    "hr_recovery_median_bpm_per_min",
    "hr_recovery_best_bpm_per_min",
    "hr_recovery_worst_bpm_per_min",
    "hr_recovery_avg_bpm_per_min",
    "vertical_speed_m_per_h",
    "vertical_ascent_m",
    "vertical_duration_h",
    "cardiac_cost",
    "cardiac_cost_adjusted",
    "cardiac_drift_pct",
    "cardiac_drift_severity",
    "cardiac_drift_significant",
    "cardiac_drift_quality",
    "hrr_pct",
    "hr_anomaly_count",
    "daily_trimp",
    "total_trimp_14d",
    "avg_trimp_per_day",
    "active_days",
    "rest_days",
    "weekly_trimp",
    "by_sport_trimp",
    "by_sport_distance_km",
    "by_sport_time_min",
    "by_sport_elevation_m",
    "fitness",
    "fatigue",
    "form",
    "form_zone",
    "banister_history",
    "acwr",
    "acwr_zone",
    "acwr_history",
    "daily_avg_trimp_7d",
    "daily_avg_trimp_28d",
    "daily_avg_trimp_90d",
    "rolling_median_cc",
    "rolling_median_cc_adj",
    "rolling_median_epkm",
    "rolling_median_hr_recovery",
    "rolling_median_cardiac_drift_pct",
    "volume_7d",
    "volume_28d",
    "load_trend_pct",
    "efficiency_trend_pct",
    "run_90d_median_cc_trend_pct",
    "activity_streak_days",
    "rest_streak_days",
    "last_hike_days_ago",
    "progressive_load_bonus",
    "progressive_cc_trends",
    "projected_daily_trimp",
    "projected_fitness",
    "projected_fatigue",
    "projected_form",
    "target_date_form",
    "post_weekend_monday_form",
    "activity_template_trimp",
}

FORBIDDEN_METRIC_IDS = {
    "z5_seconds",
    "atl",
    "ctl",
}

ALLOWED_SPORT_SCOPE = {"global", "per_sport", "both"}
ALLOWED_COMPARISON_MODE = {"sum", "avg", "median", "last", "min", "max", "trend", "distribution", "none"}
EXPECTED_AGGREGATE_MODES = {
    "sum",
    "calendar_average",
    "weighted_average",
    "ratio_of_sums",
    "quantile",
    "last_state",
    "distribution",
    "kudos_count",
}
EXPECTED_AGGREGATE_BUCKETS = {"day", "week", "month", "year", "all_time"}
EXPECTED_AGGREGATE_SCOPES = {"global", "per_sport", "both"}
EXPECTED_ROLLING_WINDOWS = {7, 14, 28, 42, 90}
EXPECTED_AGGREGATE_BUNDLES = {
    "daily_brief",
    "weekly_digest",
    "monthly_digest",
    "period_comparison",
    "sport_efficiency",
    "historical_facts",
}
EXPECTED_QUANTILES = ("p25", "median", "p75")
EXPECTED_STATUS_FACT_CODES = {
    "stale_mirror_data",
    "stale_read_model_facts",
    "missing_hr",
    "missing_streams",
    "excessive_z5_exposure",
    "hr_anomaly_burst",
    "cardiac_drift_significant_quality",
    "consecutive_high_load_hikes",
    "running_volume_jump",
}
EXPECTED_GEAR_FACT_METRICS = {
    "gear_id",
    "gear_name",
    "gear_distance_km",
    "gear_primary",
}
ALLOWED_TOOLS = {
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
    "get_training_aggregates",
}


def test_registry_covers_required_metric_ids():
    missing = REQUIRED_METRIC_IDS - set(METRIC_REGISTRY.keys())
    assert not missing, f"Missing required metric ids: {sorted(missing)}"


def test_registry_rejects_duplicate_or_placeholder_metric_ids():
    assert METRIC_REGISTRY.keys().isdisjoint(FORBIDDEN_METRIC_IDS)


def test_registry_entries_have_required_metadata():
    for metric in METRIC_REGISTRY.values():
        assert metric.metric_id
        assert metric.unit
        assert metric.source
        assert metric.scope
        assert metric.sport_scope
        assert metric.comparison_mode
        assert metric.directionality
        assert metric.requirements
        assert metric.missing_reasons
        assert metric.calculation


def test_registry_entry_enums_and_tool_allowlist():
    for metric in METRIC_REGISTRY.values():
        assert metric.sport_scope in ALLOWED_SPORT_SCOPE
        assert metric.comparison_mode in ALLOWED_COMPARISON_MODE
        unknown_tools = set(metric.exposed_in) - ALLOWED_TOOLS
        assert not unknown_tools, f"{metric.metric_id} has unknown tool ids: {sorted(unknown_tools)}"

    assert set(MCP_TOOL_IDS) == ALLOWED_TOOLS


def test_excluded_interpretations_map_to_preserved_numeric_facts():
    required_exclusions = {
        "recommendation.action",
        "recommendation.intensity",
        "recommendation.confidence",
        "weekly_plan.on_track",
        "weekly_plan.plan_days.activity",
        "safety_warnings.text",
    }
    missing = required_exclusions - set(EXCLUDED_INTERPRETATIONS.keys())
    assert not missing, f"Missing interpretation exclusions: {sorted(missing)}"

    for key, exclusion in EXCLUDED_INTERPRETATIONS.items():
        assert exclusion.field == key
        assert exclusion.preserved_metric_ids, f"{key} must preserve at least one numeric/model input metric"


def test_unknown_tool_id_is_rejected():
    with pytest.raises(ValueError):
        metrics_for_tool("get_data_status")


def test_registry_entries_describe_calculation_contract():
    banned_placeholders = {"todo", "tbd", "n/a", "unknown"}
    banned_phrases = {
        "reserved",
        "currently returns null",
        "currently not materialized",
        "currently skipped",
        "currently materialized as the same value",
        "not materialized for",
    }
    for metric in METRIC_REGISTRY.values():
        calculation = metric.calculation.strip()
        assert len(calculation) >= 24, f"{metric.metric_id} calculation is too terse"
        assert calculation.lower() not in banned_placeholders
        assert metric.metric_id != calculation, f"{metric.metric_id} repeats its id instead of explaining calculation"
        lowered = calculation.lower()
        assert not any(phrase in lowered for phrase in banned_phrases), metric.metric_id


def test_metric_catalog_payload_exposes_calculation_contracts():
    payload = metric_catalog_payload()
    catalog_metrics = {metric["metric_id"]: metric for metric in payload["metrics"]}
    for metric_id, definition in METRIC_REGISTRY.items():
        assert catalog_metrics[metric_id]["calculation"] == definition.calculation


def test_compare_periods_registry_metrics_resolve_through_aggregate_bundle():
    compare_metrics = {
        metric_id
        for metric_id, definition in METRIC_REGISTRY.items()
        if definition.comparison_mode != "none" and "compare_periods" in definition.exposed_in
    }
    bundle_metrics = set(metrics_for_aggregate_bundle("period_comparison"))

    assert compare_metrics == bundle_metrics
    for metric_id, definition in METRIC_REGISTRY.items():
        if definition.comparison_mode == "none" or "compare_periods" not in definition.exposed_in:
            continue
        assert definition.aggregate_mode is not None, metric_id
        assert definition.aggregate_source, metric_id
        assert definition.sample_size_column, metric_id
        assert definition.metric_version_policy in {"single", "mixed_allowed", "mixed_degraded"}


def test_aggregate_registry_contract_enumerates_supported_modes_and_filters():
    assert set(AGGREGATE_MODES) == EXPECTED_AGGREGATE_MODES
    assert set(SUPPORTED_AGGREGATE_BUCKETS) == EXPECTED_AGGREGATE_BUCKETS
    assert set(AGGREGATE_BUCKET_INTERVALS) == EXPECTED_AGGREGATE_BUCKETS - {"all_time"}
    assert set(SUPPORTED_AGGREGATE_SCOPES) == EXPECTED_AGGREGATE_SCOPES
    assert set(SUPPORTED_ROLLING_WINDOW_DAYS) == EXPECTED_ROLLING_WINDOWS
    assert set(MATERIALIZED_ROLLING_WINDOW_DAYS) == EXPECTED_ROLLING_WINDOWS


def test_materialized_fact_column_registry_matches_duckdb_schema():
    with duckdb.connect(database=":memory:") as conn:
        create_schema(conn)
        for table_name in MATERIALIZED_FACT_TABLES:
            rows = conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = ?
                ORDER BY ordinal_position
                """,
                [table_name],
            ).fetchall()
            schema_columns = {str(row[0]) for row in rows}
            assert schema_columns == set(materialized_fact_column_names(table_name)), table_name


def test_activity_metric_fact_schema_matches_registry_metadata():
    with duckdb.connect(database=":memory:") as conn:
        create_schema(conn)
        rows = conn.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'activity_metric_facts'
            ORDER BY ordinal_position
            """
        ).fetchall()
        schema_columns = {
            str(name): {
                "data_type": str(data_type),
                "nullable": str(is_nullable) == "YES",
                "default_sql": default_sql,
            }
            for name, data_type, is_nullable, default_sql in rows
        }
        registry_columns = MATERIALIZED_FACT_COLUMN_REGISTRY["activity_metric_facts"]

        assert list(schema_columns) == list(registry_columns)
        for column_name in (
            "activity_id",
            "activity_day",
            "zone1_seconds",
            "cardiac_drift_significant",
            "anomaly_count",
            "heartrate_sample_count",
            "calories_kcal",
        ):
            registry_column = registry_columns[column_name]
            schema_column = schema_columns[column_name]
            assert schema_column["data_type"] == registry_column.sql_type
            assert schema_column["nullable"] is registry_column.nullable
            assert schema_column["default_sql"] == registry_column.default_sql

        # VARCHAR[] DEFAULT [] — DuckDB normalises the array literal to main.list_value()
        # in information_schema; verify type and nullability only (not the repr).
        mrj_registry = registry_columns["missing_reasons_json"]
        mrj_schema = schema_columns["missing_reasons_json"]
        assert mrj_schema["data_type"] == mrj_registry.sql_type  # VARCHAR[]
        assert mrj_schema["nullable"] is mrj_registry.nullable  # NOT NULL

        primary_key_columns = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_name = 'activity_metric_facts'
                  AND tc.constraint_type = 'PRIMARY KEY'
                ORDER BY kcu.ordinal_position
                """
            ).fetchall()
        ]
        assert primary_key_columns == ["activity_id", "metric_version"]


def test_duckdb_schema_smoke_keeps_tables_views_and_nonduplicative_indexes():
    with duckdb.connect(database=":memory:") as conn:
        create_schema(conn)
        table_names = {
            str(row[0])
            for row in conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                  AND table_type = 'BASE TABLE'
                """
            ).fetchall()
        }
        view_names = {
            str(row[0])
            for row in conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                  AND table_type = 'VIEW'
                """
            ).fetchall()
        }
        index_names = {str(row[4]) for row in conn.execute("SELECT * FROM duckdb_indexes()").fetchall()}

    assert set(DUCKDB_TABLES).issubset(table_names)
    assert set(DUCKDB_VIEWS).issubset(view_names)
    assert "idx_duckdb_activities_day_id" in index_names
    assert "idx_duckdb_activity_metric_day_sport_version" not in index_names
    assert "idx_duckdb_daily_load_day_scope_sport_version" not in index_names
    assert "idx_duckdb_training_model_day_scope_sport_version" not in index_names
    assert "idx_duckdb_rolling_period_asof_window_scope_sport_version" not in index_names


def test_schema_activity_metric_fact_ddl_is_registry_generated():
    from mcp_strava.metric_registry import activity_metric_facts_table_sql

    assert schema.activity_metric_facts_table_sql is activity_metric_facts_table_sql
    generated_table_sql = activity_metric_facts_table_sql()
    assert generated_table_sql in schema.DUCKDB_SCHEMA_SQL
    assert schema.DUCKDB_SCHEMA_SQL.count(generated_table_sql) == 1


def test_materialized_fact_column_registry_has_sql_metadata():
    for table_name, columns in MATERIALIZED_FACT_COLUMN_REGISTRY.items():
        for column in columns.values():
            assert column.sql_type, f"{table_name}.{column.column_name} missing sql_type"


def test_fact_column_sql_metadata_rejects_unsafe_fragments_before_rendering():
    from mcp_strava.metric_registry import FactColumnDefinition, _validate_fact_column_sql_metadata

    def definition(**overrides):
        values = {
            "table_name": "activity_metric_facts",
            "column_name": "calories_kcal",
            "role": "metric",
            "sql_type": "DOUBLE",
        }
        values.update(overrides)
        return FactColumnDefinition(**values)

    cases = (
        (definition(table_name="activity_metric_facts; DROP TABLE activities"), "Unsafe SQL identifier"),
        (definition(column_name="calories-kcal"), "Unsafe SQL identifier"),
        (definition(sql_type="INTEGER"), "unsupported sql_type"),
        (definition(default_sql="CURRENT_TIMESTAMP"), "unsafe default_sql"),
    )
    for column, match in cases:
        with pytest.raises(ValueError, match=match):
            _validate_fact_column_sql_metadata(column)


def test_activity_metric_facts_generated_sql_matches_current_contract():
    from mcp_strava.metric_registry import (
        activity_metric_facts_table_sql,
        materialized_fact_column_definition_sql,
    )

    assert (
        materialized_fact_column_definition_sql("activity_metric_facts", "activity_id") == "activity_id BIGINT NOT NULL"
    )
    assert (
        materialized_fact_column_definition_sql("activity_metric_facts", "activity_day") == "activity_day DATE NOT NULL"
    )
    assert (
        materialized_fact_column_definition_sql("activity_metric_facts", "missing_reasons_json")
        == "missing_reasons_json VARCHAR[] NOT NULL DEFAULT []"
    )
    assert (
        materialized_fact_column_definition_sql("activity_metric_facts", "zone1_seconds")
        == "zone1_seconds BIGINT NOT NULL DEFAULT 0"
    )
    assert materialized_fact_column_definition_sql("activity_metric_facts", "calories_kcal") == ("calories_kcal DOUBLE")

    ddl = activity_metric_facts_table_sql()
    assert ddl.startswith("CREATE TABLE activity_metric_facts (")
    assert "    PRIMARY KEY (activity_id, metric_version)" in ddl
    assert ddl.rstrip().endswith(");")


def test_fact_column_registry_has_known_roles_and_metric_refs():
    allowed_roles = {"dimension", "metric", "dependency", "provenance"}
    for table_name, columns in MATERIALIZED_FACT_COLUMN_REGISTRY.items():
        assert table_name in MATERIALIZED_FACT_TABLES
        assert columns, table_name
        for column in columns.values():
            assert column.role in allowed_roles, f"{table_name}.{column.column_name}"
            assert set(column.metric_ids).issubset(METRIC_REGISTRY), f"{table_name}.{column.column_name}"
            if column.role == "metric":
                assert column.metric_ids, f"{table_name}.{column.column_name} must point to a metric"


def test_aggregate_query_columns_are_registry_derived():
    from mcp_strava.adapters.duckdb import aggregate_sql_expressions

    allowed_columns = aggregate_query_allowed_columns()
    assert allowed_columns == aggregate_sql_expressions._ALLOWED_COLUMNS
    assert "zone1_seconds" in allowed_columns
    assert "source_hash" not in allowed_columns
    assert "computed_at" not in allowed_columns


def test_materializers_use_registry_rolling_windows():
    from mcp_strava.adapters.duckdb.read_model_materializer import ROLLING_WINDOWS as duckdb_windows

    assert duckdb_windows == MATERIALIZED_ROLLING_WINDOW_DAYS


def test_aggregate_exposed_metrics_have_complete_query_metadata():
    aggregate_metrics = [metric for metric in METRIC_REGISTRY.values() if metric.aggregate_mode is not None]
    assert aggregate_metrics, "get_training_aggregates must have registry-owned metrics"

    for metric in aggregate_metrics:
        assert metric.unit
        assert metric.calculation
        assert metric.aggregate_mode in EXPECTED_AGGREGATE_MODES
        assert metric.aggregate_source
        assert metric.metric_version_policy in {"single", "mixed_allowed", "mixed_degraded"}
        assert set(metric.supported_buckets).issubset(EXPECTED_AGGREGATE_BUCKETS)
        assert metric.supported_buckets, f"{metric.metric_id} must declare aggregate buckets"
        assert set(metric.supported_scopes).issubset(EXPECTED_AGGREGATE_SCOPES)
        assert metric.supported_scopes, f"{metric.metric_id} must declare aggregate scopes"
        assert not set(metric.supported_scopes) & {"gear", "equipment"}
        assert metric.sample_size_column, f"{metric.metric_id} must expose sample-size provenance"


def test_aggregate_modes_map_locked_semantic_decisions():
    expected_modes = {
        "distance_km": ("sum", "distance_m"),
        "moving_time_min": ("sum", "moving_time_s"),
        "elevation_m": ("sum", "elevation_gain_m"),
        "trimp": ("sum", "trimp"),
        "avg_trimp_per_day": ("calendar_average", "calendar_days"),
        "avg_hr": ("weighted_average", "heartrate_sample_count"),
        "vertical_speed_m_per_h": ("ratio_of_sums", "vertical_speed_duration_hours"),
        "cardiac_cost": ("quantile", None),
        "fitness": ("last_state", None),
        "form_zone": ("distribution", None),
        "kudos_count": ("kudos_count", "activity_count"),
        "volume_7d": ("last_state", "latest_day"),
        "volume_28d": ("last_state", "latest_day"),
    }
    for metric_id, (mode, denominator) in expected_modes.items():
        metric = METRIC_REGISTRY[metric_id]
        assert metric.aggregate_mode == mode, metric_id
        if denominator is not None:
            assert metric.denominator == denominator or metric.denominator_column == denominator, metric_id


def test_weighted_hr_and_power_metrics_require_explicit_denominators():
    weighted_metrics = [
        metric
        for metric in METRIC_REGISTRY.values()
        if metric.aggregate_mode == "weighted_average" or metric.unit in {"bpm", "watts"}
    ]
    assert weighted_metrics
    for metric in weighted_metrics:
        assert metric.weight_column, metric.metric_id
        assert metric.denominator_column, metric.metric_id
        assert metric.denominator != "naive_activity_average", metric.metric_id


def test_quantile_metrics_require_distribution_context_and_sample_size():
    quantile_metrics = [metric for metric in METRIC_REGISTRY.values() if metric.aggregate_mode == "quantile"]
    assert quantile_metrics
    for metric in quantile_metrics:
        assert tuple(metric.quantiles) == EXPECTED_QUANTILES, metric.metric_id
        assert metric.sample_size_column, metric.metric_id
        assert "sample" in metric.sample_size_column, metric.metric_id


def test_aggregate_bundles_resolve_only_known_metric_ids():
    assert set(AGGREGATE_METRIC_BUNDLES) == EXPECTED_AGGREGATE_BUNDLES
    for bundle_id, metric_ids in AGGREGATE_METRIC_BUNDLES.items():
        assert metric_ids, f"{bundle_id} bundle must not be empty"
        assert set(metrics_for_aggregate_bundle(bundle_id)) == set(metric_ids)
        unknown = set(metric_ids) - set(METRIC_REGISTRY)
        assert not unknown, f"{bundle_id} has unknown metric ids: {sorted(unknown)}"
        for metric_id in metric_ids:
            metric = METRIC_REGISTRY[metric_id]
            assert metric.aggregate_mode is not None, metric_id
            assert bundle_id in metric.bundle_ids, metric_id

    with pytest.raises(ValueError):
        metrics_for_aggregate_bundle("gear_efficiency")


def test_aggregate_registry_does_not_create_pseudo_metric_ids_for_math_variants():
    forbidden_suffixes = (
        "_sum",
        "_weighted_avg",
        "_weighted_average",
        "_ratio_sum",
        "_ratio_of_sums",
        "_quantile",
        "_p25",
        "_p75",
        "_last_state",
    )
    offenders = [metric_id for metric_id in METRIC_REGISTRY if metric_id.endswith(forbidden_suffixes)]
    assert not offenders


def test_kudos_aggregate_excludes_kudos_names():
    assert METRIC_REGISTRY["kudos_count"].aggregate_mode == "kudos_count"
    assert METRIC_REGISTRY["kudos_names"].aggregate_mode is None
    for metric_ids in AGGREGATE_METRIC_BUNDLES.values():
        assert "kudos_names" not in metric_ids


def test_phase9_status_fact_registry_is_machine_readable():
    from mcp_strava.metric_registry import STATUS_FACT_REGISTRY

    assert set(STATUS_FACT_REGISTRY) == EXPECTED_STATUS_FACT_CODES
    for code, definition in STATUS_FACT_REGISTRY.items():
        assert definition.code == code
        assert definition.metric_id in METRIC_REGISTRY
        assert definition.threshold, code
        assert definition.window, code
        assert definition.evidence_keys, code
        assert definition.completeness_reasons, code
        assert len(definition.calculation) >= 24, code
        assert definition.materialized_from, code
        assert "recommend" not in definition.calculation.lower()
        assert "should" not in definition.calculation.lower()


def test_phase9_gear_facts_are_registered_context_not_aggregate_filters():
    for metric_id in EXPECTED_GEAR_FACT_METRICS:
        metric = METRIC_REGISTRY[metric_id]
        assert metric.aggregate_mode is None
        assert "get_workout_detail" in metric.exposed_in
        assert "get_training_aggregates" not in metric.exposed_in
        assert metric.metric_id not in {
            bundle_metric for metric_ids in AGGREGATE_METRIC_BUNDLES.values() for bundle_metric in metric_ids
        }
