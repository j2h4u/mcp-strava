---
phase: 11-tidy-materializer-repository-access-replace-the-6-inline-sql
plan: "01"
subsystem: adapters/duckdb
tags: [refactor, boundary, repository, materializer, IN-03]
dependency_graph:
  requires: []
  provides: [named-repo-methods-for-materializer]
  affects: [src/mcp_strava/adapters/duckdb/repository.py, src/mcp_strava/adapters/duckdb/read_model_materializer.py]
tech_stack:
  added: []
  patterns: [repository-public-api, named-query-methods]
key_files:
  created: []
  modified:
    - src/mcp_strava/adapters/duckdb/repository.py
    - src/mcp_strava/adapters/duckdb/read_model_materializer.py
decisions:
  - "SQL copied verbatim from materializer call sites — no reformatting, no reordering of params"
  - "zone_seconds_for_activity preserves the exact 9-param list [b[0], b[0], b[1], b[1], b[2], b[2], b[3], b[-2], activity_id]"
  - "stream_counts_for_activity returns tuple[int,int] directly; materializer one-liners call it without local var extraction"
metrics:
  duration_seconds: 243
  completed_date: "2026-05-30"
  tasks_completed: 2
  files_modified: 2
---

# Phase 11 Plan 01: Tidy Materializer Repository Access Summary

**One-liner:** Moved 6 inline SQL call sites from read_model_materializer.py into named DuckDBRepository public methods, closing IN-03 (boundary-crossing private helper calls).

## Tasks Completed

| Task | Commit | Description |
|------|--------|-------------|
| 1: Add 6 named methods to DuckDBRepository | d9f614a | stream_counts_for_activity, zone_seconds_for_activity, daily_fact_sums, rolling_load_aggregate, training_model_row, rolling_cardiac_metric_rows |
| 2: Replace 6 inline call sites in materializer + green-suite gate | 3e083e7 | All 6 sites replaced; materializer now uses named public API only |

## What Was Done

**Task 1** added 6 new public methods to `DuckDBRepository`, positioned after `stream_altitude_rows` in the streams/load section. Each method copies its SQL verbatim from the corresponding materializer call site and uses `_fetchone`/`_fetchall` internally (the correct private primitives inside the repository).

**Task 2** replaced every `repo._fetchone` and `repo._fetchall` call in `read_model_materializer.py` with the corresponding named method. The helper functions `_stream_counts` and `_zone_seconds` became one-liners. The three sites in `_materialize_rolling_facts` became three clean single-line assignments. All downstream variable names, guard expressions, and return types were preserved.

## Verification

- `grep -v "^#" read_model_materializer.py | grep -c "repo\._fetchone\|repo\._fetchall"` → **0**
- `grep -c "def stream_counts_for_activity|def zone_seconds_for_activity|..."` in repository.py → **6**
- `just test` (Docker build + smoke): **status: ok** — all 6 MCP tools healthy, container healthy

Note: `just test` is the project's test runner (Docker build + container smoke). The `uv run pytest` path requires `duckdb` in the system environment which is not available outside the container. The smoke gate (rebuild + healthy container + tool calls) is the authoritative verification for this project.

## Deviations from Plan

None — plan executed exactly as written. SQL copied character-for-character; parameter ordering preserved verbatim in all 6 methods; no existing methods modified.

## Known Stubs

None.

## Threat Flags

None — pure intra-adapter relocation, no new trust boundaries, no new SQL introduced.

## Self-Check

- [x] `src/mcp_strava/adapters/duckdb/repository.py` modified — FOUND (commit d9f614a)
- [x] `src/mcp_strava/adapters/duckdb/read_model_materializer.py` modified — FOUND (commit 3e083e7)
- [x] 6 named methods in repository.py — VERIFIED (grep returns 6)
- [x] 0 private calls in materializer — VERIFIED (grep returns 0)
- [x] Full suite green — VERIFIED (just test → status: ok)

## Self-Check: PASSED
