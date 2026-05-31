# Phase 14 Research - Registry-Owned Fact Schema

## Source Inventory

Phase 14 is the first slice of the broader metric-platform refactor. The current
code already has a materialized fact-column registry in
`src/mcp_strava/metric_registry.py`, but the DuckDB table DDL still lives as a
parallel hand-written block in `src/mcp_strava/adapters/duckdb/schema.py`.

Relevant current files:

- `src/mcp_strava/metric_registry.py`
  - `FactColumnDefinition` currently stores `table_name`, `column_name`, `role`,
    `metric_ids`, and `description`.
  - `MATERIALIZED_FACT_COLUMN_REGISTRY` enumerates all four materialized fact
    tables.
  - `materialized_fact_column_names(table_name)` exposes registry column names.
- `src/mcp_strava/adapters/duckdb/schema.py`
  - `DUCKDB_SCHEMA_SQL` contains a hand-written `CREATE TABLE activity_metric_facts`
    block.
  - `DUCKDB_AGGREGATE_VIEW_SQL` projects `activity_metric_facts` into
    `v_activity_aggregate_facts`.
  - `ensure_provenance_columns()` hand-writes additive `ALTER TABLE` statements
    for late activity fact columns.
- `tests/test_metric_registry.py`
  - `test_materialized_fact_column_registry_matches_duckdb_schema()` only checks
    names from `information_schema.columns`; it catches missing columns but cannot
    make the registry the schema source of truth.

## Confirmed Scope

This phase should deliver only slice 1 from `14-CONTEXT.md`:

1. Add SQL schema metadata to materialized fact-column definitions.
2. Generate the `activity_metric_facts` table DDL from that registry metadata.
3. Generate additive `activity_metric_facts` migration SQL from registry metadata.
4. Keep later slices out of scope:
   - No simple-metric source grammar.
   - No computed-metric DAG/context layer.
   - No per-tool payload generation changes.
   - No `rematerialize-all` command.

## Design Notes

`sql_type` alone is not enough to reproduce the current DDL safely. The table
also carries `NOT NULL`, defaults, and a primary key. The registry should gain
the minimum extra schema metadata needed to generate the exact current
`activity_metric_facts` column definitions:

- `sql_type`: DuckDB SQL type token, such as `BIGINT`, `DOUBLE`, `VARCHAR`, `DATE`.
- `nullable`: whether the column is nullable.
- `default_sql`: optional SQL default expression, for example `'[]'`, `0`, or `0.0`.

The activity table primary key can stay table-level metadata in the DDL generator
instead of being repeated on each column.

For additive migrations, the policy question is which columns are safe to add to
existing DBs. The current late set is:

- `observed_min_hr`
- `observed_max_hr`
- `hr_zone_model`
- `hr_max_used`
- `hr_rest_used`
- `calories_kcal`

The migration policy can remain an explicit allowlist, but the SQL emitted for
those columns should come from registry-owned SQL metadata.

## Verification Strategy

Use temp DuckDB databases only. Do not run live admin commands or mutate
`/opt/docker/mcp-strava/data/strava.duckdb` during planning or execution.

Targeted checks:

- Registry import validates every materialized fact column has SQL metadata.
- Generated `activity_metric_facts` DDL creates the same column names, types,
  nullability, defaults, and primary key as the current hand-written table.
- `ensure_provenance_columns()` can add the current late columns to an older
  fixture table using generated SQL.
- Aggregate/read-model tests still pass after `schema.py` consumes generated DDL.
