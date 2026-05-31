---
analysis_date: 2026-05-31
last_mapped_commit: c80c39e
scope: full-repo
---
# Codebase Concerns

**Analysis Date:** 2026-05-31

---

## Tech Debt

**constants.py imports sports.py at module bottom (noqa E402/F401/I001):**
- Issue: `constants.py` re-exports all sport-type symbols from `sports.py` via an out-of-order import at line 118, suppressed with `# noqa: E402, F401, I001`. This was a backward-compat shim from the Phase 12/13 migration that split sports into `sports.py` but kept the old `constants.*` access paths live.
- Files: `src/mcp_strava/constants.py:118-130`
- Impact: Callers importing `TRAINING_SPORTS`, `RUNNING_SPORTS`, etc. from `constants` still work, but the dual-import path is confusing and the noqa markers suppress real lint rules rather than fixing the cause. New code should import from `mcp_strava.sports` directly.
- Fix approach: Audit callers of `from mcp_strava.constants import TRAINING_SPORTS` (and similar) — most already import from `sports.py` — then drop the re-export block and the noqa markers.

**mcp_http.py noqa F401 on load_prompt import:**
- Issue: `from mcp_strava.mcp_content import MCP_PROMPT_NAMES, load_prompt  # noqa: F401` at line 26 suppresses an "imported but unused" warning. `load_prompt` is imported for its side-effect or anticipated future use, not an active call in the module.
- Files: `src/mcp_strava/interfaces/mcp_http.py:26`
- Impact: Minor — suppressed lint marker hides whether `load_prompt` is actually used or just dead weight.
- Fix approach: Either invoke `load_prompt` explicitly during server startup (if needed for prompt registration), or remove the import.

**`CURRENT_METRIC_VERSION = 1` is hardcoded in repository and never incremented:**
- Issue: `CURRENT_METRIC_VERSION = 1` is defined in `src/mcp_strava/adapters/duckdb/repository.py:27` and passed throughout the materializer and read-model queries. There is no mechanism to bump it short of a manual code edit. When metric definitions change (e.g., new columns in `activity_metric_facts`), all old facts remain at version 1 and the staleness logic depends on version mismatches to trigger re-materialization.
- Files: `src/mcp_strava/adapters/duckdb/repository.py:27`, `src/mcp_strava/refresh/runtime.py:109`, `src/mcp_strava/adapters/duckdb/read_model_materializer.py`
- Impact: Any future metric schema change that should invalidate all existing facts requires manually bumping the constant AND re-running full materialization — easy to forget, with silent stale data as the consequence.
- Fix approach: Document the bump procedure in a comment adjacent to the constant; add a test that asserts `CURRENT_METRIC_VERSION` matches a hash or count of `FactColumnDefinition` entries so a schema change is caught at CI time.

**`DuckDBRepository.conn` typed as `Any`:**
- Issue: The `conn` field on `DuckDBRepository` (line 159) is typed `Any`, which means every `self.conn.execute(...)` call is unchecked by pyright. The actual DuckDB connection type is `duckdb.DuckDBPyConnection`.
- Files: `src/mcp_strava/adapters/duckdb/repository.py:159`
- Impact: Pyright cannot detect mis-shaped SQL calls or wrong argument types against the connection object. Low blast radius today, but grows as the repository accumulates query methods.
- Fix approach: Import `duckdb.DuckDBPyConnection` and annotate `conn: duckdb.DuckDBPyConnection`. Guard with `TYPE_CHECKING` if needed to avoid a runtime import cost.

**`aggregate_queries.py` and `repository.py` are oversized single-file modules:**
- Issue: `aggregate_queries.py` is 1,277 lines with 50+ top-level functions. `repository.py` is 2,266 lines. Both were assembled during the Phase 8–13 migration with the intent to split later.
- Files: `src/mcp_strava/adapters/duckdb/aggregate_queries.py`, `src/mcp_strava/adapters/duckdb/repository.py`
- Impact: Merge conflicts are more likely; comprehension requires scrolling across 2,000+ lines. Finding the right function requires knowing the file well.
- Fix approach: `aggregate_queries.py` could be split into `status_queries.py` (the `_query_*_status` family) and `metric_queries.py` (the `_build_*_query`, `_query_metric` family). `repository.py` could extract stream/activity read methods into `activity_reads.py`.

**`metric_registry.py` is 2,191 lines of declarative data:**
- Issue: The metric registry is a single 2,191-line Python file that is purely data (metric definitions, fact-column definitions, status-fact definitions). It was intentionally kept monolithic during Phase 10 to avoid import-order issues, but no plan exists to split it.
- Files: `src/mcp_strava/application/metric_registry.py`
- Impact: Any edit to a metric definition requires loading the full 2K-line file mentally. Pyright takes longer to type-check it.
- Fix approach: Consider splitting into `metric_registry_definitions.py` (MetricDefinition records), `fact_column_registry.py` (FactColumnDefinition records), and keeping `metric_registry.py` as the public API that imports from both.

---

## Known Bugs / Workarounds

**DuckDB ART index bloat on unchanged-activity rewrites (mitigated, not fixed):**
- Symptoms: DuckDB `.duckdb` file grows unboundedly if the daily refresh rewrites semantically identical activity rows, because freed ART index blocks are never reclaimed and re-triggers a known DuckDB corruption path.
- Files: `src/mcp_strava/refresh/_sync_ops.py:200-208`, `src/mcp_strava/adapters/duckdb/repository.py:128-146`
- Trigger: Daily refresh calls `sync_summaries` which re-sees all ~600 activities each cycle.
- Workaround: `summary_payload_changed()` computes a SHA-256 semantic hash and skips the write when content is identical. Compaction via `maintenance/compact.py` shrinks the file periodically.
- Residual risk: Hash collision (negligible) or a new non-semantic Strava field that isn't listed in `NON_SEMANTIC_SOURCE_KEYS` would cause a missed skip, re-triggering bloat until next compaction.

**HR recovery pause-detection has six documented edge-case fixes (WR-01 through WR-06):**
- Symptoms: The `calc_hr_recovery()` function in `metrics.py` accumulated six targeted workarounds during Phase 10 testing, each addressing a specific mis-calculation. The function is now correct but dense with special-case logic.
- Files: `src/mcp_strava/metrics.py:69-183`
- Trigger: Activities with duplicate `time_offset` values (WR-01), short pauses spanning data gaps (WR-02/WR-05), activities with no HR in a pause window (WR-03), Decimal types from DuckDB (WR-04), nullable rates (WR-06).
- Residual risk: The function is algorithmically complex (~120 lines) with interacting preconditions. A future refactor of stream-row format could silently violate one of the documented preconditions.
- Safe modification: Any change to `calc_hr_recovery` must verify all six WR scenarios against `tests/test_metrics_pure.py`.

**`type: ignore[arg-type]` suppressions in period-comparison delta math:**
- Symptoms: Three `# type: ignore[arg-type]` markers on lines 668–674 of `metric_services.py` suppress pyright errors on `float(value_a)` / `float(delta)` calls. The `_is_number()` guard narrows the type logically but pyright cannot see through it.
- Files: `src/mcp_strava/application/metric_services.py:668-674`
- Impact: Low — the logic is correct; the suppression just papers over a narrowing gap.
- Fix approach: Replace `_is_number()` with an `isinstance(value_a, (int, float))` guard so pyright narrows the type automatically, eliminating the `type: ignore` markers.

---

## Security Considerations

**Module-level mutable cache in `mcp_http.py` (`_TOOL_RESPONSE_CACHE`):**
- Risk: `_TOOL_RESPONSE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}` is a process-global mutable dict at `src/mcp_strava/interfaces/mcp_http.py:51`. It is accessed and mutated by multiple FastMCP worker threads without a lock.
- Files: `src/mcp_strava/interfaces/mcp_http.py:51-161`
- Current mitigation: CPython's GIL means `dict` operations are individually atomic, so the cache won't corrupt. However, the prune logic (`_prune_tool_response_cache`) reads and modifies the dict in a non-atomic sequence; a concurrent write between the `min()` scan and `pop()` can target the wrong key.
- Recommendations: Add a `threading.Lock()` around cache reads/writes, or switch to `cachetools.TTLCache` with a lock. Alternatively, mark the cache as test-unsafe and document the threading assumption explicitly.

**No authentication on MCP HTTP surface:**
- Risk: The MCP HTTP server has transport security (host/origin validation, bind host guards) but no per-request authentication. Any process that can reach the bound address can call all tools.
- Files: `src/mcp_strava/interfaces/mcp_http.py:165-188`, `src/mcp_strava/deploy/preflight.py`
- Current mitigation: Container profile enforces loopback bind by default; `allow_container_bind` must be explicitly set to allow wildcard. The MCP instructions instruct the calling LLM not to expose raw data.
- Recommendations: Acceptable for a single-user local deployment. Document clearly that this is the threat model so any future multi-user scenario is flagged.

---

## Performance Bottlenecks

**Thread-local read connection reuse assumes FastMCP uses a stable thread pool:**
- Problem: `ReadConn` in `connection.py` caches one DuckDB connection per thread in `threading.local()`. If FastMCP ever switches to async/coroutine dispatch or spawns ephemeral threads, each "thread" gets one connection opened and never closed, leaking file descriptors.
- Files: `src/mcp_strava/adapters/duckdb/connection.py:79-130`
- Cause: Design choice made to avoid the ~25 ms DuckDB catalog-attach cost per request.
- Improvement path: Call `reset_thread_connections()` at server shutdown. For async scenarios, replace with an explicit connection pool (`duckdb` supports per-thread connections but not coroutines natively).

**Read-model materialization is a full recompute on every refresh cycle:**
- Problem: `materialize_read_model_stage()` recomputes all metric facts for all activities each time a refresh completes. With hundreds of activities and rolling-window facts across multiple windows and sports, this is O(activities × windows × sports).
- Files: `src/mcp_strava/adapters/duckdb/read_model_materializer.py`, `src/mcp_strava/refresh/runtime.py:104-111`
- Cause: Simpler to implement than incremental; correctness is easier to reason about.
- Improvement path: Track a `last_materialized_at` per-activity and skip activities whose source rows haven't changed since that timestamp. Daily-load and rolling facts still need full recompute, but activity-level metrics could be incremental.

---

## Fragile Areas

**`calc_hr_recovery()` precondition: unique `time_offset` values from DuckDB:**
- Files: `src/mcp_strava/metrics.py:69-99`
- Why fragile: The function documents "DuckDB does not enforce that here" — it relies on de-duplication inside itself (WR-01). If the SQL query in `repository.stream_hr_velocity_time_rows()` is ever changed to add a JOIN that produces duplicate offsets, the de-duplication catches it silently but a future caller who trusts `len(rows)` may not.
- Safe modification: Do not add JOINs to `stream_hr_velocity_time_rows` that can produce fan-out rows without updating the de-duplication guard.
- Test coverage: `tests/test_metrics_pure.py` covers the WR scenarios.

**`_TOOL_RESPONSE_CACHE` is a module-level singleton that survives between tests:**
- Files: `src/mcp_strava/interfaces/mcp_http.py:51`
- Why fragile: Tests that exercise cached tools can bleed cache state into subsequent tests if the cache is not cleared between runs. There is no `cache_clear()` helper exposed.
- Safe modification: Any test exercising `compare_periods` or `get_training_aggregates` should either monkeypatch `_TOOL_RESPONSE_CACHE` to `{}` in a fixture or set `_TOOL_CACHE_TTL_SECONDS = 0` for the test duration.
- Test coverage: `tests/test_mcp_surface.py` covers these tools; unclear if cache isolation is enforced.

**`_ensure_schema_extensions()` silently swallows all exceptions:**
- Files: `src/mcp_strava/adapters/duckdb/repository.py:178-184`
- Why fragile: The bare `except Exception: pass` on provenance column migration means a genuine schema corruption or permission error is silently discarded. The comment "Table may not exist yet (fresh DB)" is correct for one case but the blanket suppression covers everything.
- Safe modification: At minimum, check `isinstance(exc, duckdb.CatalogException)` or check for the specific table-not-found error rather than catching all exceptions.

**Checkpoint stage string values are bare string literals:**
- Files: `src/mcp_strava/refresh/checkpoints.py`, `src/mcp_strava/refresh/runtime.py`
- Why fragile: `Stage.COMPLETE.value`, `Stage.SUMMARIES.value`, etc. are enum values used as checkpoints in the DB. `_daily_start_index()` / `_backfill_start_index()` look up stages by comparing `stage == candidate.value` — if a `Stage` enum value is ever renamed without a DB migration, all in-progress checkpoints break silently and the refresh re-runs from stage 0.
- Safe modification: Any Stage enum rename requires a DB migration that updates the `checkpoint_stage` column in the refresh state table.

---

## Scaling Limits

**DuckDB single-writer constraint:**
- Current capacity: One writer process (the refresh worker) at a time, enforced by `_DUCKDB_PROCESS_LOCK` (process-level RLock) and the `MirrorDbLocked` exception on OS-level file lock conflict.
- Limit: If a second process (CLI, admin command) attempts a write while refresh is running, it gets `MirrorDbLocked` immediately. The `run_stream_channel_catchup` admin command holds the lock for up to 30 minutes.
- Scaling path: Not applicable — single-user single-process design by intent. Document that any admin command requiring writes should acquire the refresh lease first.

**Strava API rate limit: 100 requests/15 min, 1000/day:**
- Current capacity: Tracked in `adapters/strava/rate_limit.py`; backoff is applied on 429 responses.
- Limit: A full backfill (streams + details for 600+ activities) can exhaust the daily quota in one run.
- Scaling path: Inherent Strava constraint. The per-stage checkpoint system allows resuming after rate-limit backoff. No change needed unless activity count grows significantly.

---

## Dependencies at Risk

**DuckDB ART index known corruption (mitigated by semantic-hash skip):**
- Risk: The DuckDB version in use has a known issue where repeated upserts to the same primary-key row can re-trigger an ART stale-update-read corruption. The semantic-hash skip in `_sync_ops.sync_summaries` is the primary mitigation.
- Impact: If the mitigation fails (e.g., a non-semantic Strava field is added and not listed in `NON_SEMANTIC_SOURCE_KEYS`), the DB can silently return stale read-model facts until compaction.
- Migration plan: Monitor DuckDB release notes; when the ART corruption fix is confirmed upstream, the `NON_SEMANTIC_SOURCE_KEYS` exemption list and hash-skip logic can be simplified to a plain timestamp comparison.

---

## Test Coverage Gaps

**`mcp_http.py` tool response cache threading behavior:**
- What's not tested: No test exercises concurrent requests hitting the same cached tool to verify the prune/evict race is benign under GIL.
- Files: `src/mcp_strava/interfaces/mcp_http.py:128-162`
- Risk: Silent stale-entry eviction of the wrong key under thread contention; unlikely but unverified.
- Priority: Low — single-user deployment with low concurrency.

**`_ensure_schema_extensions()` error paths:**
- What's not tested: The silent `except Exception: pass` on provenance migration has no test for the case where the table exists but the column add fails (e.g., type conflict).
- Files: `src/mcp_strava/adapters/duckdb/repository.py:178-184`
- Risk: A schema mismatch on an upgraded DB silently passes preflight and then fails at query time with a column-not-found error.
- Priority: Medium.

**`run_stream_channel_catchup` in `refresh/runtime.py`:**
- What's not tested: The stream-channel backfill path (the third `run_*` function) is an admin-only command. Its `StravaUnavailable` error branch at line 289 calls `_handle_failure` but also re-sets the checkpoint — coverage of this combined error+checkpoint path is unclear.
- Files: `src/mcp_strava/refresh/runtime.py:208-304`
- Risk: A failed stream-channel backfill could leave the checkpoint in `STREAM_CHANNELS_BACKFILL` with a stale cursor, blocking future daily refreshes until an operator manually resets the stage.
- Priority: Medium.

**`cardiac_drift.py` Jenks clustering with edge inputs:**
- What's not tested: Activities with exactly `MIN_CLUSTER_SIZE` (30) points at the boundary, or activities where `MAX_K=6` clusters all have GVF below the threshold.
- Files: `src/mcp_strava/cardiac_drift.py`, `src/mcp_strava/constants.py:23-40`
- Risk: Edge inputs fall through to the `error` result path silently; drift is reported as unavailable without indication of why.
- Priority: Low.

---

*Concerns audit: 2026-05-31*
