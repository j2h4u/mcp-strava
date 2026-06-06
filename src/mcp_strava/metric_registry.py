"""Core metric registry contract.

The registry inventories every Strava-sourced, calculated, or deliberately
derived metric. MCP tools expose filtered subsets through ``exposed_in``.
"""

from __future__ import annotations

import hashlib
import inspect
from importlib import import_module
from typing import Any

from mcp_strava.metric_registry_aggregates import AGGREGATE_METRIC_BUNDLES
from mcp_strava.metric_registry_fact_columns import (
    AGGREGATE_QUERY_PROJECTION_COLUMNS,
    FACT_COLUMN_ROLES,
    MATERIALIZED_FACT_COLUMN_REGISTRY,
    MATERIALIZED_FACT_TABLES,
    FactColumnDefinition,
    _validate_fact_column_registry,
    _validate_fact_column_sql_metadata,
    activity_metric_facts_table_sql,
    aggregate_query_allowed_columns,
    materialized_fact_column_definition,
    materialized_fact_column_definition_sql,
    materialized_fact_column_names,
)
from mcp_strava.metric_registry_metrics import METRIC_REGISTRY
from mcp_strava.metric_registry_shared import (
    AGGREGATE_BUCKET_INTERVALS,
    AGGREGATE_MODES,
    DEFAULT_AGGREGATE_QUANTILES,
    MATERIALIZED_ROLLING_WINDOW_DAYS,
    MCP_TOOL_IDS,
    SUPPORTED_AGGREGATE_BUCKETS,
    SUPPORTED_AGGREGATE_SCOPES,
    SUPPORTED_ROLLING_WINDOW_DAYS,
)
from mcp_strava.metric_registry_status import EXCLUDED_INTERPRETATIONS, STATUS_FACT_REGISTRY
from mcp_strava.types import MetricDefinition

__all__ = [
    "AGGREGATE_BUCKET_INTERVALS",
    "AGGREGATE_METRIC_BUNDLES",
    "AGGREGATE_MODES",
    "AGGREGATE_QUERY_PROJECTION_COLUMNS",
    "COMPUTE_SOURCE_MODULES",
    "DEFAULT_AGGREGATE_QUANTILES",
    "EXCLUDED_INTERPRETATIONS",
    "FACT_COLUMN_ROLES",
    "MATERIALIZED_FACT_COLUMN_REGISTRY",
    "MATERIALIZED_FACT_TABLES",
    "MATERIALIZED_ROLLING_WINDOW_DAYS",
    "MCP_TOOL_IDS",
    "METRIC_REGISTRY",
    "STATUS_FACT_REGISTRY",
    "SUPPORTED_AGGREGATE_BUCKETS",
    "SUPPORTED_AGGREGATE_SCOPES",
    "SUPPORTED_ROLLING_WINDOW_DAYS",
    "FactColumnDefinition",
    "_validate_fact_column_registry",
    "_validate_fact_column_sql_metadata",
    "activity_metric_facts_table_sql",
    "aggregate_query_allowed_columns",
    "cached_logic_fingerprint",
    "comparable_metrics",
    "compute_logic_fingerprint",
    "materialized_fact_column_definition",
    "materialized_fact_column_definition_sql",
    "materialized_fact_column_names",
    "metric_catalog_payload",
    "metric_definition",
    "metrics_for_aggregate_bundle",
    "metrics_for_tool",
]


def metric_definition(metric_id: str) -> MetricDefinition:
    return METRIC_REGISTRY[metric_id]


def metrics_for_tool(tool_id: str) -> list[MetricDefinition]:
    if tool_id not in MCP_TOOL_IDS:
        raise ValueError(f"Unknown MCP tool id: {tool_id}")
    return sorted(
        [metric for metric in METRIC_REGISTRY.values() if tool_id in metric.exposed_in],
        key=lambda metric: metric.metric_id,
    )


def metrics_for_aggregate_bundle(bundle_id: str) -> tuple[str, ...]:
    if bundle_id not in AGGREGATE_METRIC_BUNDLES:
        raise ValueError(f"Unknown aggregate bundle id: {bundle_id}")
    return AGGREGATE_METRIC_BUNDLES[bundle_id]


def comparable_metrics(scope: str | None = None, sport_scope: str | None = None) -> list[MetricDefinition]:
    metrics = [metric for metric in METRIC_REGISTRY.values() if metric.comparison_mode != "none"]
    if scope is not None:
        metrics = [metric for metric in metrics if metric.scope == scope]
    if sport_scope is not None:
        metrics = [metric for metric in metrics if metric.sport_scope == sport_scope]
    return sorted(metrics, key=lambda metric: metric.metric_id)


def metric_catalog_payload() -> dict[str, Any]:
    return {
        "tool_ids": list(MCP_TOOL_IDS),
        "metrics": [
            {
                "metric_id": metric.metric_id,
                "label": metric.label,
                "unit": metric.unit,
                "source": metric.source,
                "scope": metric.scope,
                "sport_scope": metric.sport_scope,
                "comparison_mode": metric.comparison_mode,
                "directionality": metric.directionality,
                "requirements": metric.requirements,
                "missing_reasons": metric.missing_reasons,
                "exposed_in": metric.exposed_in,
                "calculation": metric.calculation,
                "description": metric.description,
                "aggregate_mode": metric.aggregate_mode,
                "aggregate_source": metric.aggregate_source,
                "denominator": metric.denominator,
                "weight_column": metric.weight_column,
                "numerator_column": metric.numerator_column,
                "denominator_column": metric.denominator_column,
                "value_column": metric.value_column,
                "sample_size_column": metric.sample_size_column,
                "supported_buckets": metric.supported_buckets,
                "supported_scopes": metric.supported_scopes,
                "bundle_ids": metric.bundle_ids,
                "quantiles": metric.quantiles,
                "metric_version_policy": metric.metric_version_policy,
                "rolling_window_days": metric.rolling_window_days,
                "fixed_rolling_window": metric.fixed_rolling_window,
            }
            for metric in sorted(METRIC_REGISTRY.values(), key=lambda metric: metric.metric_id)
        ],
        "aggregate": {
            "modes": list(AGGREGATE_MODES),
            "buckets": list(SUPPORTED_AGGREGATE_BUCKETS),
            "scopes": list(SUPPORTED_AGGREGATE_SCOPES),
            "rolling_window_days": list(SUPPORTED_ROLLING_WINDOW_DAYS),
            "materialized_rolling_window_days": list(MATERIALIZED_ROLLING_WINDOW_DAYS),
            "bundles": {
                bundle_id: list(metric_ids) for bundle_id, metric_ids in sorted(AGGREGATE_METRIC_BUNDLES.items())
            },
        },
        "status_facts": [
            {
                "code": definition.code,
                "metric_id": definition.metric_id,
                "threshold": definition.threshold,
                "window": definition.window,
                "evidence_keys": definition.evidence_keys,
                "completeness_reasons": definition.completeness_reasons,
                "calculation": definition.calculation,
                "materialized_from": definition.materialized_from,
            }
            for definition in STATUS_FACT_REGISTRY.values()
        ],
        "materialized_fact_columns": {
            table_name: [
                {
                    "column_name": column.column_name,
                    "role": column.role,
                    "metric_ids": list(column.metric_ids),
                    "description": column.description,
                }
                for column in columns.values()
            ]
            for table_name, columns in MATERIALIZED_FACT_COLUMN_REGISTRY.items()
        },
        "aggregate_query_columns": sorted(aggregate_query_allowed_columns()),
        "excluded_interpretations": {
            key: {
                "field": value.field,
                "reason": value.reason,
                "preserved_metric_ids": value.preserved_metric_ids,
            }
            for key, value in EXCLUDED_INTERPRETATIONS.items()
        },
    }


# ═══════════════════════════════════════════════════════════════
#  Source-text logic fingerprint
# ═══════════════════════════════════════════════════════════════
#
# This is the detector that makes the read model self-invalidating. Instead of a
# hand-bumped ``metric_version`` int that someone must remember to advance, the
# fingerprint is derived directly from the *source text* of every module on the
# materializer compute path (a local analog of dbt's ``state:modified``).
#
# COMPUTE_SOURCE_MODULES is the full recursive ``mcp_strava`` import closure of
# ``read_model_materializer`` — i.e. every module whose source participates in
# materializing a fact. Listing the whole closure (not a hand-picked "compute
# only" subset) makes coverage automatic-by-construction: there is no judgment
# call about which modules count, so nothing can silently fall out of scope. The
# completeness test in ``tests/test_logic_fingerprint.py`` recomputes this
# closure and fails loudly if the tuple drifts from it.
COMPUTE_SOURCE_MODULES: tuple[str, ...] = (
    "mcp_strava.adapters.duckdb.activity_lookup_queries",
    "mcp_strava.adapters.duckdb.activity_rows",
    "mcp_strava.adapters.duckdb.connection",
    "mcp_strava.adapters.duckdb.daily_load_queries",
    "mcp_strava.adapters.duckdb.read_model_fact_write_repository",
    "mcp_strava.adapters.duckdb.read_model_logic_repository",
    "mcp_strava.adapters.duckdb.read_model_materializer",
    "mcp_strava.adapters.duckdb.read_model_repository",
    "mcp_strava.adapters.duckdb.read_model_repository_host",
    "mcp_strava.adapters.duckdb.read_model_source_repository",
    "mcp_strava.adapters.duckdb.repository",
    "mcp_strava.adapters.duckdb.repository_models",
    "mcp_strava.adapters.duckdb.repository_utils",
    "mcp_strava.adapters.duckdb.source_hashing",
    "mcp_strava.adapters.duckdb.stream_metric_queries",
    "mcp_strava.adapters.duckdb.stream_write_repository",
    "mcp_strava.adapters.duckdb.trimp_sql",
    "mcp_strava.cardiac_drift",
    "mcp_strava.constants",
    "mcp_strava.hr_zones",
    "mcp_strava.mcp_content",
    "mcp_strava.metric_registry",
    "mcp_strava.metric_registry_aggregates",
    "mcp_strava.metric_registry_fact_columns",
    "mcp_strava.metric_registry_metrics",
    "mcp_strava.metric_registry_shared",
    "mcp_strava.metric_registry_status",
    "mcp_strava.metrics",
    "mcp_strava.settings",
    "mcp_strava.sports",
    "mcp_strava.training",
    "mcp_strava.types",
)


def compute_logic_fingerprint() -> str:
    """Return a deterministic sha256 over the source text of the compute path."""
    digest = hashlib.sha256()
    for module_name in sorted(COMPUTE_SOURCE_MODULES):
        source = inspect.getsource(import_module(module_name))
        digest.update(module_name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(source.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


_live_fingerprint_cache: str | None = None


def cached_logic_fingerprint() -> str:
    """Return the live logic fingerprint, memoized for the process lifetime."""
    global _live_fingerprint_cache
    if _live_fingerprint_cache is None:
        _live_fingerprint_cache = compute_logic_fingerprint()
    return _live_fingerprint_cache
