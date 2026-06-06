"""Fact-column model and definition factory."""

from __future__ import annotations

from dataclasses import dataclass

from mcp_strava.metric_registry_fact_column_sql import _MATERIALIZED_FACT_COLUMN_SQL_METADATA

FACT_COLUMN_ROLES = ("dimension", "metric", "dependency", "provenance")


MATERIALIZED_FACT_TABLES = (
    "activity_metric_facts",
    "daily_load_facts",
    "training_model_daily",
    "rolling_period_facts",
)


@dataclass(frozen=True)
class FactColumnDefinition:
    """Registry entry for a materialized analytic fact-table column."""

    table_name: str
    column_name: str
    role: str
    metric_ids: tuple[str, ...] = ()
    description: str = ""
    sql_type: str = ""
    nullable: bool = True
    default_sql: str | None = None


def _fact_column(
    table_name: str,
    column_name: str,
    role: str,
    metric_ids: tuple[str, ...] = (),
    description: str = "",
) -> FactColumnDefinition:
    if role not in FACT_COLUMN_ROLES:
        raise ValueError(f"Unknown fact column role: {role}")
    sql_type, nullable, default_sql = _MATERIALIZED_FACT_COLUMN_SQL_METADATA.get(table_name, {}).get(
        column_name, ("", True, None)
    )
    return FactColumnDefinition(
        table_name=table_name,
        column_name=column_name,
        role=role,
        metric_ids=metric_ids,
        description=description,
        sql_type=sql_type,
        nullable=nullable,
        default_sql=default_sql,
    )


def _fact_table(
    table_name: str, columns: tuple[tuple[str, str, tuple[str, ...], str], ...]
) -> dict[str, FactColumnDefinition]:
    return {
        column_name: _fact_column(table_name, column_name, role, metric_ids, description)
        for column_name, role, metric_ids, description in columns
    }
