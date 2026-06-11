---
status: passed
phase: 16-duckdb-native-storage-cleanup
verified: 2026-06-11T10:45:00Z
method: goal-backward (inline; verifier subagent hit session limit, orchestrator completed)
must_haves_verified: 8
must_haves_total: 8
score: 8/8
tests: 427 passed; just check clean
---

# Phase 16: Verification Report — DuckDB-native storage cleanup

**Goal:** Remove SQLite-era legacy from the DuckDB storage layer so it uses native
DuckDB types (DATE/BOOLEAN/arrays) where it matters, contains no SQLite-only SQL
functions, and has no string-typed columns that are range-scanned or duplicate a
native column — while preserving identical external behavior (MCP/CLI payloads,
freshness semantics, read-model values).

**Verdict:** PASSED (8/8 must-haves verified against the live codebase).

## Must-Have Checks

| # | Must-have | Evidence | Status |
|---|-----------|----------|--------|
| 1 | `activities.date VARCHAR` removed; readers use native `activity_day DATE` | `schema_tables.py:10` `activity_day DATE NOT NULL`; indexes `idx_duckdb_activities_day_id` on `activity_day`; `RepositoryActivityRow.date` → `activity_day` (no `.date` left in `types_repository.py`) | ✅ |
| 2 | `refresh_requests.requested_for_day` native DATE | `schema_tables.py:96` `requested_for_day DATE NOT NULL` | ✅ |
| 3 | `streams.is_moving` + `cardiac_drift_significant` native BOOLEAN | `schema_tables.py:34` `is_moving BOOLEAN`; `metric_registry_fact_column_sql.py:45` `_sql("BOOLEAN", …)`; write sites bind `bool(drift and drift.is_significant)` | ✅ |
| 4 | `missing_reasons_json` → `VARCHAR[]` in all four fact tables; no decode path | `metric_registry_fact_column_sql.py:25,70,91,114` `_sql("VARCHAR[]", default_sql="[]")` (activity/daily/model/rolling); `schema_tables.py:134,157,182`; no `json.loads` references `missing_reasons_json` | ✅ |
| 5 | No SQLite-only SQL functions (`date('now')`, `strftime`, `julianday`) | grep: zero SQL-level matches; kudos window uses `CURRENT_DATE - (? * INTERVAL '1 day')`. Remaining `strftime` are Python `datetime.strftime` (metrics/training/compact), not SQL | ✅ |
| 6 | No no-op `CAST(x AS DATE)` in views | `schema_views.py`: zero `CAST(… AS DATE)` (16-06 removed all 7) | ✅ |
| 7 | Out-of-scope items intentionally preserved | `summary_json`/`detail_json` (`schema_tables.py:17-18`) + `zones_json` (`:55`) still VARCHAR; operational `*_at` ISO-string instants unchanged | ✅ |
| 8 | Identical external behavior | Full suite `just unit` = 427 passed; `just check` clean (ruff/basedpyright src 0 errors/lint-imports 3 contracts kept/vulture) | ✅ |

## Cross-Plan Trace

All 6 plans have SUMMARY.md and are reflected in code:
- 16-01 regression guard (kudos window_days) — test present, xfail flipped to passing by 16-02.
- 16-02 drop `date VARCHAR` + native kudos + `activity_day` rename — verified (check 1).
- 16-03 `requested_for_day` → DATE — verified (check 2).
- 16-04 BIGINT → BOOLEAN (`is_moving`, `cardiac_drift_significant`) — verified (check 3).
- 16-05 `missing_reasons_json` → `VARCHAR[]` + `flatten()` SQL + `json.loads` removed — verified (check 4).
- 16-06 remove no-op CASTs + `json_extract_string` coverage predicate — verified (check 6).

## Code Review Remediation

`16-REVIEW.md` status: resolved (commit 85dab88). Reviewer's 3 "criticals" were
re-verified and did not hold as runtime blockers (CR-01 stale annotations on
never-instantiated dataclasses; CR-02/CR-03 pre-existing). Real post-migration dead
shims removed (WR-02 ALTER migration + 2 backward-compat tests, WR-03 `_coerce_day`
str-parse, CR-03 `requested_at` fallback). WR-01/WR-04 rejected with rationale
(deliberate boundary contract / by-design SQL assembler, zero injection). CR-02/WR-05
deferred as pre-existing single-writer concurrency notes.

## Minor Observations (non-blocking)

- `metric_registry_fact_column_sql.py:45` sets `cardiac_drift_significant` BOOLEAN with
  `default_sql="0"` — DuckDB coerces `0`→`false` (tests green); could read `FALSE` for clarity.
- `metric_registry_metric_factory.py:48` description still says "materialized as 1 …
  otherwise 0" — stale wording describing the old int semantics; cosmetic.

These are tracked in `16-REVIEW.md` scope as cosmetic and do not affect behavior.
