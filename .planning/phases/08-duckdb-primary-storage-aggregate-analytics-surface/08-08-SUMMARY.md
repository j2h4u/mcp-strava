---
phase: 08-duckdb-primary-storage-aggregate-analytics-surface
plan: 08-08
subsystem: infra
tags: [duckdb, performance, mcp, read-model, connection-pool, latency-gate]

requires:
  - phase: 08-07
    provides: get_training_aggregates MCP tool and six-tool product allowlist
  - phase: 08-04
    provides: DuckDB runtime repository routing and aggregate query layer
provides:
  - Docker-first acceptance evidence for Phase 8 (six-tool smoke + 100 ms p95 gate)
  - Thread-local DuckDB read-connection reuse on the runtime read path
  - Per-call memoization of the read-model schema-existence check
affects: [phase-08, milestone-v1.1, read-model, mcp-surface, performance-gates]

tech-stack:
  added: []
  patterns:
    - Read services reuse one DuckDB connection per (thread, db path) instead of opening per call
    - Process-immutable schema facts are memoized per repository instance, not re-queried per use

key-files:
  created:
    - .planning/phases/08-duckdb-primary-storage-aggregate-analytics-surface/08-08-SUMMARY.md
  modified:
    - src/mcp_strava/db.py
    - src/mcp_strava/application/metric_services.py
    - src/mcp_strava/application/aggregate_services.py
    - src/mcp_strava/application/product_facts.py
    - src/mcp_strava/adapters/duckdb/repository.py
    - tests/conftest.py
    - tests/test_metric_services.py

key-decisions:
  - "Pass the 100 ms p95 gate by lowering the structural read-path floor, not by loosening the gate."
  - "Reuse a thread-local DuckDB read connection per worker thread (matches D-13 per-thread-connection model); only connection lifetime changes, not the in-process RLock or MVCC behaviour."
  - "Memoize _read_model_enabled() per repository instance so read_model_status derives schema existence once per call instead of twice."
  - "Defer the read_model_status envelope redesign (4x DISTINCT scans + per-request recompute) — it is the next lever, tracked but out of scope here."

patterns-established:
  - "ReadConn: thread-local reused read connection, evicted+closed on in-block error, reset per test via autouse fixture."
  - "Structural perf regression guard via call-count assertions (one connect, one schema check) instead of a flaky wall-clock gate."
---

# 08-08: Phase 8 Docker-first acceptance + warm read-path latency fix

## Objective

Close the final Phase 8 acceptance gate. The Docker-first validation tooling,
six-tool smoke, and deployment runbook were already in place from earlier 08-08
work; the milestone was held open solely because the warm `100 ms p95` gate
(`just mcp-read-model-perf 20 2 100`) failed on 2026-05-26:
`get_fitness_state` 100.07 ms, `list_workouts` 118.11 ms, `get_workout_detail`
131.93 ms.

## Root cause

cProfile of the read path (30x `list_workouts`, in-container) showed the
latency was per-call DB plumbing, not analytics:

- `duckdb.connect` + `close` ≈ **28 ms/call** — every MCP tool call opened a
  fresh read-write DuckDB connection.
- ~13 sequential queries/call, several redundant: `_table_exists`
  (`activity_source_state`) ran **twice per call** inside `read_model_status`
  (once directly, once via `_read_model_metadata_versions`).

The fast tools (`compare_periods`, aggregate bundles) only looked fast because
they happened to issue fewer queries; the connection churn was paid by all six.

## Change (decided via critical review — "A + lite-B")

- **A — connection reuse (`src/mcp_strava/db.py`):** new `ReadConn` context
  manager keeps one DuckDB connection per `(thread, db path)` and reuses it
  across calls; evicts+closes the connection if an error occurs inside the
  block; `reset_thread_connections()` for shutdown/tests. Wired into the read
  paths of `metric_services`, `aggregate_services`, and `product_facts`. DuckDB
  caches the DB instance by path in-process, so a persistent reader coexists
  with the refresh writer exactly as the previous open-per-call readers did —
  only connection lifetime changed.
- **lite-B — schema-check memoization (`repository.py`):**
  `_read_model_enabled()` is cached on the per-call repository instance, turning
  the duplicate `activity_source_state` catalog lookup into one. Read-model
  schema is immutable within a process (migrations own DDL), and the read repo
  is short-lived, so there is no staleness window. Dynamic freshness queries
  (`dirty_count`, `last_materialized_at`, refresh state) remain live every call.

## Evidence

Acceptance gates after rebuild/recreate of the Docker runtime on this code:

- **Full test suite:** 301 passed (was 300 + 1 new regression test).
- **`just mcp-read-model-perf 20 2 100`:** overall `status: ok`. Per-tool p95
  across 3 runs on a loaded host (load avg ~2.5):

  | Tool | p95 before (05-26) | p95 now |
  |------|--------------------|---------|
  | get_fitness_state | 100.07 (fail) | 34–35 |
  | list_workouts | 118.11 (fail) | 46–49 |
  | get_workout_detail | 131.93 (fail) | 45–50 |
  | compare_periods | — | 23–28 |
  | project_fitness_state | — | 38–42 |
  | get_training_aggregates (daily_brief / weekly_digest / historical_facts) | — | 20–25 / 77–81 / 18–28 |

  p50 of the formerly-failing tools dropped ~30–40 ms — comfortable headroom,
  not a squeak-past.
- **`just mcp-smoke-full`:** `status: ok` — six product tools + three aggregate
  bundles, no forbidden tools.
- **Docker runtime:** Python 3.14.5, duckdb 1.5.3, DB path
  `/runtime/data/strava.duckdb`.

## Regression guard

`tests/test_metric_services.py::test_read_path_reuses_connection_and_checks_schema_once`
asserts structurally (not by wall clock) that a runtime read opens exactly one
connection (reused on the next read) and checks `activity_source_state` once,
not twice, per call.

## Deferred / next lever

`get_training_aggregates:weekly_digest` (bucket=week) is the slowest remaining
tool at ~77–81 ms p95 — still inside the gate, but it is the heaviest path. The
underlying cost is `read_model_status` recomputing its full envelope on every
product read, including `_read_model_metadata_versions` doing 4x
`SELECT DISTINCT metric_version` scans. A running refresh worker can legitimately
add a metric_version mid-process, so this is a contract/design question (cache
window vs. liveness), deliberately left out of this change.
