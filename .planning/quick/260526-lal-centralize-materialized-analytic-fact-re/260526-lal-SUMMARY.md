---
quick_id: 260526-lal
slug: centralize-materialized-analytic-fact-re
status: complete
completed_at: "2026-05-26T15:30:15+05:00"
---

# Summary

Centralized the materialized analytic fact contract behind the metric registry.

## Completed

- Added a materialized fact column registry for read-model fact tables, with each column classified as `dimension`, `metric`, `dependency`, or `provenance`.
- Derived the DuckDB aggregate query allowlist from that registry instead of maintaining a second private set.
- Centralized materialized rolling windows and wired both DuckDB and SQLite materializers to that shared contract.
- Added drift tests comparing DuckDB fact-table schema columns and materializer windows to the registry.

## Verification

- `uv run pytest -q tests/test_metric_registry.py tests/test_read_model_materialization.py tests/test_read_model_queries.py tests/test_training_aggregates.py` -> 63 passed.
- `uv run pytest -q` -> 332 passed, 1 skipped.
- `just test` -> Docker build, healthy container, basic direct MCP smoke passed.
- `just mcp-smoke-full` -> all six product MCP tools called successfully.
