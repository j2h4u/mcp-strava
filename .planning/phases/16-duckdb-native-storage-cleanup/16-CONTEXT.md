# Phase 16: DuckDB-native storage cleanup - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning
**Source:** Codebase audit (Explore subagent) + owner-verified findings. No discuss-phase needed — scope is fully determined; there are no open design questions.

<domain>
## Phase Boundary

Remove SQLite-era legacy from the DuckDB storage layer (`src/mcp_strava/adapters/duckdb/`) so it uses native DuckDB types and SQL. The project migrated SQLite→DuckDB; residual string-typed columns, a SQLite-only SQL function, and BIGINT-as-boolean columns remain. This phase converts/removes them **with no change to external behavior** (MCP/CLI payloads, freshness semantics, read-model values stay byte-for-byte equivalent).

**Hard principle (project-wide): NO backward compatibility.** The DB regenerates from source (resync + read-model rematerialization). Drop/retype columns cleanly — NO migration of old DBs, NO compat shims, NO fallback for the old string forms. A removed/retyped column hitting old code SHOULD fail fast.

Each item below is an independent, atomic commit with its own tests. Verify each finding against the live code before changing it (findings are leads, not gospel — the audit already mis-stated one severity; see Task 1).
</domain>

<decisions>
## Implementation Decisions (locked)

### Task 1 — Drop `activities.date`; make kudos_store native (couple: same column)
- `activities.date VARCHAR` (`schema_tables.py:11`) duplicates native `activities.activity_day DATE` (`:10`). They hold the SAME local day — `INSERT` does `activity_day = CAST(date[:10] AS DATE)`, `date = date`, fed from `_sync_ops.py:245 start_date_local[:10]`. **Remove the `date` column.**
- `kudos_store.py:52-54` uses `a.date >= date('now', ?)` — `date('now',...)` is **SQLite-only and FAILS on DuckDB** (verified live: ParserException / ConversionException). The branch is currently DEAD (both `_sync_kudos` callers — `runtime.py:135`, the test — pass `window_days=None`), so it is a **latent mine, not an active runtime bug** (audit over-stated this as HIGH "fails at runtime"). Rewrite the `window_days` branch to native: `a.activity_day >= (CURRENT_DATE - (? * INTERVAL '1 day'))` binding an int; `ORDER BY a.date DESC` → `ORDER BY a.activity_day DESC`.
- Update ALL readers of `a.date` → `a.activity_day`: `activity_lookup_queries.py` (SELECT `a.date`; `MAX(date)` in `latest_activity_at` — `str(MAX(activity_day))` still yields "YYYY-MM-DD", preserve), `activity_selectors.py:22,29` (SELECT + GROUP BY), `stream_coverage_queries.py:40`, `read_model_repository.py:178,202` (`a.date AS activity_date` → `a.activity_day AS activity_date`; the MCP payload's `activity_date` already comes from `row["activity_day"]`, so surface is unchanged).
- **Add a test for the `window_days` kudos branch** — it is currently untested, which is exactly why the broken SQL hid.

### Task 2 — `refresh_requests.requested_for_day` VARCHAR → DATE
- `schema_tables.py:97`. Equality-filtered only (`refresh_state_store.py:202`), no range scan. Convert column to `DATE`; pass a `datetime.date` from the Python call site instead of a string.

### Task 3 — Boolean columns BIGINT → native BOOLEAN
- `streams.is_moving BIGINT` (`schema_tables.py:35`) → `BOOLEAN`; write path `stream_write_repository.py:137` cast int→bool before binding.
- `activity_metric_facts.cardiac_drift_significant BIGINT` (`metric_registry_fact_column_sql.py:45`) → `BOOLEAN`. Requires adding `"BOOLEAN"` to `_SUPPORTED_FACT_SQL_TYPES` (`metric_registry_fact_column_sql.py:5`); write path `read_model_activity_facts.py:184,323` bind `bool`; predicate `status_fact_queries.py:247` `>= ?`(1) → `= TRUE`. This touches the registry-owned fact schema (Phase 14) and the read-model logic fingerprint — the fingerprint recompute is automatic-by-construction (a logic change auto-invalidates); ensure `COMPUTE_SOURCE_MODULES` coverage still holds (the fingerprint completeness test in `test_logic_fingerprint.py` will catch a gap).

### Task 4 — `missing_reasons_json` VARCHAR-JSON → native VARCHAR[]
- `schema_tables.py:135,158,183` (daily_load_facts / training_model_daily / rolling_period_facts). Stored as a JSON-array string, aggregated via DuckDB `list()` (`aggregate_queries.py:294,377,462`) then **double-decoded** in Python (`aggregate_rows.py:169-181` json.loads each element). Convert column to native `VARCHAR[]` so `list_flatten`/`list_distinct` work in SQL and the Python double-`json.loads` disappears. Touches schema + aggregate SQL + write-path serialization + decode. Medium effort.

### Task 5 — Low-risk SQL cleanups (one commit)
- `schema_views.py`: remove redundant `CAST(x AS DATE)` where `x` is already DATE (lines ~9,55,82,109,121,125,182); the WHERE predicate at ~125 `CAST(a.activity_day AS DATE) <= d.day` → `a.activity_day <= d.day` (index-friendliness).
- `values_json` channel-coverage check (`stream_coverage_queries.py:87`): replace the per-row Python `json.loads` loop with one SQL predicate `json_extract_string(values_json, '$.' || ?) IS NOT NULL`. **Leave the merge path** (`stream_write_repository.py:252`) as-is.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Schema & types
- `src/mcp_strava/adapters/duckdb/schema_tables.py` — table DDL (activities, streams, refresh_requests, daily_load_facts, training_model_daily, rolling_period_facts)
- `src/mcp_strava/adapters/duckdb/schema_views.py` — views with redundant CASTs
- `src/mcp_strava/metric_registry_fact_column_sql.py` — registry-owned fact-column SQL types (`_SUPPORTED_FACT_SQL_TYPES`, cardiac_drift_significant)

### SQL call sites
- `src/mcp_strava/adapters/duckdb/kudos_store.py` — the SQLite `date('now')` + VARCHAR sort
- `src/mcp_strava/adapters/duckdb/activity_lookup_queries.py`, `activity_selectors.py`, `stream_coverage_queries.py`, `read_model_repository.py` — readers of `a.date`
- `src/mcp_strava/adapters/duckdb/refresh_state_store.py` — requested_for_day usage
- `src/mcp_strava/adapters/duckdb/stream_write_repository.py`, `read_model_activity_facts.py`, `status_fact_queries.py` — boolean write/read paths
- `src/mcp_strava/adapters/duckdb/aggregate_queries.py`, `aggregate_rows.py` — missing_reasons_json aggregate + decode
- `src/mcp_strava/refresh/_sync_ops.py` (activities.date / kudos), `refresh/runtime.py` (`_sync_kudos` caller)

### Invariants
- `metric_registry.py` `COMPUTE_SOURCE_MODULES` + `tests/test_logic_fingerprint.py` — read-model fingerprint completeness (Task 3 touches the compute path)
- import-linter contracts (pyproject.toml `[tool.importlinter]`) — adapters/domain boundaries must stay KEPT
</canonical_refs>

<specifics>
## Specific Ideas
- Atomic commits in the severity/dependency order above (1→5). Task 1's two halves (drop column + kudos rewrite) are coupled (same column) → one commit.
- Verify-before-fix each finding (grep file:line, confirm). The audit already over-stated Task 1 severity ("fails at runtime" — actually a dead branch).
- Gate after each task: `just check` (ruff + format + basedpyright + import-linter + vulture) + `pytest -n auto`.
- Final acceptance: full suite green + container rebuild healthy with MCP surface intact (6 tools, 3 prompts, 2 resources) + a fresh resync/rematerialization produces identical payloads.
</specifics>

<deferred>
## Deferred / Out of Scope (intentional — do NOT touch)
- `summary_json` / `detail_json` / `zones_json` stored as VARCHAR — deliberate full-payload retention; `json_extract*` already works on VARCHAR in DuckDB. Leave.
- All operational `*_at` ISO-string instant columns (`synced_at`, `fetched_at`, `computed_at`, `last_success_at`, `last_attempt_at`, `backoff_until`, `lease_expires_at`, `started_at`, `finished_at`, `changed_at`, `requested_at`, `consumed_at`, `timestamp`) — moments, not range-scanned, deliberately ISO strings. Leave.
- `CAST(? AS DATE)` on bound ISO params in `activity_selectors.py` / `aggregate_sql_expressions.py` — correct as-is. Optional polish only.
- Bucket calendar-vs-rolling semantics + configurable week-start (separate parked product question from the MCP-design thread).
</deferred>

---

*Phase: 16-duckdb-native-storage-cleanup*
*Context gathered: 2026-06-11 via codebase audit (no discuss-phase — scope fully determined)*
