"""Materialized fact-column registry validation and SQL helpers."""

from __future__ import annotations

import re

from mcp_strava.metric_registry_fact_column_model import (
    FACT_COLUMN_ROLES,
    MATERIALIZED_FACT_TABLES,
    FactColumnDefinition,
)
from mcp_strava.metric_registry_fact_column_projection import AGGREGATE_QUERY_PROJECTION_COLUMNS
from mcp_strava.metric_registry_fact_column_sql import (
    _MATERIALIZED_FACT_COLUMN_SQL_METADATA,
    _SUPPORTED_FACT_DEFAULT_SQL,
    _SUPPORTED_FACT_SQL_TYPES,
)
from mcp_strava.metric_registry_fact_column_tables import MATERIALIZED_FACT_COLUMN_REGISTRY
from mcp_strava.metric_registry_metrics import METRIC_REGISTRY

__all__ = [
    "AGGREGATE_QUERY_PROJECTION_COLUMNS",
    "FACT_COLUMN_ROLES",
    "MATERIALIZED_FACT_COLUMN_REGISTRY",
    "MATERIALIZED_FACT_TABLES",
    "FactColumnDefinition",
    "activity_metric_facts_table_sql",
    "aggregate_query_allowed_columns",
    "materialized_fact_column_definition",
    "materialized_fact_column_definition_sql",
    "materialized_fact_column_names",
]

_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_sql_identifier(identifier: str) -> None:
    if not _SQL_IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")


def _validate_fact_column_sql_metadata(definition: FactColumnDefinition) -> None:
    _validate_sql_identifier(definition.table_name)
    _validate_sql_identifier(definition.column_name)
    if not definition.sql_type:
        raise ValueError(f"{definition.table_name}.{definition.column_name} missing sql_type")
    if definition.sql_type not in _SUPPORTED_FACT_SQL_TYPES:
        raise ValueError(
            f"{definition.table_name}.{definition.column_name} has unsupported sql_type: {definition.sql_type}"
        )
    if definition.default_sql is not None and definition.default_sql not in _SUPPORTED_FACT_DEFAULT_SQL:
        raise ValueError(
            f"{definition.table_name}.{definition.column_name} has unsafe default_sql: {definition.default_sql}"
        )


def _validate_registry_table_set() -> None:
    unknown_tables = set(MATERIALIZED_FACT_COLUMN_REGISTRY) - set(MATERIALIZED_FACT_TABLES)
    if unknown_tables:
        raise ValueError(f"Unknown materialized fact tables: {sorted(unknown_tables)}")
    missing_tables = set(MATERIALIZED_FACT_TABLES) - set(MATERIALIZED_FACT_COLUMN_REGISTRY)
    if missing_tables:
        raise ValueError(f"Missing materialized fact table registries: {sorted(missing_tables)}")
    unknown_metadata_tables = set(_MATERIALIZED_FACT_COLUMN_SQL_METADATA) - set(MATERIALIZED_FACT_COLUMN_REGISTRY)
    if unknown_metadata_tables:
        raise ValueError(f"Unknown materialized fact SQL metadata tables: {sorted(unknown_metadata_tables)}")


def _validate_table_columns(table_name: str, columns: dict) -> None:
    metadata_columns = set(_MATERIALIZED_FACT_COLUMN_SQL_METADATA.get(table_name, {}))
    unknown_metadata_columns = metadata_columns - set(columns)
    if unknown_metadata_columns:
        raise ValueError(f"{table_name} has SQL metadata for unknown columns: {sorted(unknown_metadata_columns)}")
    for column_name, definition in columns.items():
        if definition.table_name != table_name or definition.column_name != column_name:
            raise ValueError(f"Fact column key mismatch: {table_name}.{column_name}")
        _validate_fact_column_sql_metadata(definition)
        unknown_metric_ids = set(definition.metric_ids) - set(METRIC_REGISTRY)
        if unknown_metric_ids:
            raise ValueError(f"{table_name}.{column_name} references unknown metrics: {sorted(unknown_metric_ids)}")


def _validate_aggregate_projection_columns() -> None:
    for column_name, definition in AGGREGATE_QUERY_PROJECTION_COLUMNS.items():
        if definition.column_name != column_name:
            raise ValueError(f"Aggregate projection key mismatch: {column_name}")
        unknown_metric_ids = set(definition.metric_ids) - set(METRIC_REGISTRY)
        if unknown_metric_ids:
            raise ValueError(f"{column_name} references unknown metrics: {sorted(unknown_metric_ids)}")


def _validate_fact_column_registry() -> None:
    _validate_registry_table_set()
    for table_name, columns in MATERIALIZED_FACT_COLUMN_REGISTRY.items():
        _validate_table_columns(table_name, columns)
    _validate_aggregate_projection_columns()


_validate_fact_column_registry()


def materialized_fact_column_names(table_name: str) -> frozenset[str]:
    if table_name not in MATERIALIZED_FACT_COLUMN_REGISTRY:
        raise ValueError(f"Unknown materialized fact table: {table_name}")
    return frozenset(MATERIALIZED_FACT_COLUMN_REGISTRY[table_name])


def materialized_fact_column_definition(table_name: str, column_name: str) -> FactColumnDefinition:
    if table_name not in MATERIALIZED_FACT_COLUMN_REGISTRY:
        raise ValueError(f"Unknown materialized fact table: {table_name}")
    if column_name not in MATERIALIZED_FACT_COLUMN_REGISTRY[table_name]:
        raise ValueError(f"Unknown materialized fact column: {table_name}.{column_name}")
    return MATERIALIZED_FACT_COLUMN_REGISTRY[table_name][column_name]


def materialized_fact_column_definition_sql(table_name: str, column_name: str) -> str:
    definition = materialized_fact_column_definition(table_name, column_name)
    parts = [definition.column_name, definition.sql_type]
    if not definition.nullable:
        parts.append("NOT NULL")
    if definition.default_sql is not None:
        parts.extend(("DEFAULT", definition.default_sql))
    return " ".join(parts)


def activity_metric_facts_table_sql() -> str:
    columns = [
        f"    {materialized_fact_column_definition_sql('activity_metric_facts', column_name)}"
        for column_name in MATERIALIZED_FACT_COLUMN_REGISTRY["activity_metric_facts"]
    ]
    columns.append("    PRIMARY KEY (activity_id, metric_version)")
    return "CREATE TABLE activity_metric_facts (\n" + ",\n".join(columns) + "\n);"


def aggregate_query_allowed_columns() -> frozenset[str]:
    columns: set[str] = set(AGGREGATE_QUERY_PROJECTION_COLUMNS)
    for table in MATERIALIZED_FACT_COLUMN_REGISTRY.values():
        columns.update(
            column_name for column_name, definition in table.items() if definition.role in {"metric", "dependency"}
        )
    return frozenset(columns)
