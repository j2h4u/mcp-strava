---
phase: "13"
plan: "02"
subsystem: "type-checking"
tags: ["pyright", "type-annotations", "duckdb", "Any", "dict-widening"]
dependency_graph:
  requires: ["13-01"]
  provides: ["D-02 None-guards", "D-04.1 mcp_http import", "D-04.2 connection cast", "D-04.3 client sorted", "dict[str,Any] widening", "0-error pyright baseline"]
  affects: ["all DuckDB row consumers", "preflight", "cli", "metric_services", "mirror_coverage", "freshness"]
tech_stack:
  added: []
  patterns: ["honest-Any at all dict[str,object] boundaries", "assert for structurally-impossible None sites", "explicit type annotation for narrowing"]
key_files:
  created: []
  modified:
    - src/mcp_strava/adapters/duckdb/connection.py
    - src/mcp_strava/adapters/duckdb/repository.py
    - src/mcp_strava/adapters/duckdb/aggregate_queries.py
    - src/mcp_strava/adapters/duckdb/read_model_materializer.py
    - src/mcp_strava/application/aggregate_services.py
    - src/mcp_strava/application/metric_registry.py
    - src/mcp_strava/application/metric_services.py
    - src/mcp_strava/application/mirror_coverage.py
    - src/mcp_strava/application/product_facts.py
    - src/mcp_strava/cli.py
    - src/mcp_strava/deploy/preflight.py
    - src/mcp_strava/devtools/mcp_client/client.py
    - src/mcp_strava/interfaces/mcp_http.py
    - src/mcp_strava/refresh/_sync_ops.py
    - src/mcp_strava/refresh/freshness.py
    - src/mcp_strava/types.py
decisions:
  - "conn: Any in DuckDBRepository (not object) — honest boundary for untyped duckdb Connection"
  - "dict[str, object] → dict[str, Any] across all 16 affected files — consistent with D-01 Row=dict[str,Any] pattern"
  - "assert for structurally-impossible None (COUNT(*) aggregates, post-INSERT fetch, post-guard sites)"
  - "mirror_coverage._count() helper extracts the assert-fetchone[0] pattern for reuse"
  - "cli.py cmd_sql: cursor.description for column names (not fetchall tuple .keys()); cmd_log: dict(zip) with column tuple"
  - "metric_services._distribution_delta: explicit dict[str,Any] annotation on buckets_a/b to help pyright narrow"
  - "freshness.py: local variables for _parse_dt() results — pyright can't narrow across repeated calls"
metrics:
  duration: "30 min"
  completed: "2026-05-30"
  tasks_completed: 1
  files_modified: 16
---

# Phase 13 Plan 02: Pyright Residual Sweep Summary

**One-liner:** Swept all 211 post-Plan-01 pyright errors to 0 by widening `dict[str, object]` → `dict[str, Any]` across 16 files, changing `conn: object` → `conn: Any` in the DuckDB repository, and applying targeted None-guards and one-off D-04 fixes.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Sweep pyright residual to 0 errors — D-02/D-04 + dict[str,Any] | c5fde89 | 16 files |

## What Was Done

**Root cause analysis:** The 211 remaining errors after Plan 01 had two primary sources:

1. `conn: object` in `DuckDBRepository` — all `.execute()`, `.close()`, `.commit()`, `.rollback()` calls on `self.conn` failed pyright because `object` has no such methods. Fix: `conn: Any`.

2. `dict[str, object]` return/parameter annotations throughout the DuckDB adapter and application layers — when `object` values flowed into `int()`, `float()`, subscript operators, `.get()` etc., pyright rejected them. Fix: global replacement of `dict[str, object]` → `dict[str, Any]` across 16 files using sed (consistent with D-01's `Row = dict[str, Any]` pattern).

**D-04 one-offs applied:**
- D-04.1: `mcp_http.py` import changed from `mcp.server.fastmcp.server` (private) to `mcp.server.transport_security` (public)
- D-04.2: `connection.py` `_thread_read_connections()` return type `dict[str, object]` → `dict[str, Any]`; `conn` in `ReadConn.__exit__` already typed as `Any` via the dict
- D-04.3: `client.py` `verify_tool_surface()` set comprehension now filters None via walrus: `{name for tool in tools if isinstance(tool, dict) and (name := tool.get("name")) is not None}`

**D-02 None guards:**
- `repository.py`: `stream_count_for_activity` (COUNT + SUM always returns row), `zone_seconds_for_activity` (SUM always returns row), `get_refresh_state` (post-INSERT fetch is always non-None) — all use `assert row is not None, "..."` 
- `preflight.py:119`: `_count_row = conn.execute(...).fetchone(); assert _count_row is not None` before `int(_count_row[0])`

**D-04.4 additional fixes (per-site as required):**
- `aggregate_queries.py`: `_rows()` returns `list[dict[str, Any]]`; all `dict[str, object]` params widened
- `read_model_materializer.py`: `_median_or_none(values: list[Any])`
- `mirror_coverage.py`: `_count()` helper replaces 6 inline `fetchone()[0]` patterns
- `metric_services.py`: `rolling: dict[int, Any]`, gear dict explicit type annotation, `resolved_id` assert, `_distribution_delta` explicit `dict[str, Any]` vars for `buckets_a`/`buckets_b`, `delta: float | None` annotation with `# type: ignore[arg-type]` for `_is_number`-guarded float conversions
- `cli.py`: `cursor.description` for column names in `cmd_sql`; `dict(zip(..., strict=False))` for `cmd_log` rows; `from typing import Any` added
- `freshness.py`: local variables for `_parse_dt()` calls to enable narrowing

## Verification Results

- `uv run pyright src`: **0 errors, 0 warnings, 0 informations** (down from 211)
- `uv run ruff check src`: all checks passed
- `uv run ruff format src --check`: all formatted
- `uv run pytest tests/ -x -q`: **328 passed** (exit 0)

## Deviations from Plan

**[Rule 2 - Missing coverage] Extended file set beyond plan's `files_modified`**
- Plan listed 4 files; actual sweep touched 16 files
- Reason: the post-Plan-01 residual was larger than anticipated — `dict[str, object]` propagated through the full application layer, not just the 4 expected D-02/D-04 sites
- All changes are within the authorized D-04.4 scope ("extend file set at execution time is parallel-safe")
- Files affected beyond plan frontmatter: `aggregate_queries.py`, `read_model_materializer.py`, `aggregate_services.py`, `metric_registry.py`, `product_facts.py`, `_sync_ops.py`, `types.py`, `freshness.py`, `mirror_coverage.py`, `cli.py`

## Known Stubs

None.

## Threat Flags

None — pure type annotation changes. No new runtime surface, no new network endpoints, no schema changes.

## Self-Check: PASSED

- All 16 modified files verified by `git diff HEAD~1 --name-only`
- Commit c5fde89 exists: `git log --oneline | head -1`
- pyright: 0 errors confirmed
- pytest: 328 passed confirmed
