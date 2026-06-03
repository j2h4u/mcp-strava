---
phase: 15
reviewers: [codex, opencode]
reviewed_at: 2026-06-03T13:12:42Z
plans_reviewed: [15-01-PLAN.md, 15-02-PLAN.md, 15-03-PLAN.md, 15-04-PLAN.md, 15-05-PLAN.md]
---

# Cross-AI Plan Review — Phase 15

## Codex Review

## Summary

The phase is well aimed: source-derived invalidation, system-managed metric versions, version-pinned reads, Walk TRIMP discount, and workout time fields all match the project direction. As written, I would not execute the plans unchanged. The main blockers are dependency ordering, an inconsistent fingerprint module set, incomplete metric-version pinning, and a few runtime edge cases around the refresh worker and Docker smoke.

## Strengths

- The bigint `metric_version` sidecar design preserves existing PK/read contracts while removing the manual version knob.
- The single materialization chokepoint is the right place to wire the orphaned `enqueue_metric_version_recompute()` in `repository.py:534`.
- The R11 concern is real: aggregate reads currently use `COUNT(DISTINCT metric_version)` as a diagnostic but do not filter by current version in `aggregate_queries.py:693`.
- Walk discount is scoped pragmatically: a pure function plus repository aggregation, without adding env config.

## Concerns

**HIGH: 15-02 depends on 15-01 but declares no dependency.**
15-02 imports `compute_logic_fingerprint()` from 15-01, so it cannot safely run in parallel or before 15-01.

**HIGH: fingerprint module set is internally inconsistent.**
15-01's tuple omits `mcp_strava.metric_registry`, but 15-05 explicitly assumes `metric_registry.py` is fingerprinted. Since registry-owned schema metadata lives in `metric_registry.py:1574`, this can miss registry-only computed-field/schema changes.

**HIGH: version pinning is incomplete.**
15-03 pins `_where_clause()`, but `_effective_range_for_metric()` still derives all-time ranges from unpinned views in `aggregate_queries.py:607`. Status facts also query `activity_metric_facts` directly without `metric_version` filters, e.g. `aggregate_queries.py:252`.

**HIGH: sidecar migration can create partial schema on schema-less DBs.**
`DuckDBRepository.from_connection()` currently tolerates a blank in-memory DB by swallowing the missing `activity_metric_facts` `CatalogException` in `repository.py:195`. Creating `read_model_logic_version` there before `create_schema()` risks a partial schema conflicting with normal `CREATE TABLE` DDL.

**MEDIUM: worker can skip fingerprint detection when dirty queue is empty.**
`_materialize_dirty_read_model()` checks dirty count before calling `materialize_read_model_stage()` in `worker.py:60`. A logic-only edit with no dirty rows may not be detected on that path.

**MEDIUM: CURRENT_METRIC_VERSION removal needs wider scope.**
The plan names main files, but `adapters/duckdb/__init__.py:5` also re-exports it. `aggregate_services.py` also calls `repo.read_model_status()` unpinned.

**MEDIUM: Walk discount must preserve observed/effective semantics through model facts.**
Daily facts can keep `observed_trimp` undiscounted, but `training_model_daily.observed_trimp` is currently set to the Banister input `trimp` in `read_model_materializer.py:280`. The plan should specify whether that column becomes undiscounted or is renamed/treated as effective.

**MEDIUM: packaged-install smoke is not guaranteed by `tests/test_docker_runtime.py`.**
Those tests run locally. To prove `pip install /app` source availability, add a `docker compose exec` check to `just test` or the MCP smoke path in `Justfile:37`.

**MEDIUM: relative_time needs datetime normalization.**
Fixtures include both offset-less local strings and `Z` strings. The plan should normalize aware/naive values before subtracting from service `now`.

## Suggestions

- Make `15-02 depends_on: [15-01]`.
- Add `mcp_strava.metric_registry` to `COMPUTE_SOURCE_MODULES`, and hash `(module_name, source_text)` pairs sorted by module name.
- Replace vague "transitively imported compute path" completeness with a small explicit allowlist plus a test that fails when direct compute imports in `read_model_materializer.py` are not represented.
- In 15-03, introduce one helper that returns `(current_metric_version, trigger_reason)` and call it before dirty-count gates.
- Pin current version in `_where_clause()`, `_effective_range_for_metric()`, `query_status_facts()`, and service read-model metadata.
- Update existing mixed-version aggregate tests to assert "pinned current" behavior, keeping `metric_version_count` as a tripwire.
- For Walk discount, avoid per-sport rounding drift: sum raw per-sport TRIMP, apply discount, then round once.
- For 15-05, decide whether `start_time_local` is a new metric id or a payload alias for existing `start_time`.

## Risk Assessment

- 15-01: MEDIUM
- 15-02: MEDIUM-HIGH
- 15-03: HIGH
- 15-04: MEDIUM
- 15-05: MEDIUM

Overall: HIGH as written, mostly because 15-03 can still blend or miss versions. With the pinning/migration fixes above, this drops to MEDIUM.

---

## OpenCode Review

# Phase 15 — Cross-AI Plan Review

## Executive Summary

The phase goal (zero-knob auto-recompute + Walk discount + time fields) is **achievable** and the architecture is **sound**. The single-chokepoint design, whole-module fingerprinting, and monotonic-version approach are well-chosen. However, several **HIGH** concerns need resolution, primarily around: dependency ordering within Wave 1, error handling in `_ensure_schema_extensions` (seed path), missing `metric_version` threading in `_where_clause`'s actual code shape, and the `update_activity_source_state_and_enqueue_dirty` default-arg rewiring.

## Plan 15-01: Source-text logic fingerprint

### Strengths
- Runtime `importlib.import_module()` inside the function avoids the `metric_registry → repository → schema → metric_registry` cycle.
- `sha256` over `inspect.getsource` is stable across processes and `PYTHONHASHSEED` — well-proven.
- Completeness test walks transitive imports from `read_model_materializer` to detect missing modules — excellent poka-yoke.
- Sensitivity test uses monkeypatching as a fast CI-safe alternative to actually editing files.

### Concerns
- **MEDIUM** — The completeness test must walk imports transitively from `read_model_materializer`, restricted to `mcp_strava`, and must distinguish `import` statements from runtime parameter usage. Walk **static imports** only (`ast.parse`), not runtime call graphs — a dynamic `sys.modules` snapshot would include test-only modules.
- **LOW** — No test proves `inspect.getsource` actually succeeds on all listed modules (presence + text-change are covered, but not source-readability until the 15-05 Docker smoke).
- **LOW** — `inspect.getsource` representation can vary across Python versions; non-issue while 3.14 is locked, but flag for any future upgrade.

### Risk Assessment: **LOW**

## Plan 15-02: `read_model_logic_version` sidecar

### Strengths
- Singleton table design with fixed `id=1` is simple and correct.
- Idempotent seed (insert-if-absent) prevents double-row bugs.
- Seed=current fingerprint ensures no spurious recompute on deploy — critical for data preservation.
- Fallback logic (`max metric_version across fact tables, else 1`) for partially-migrated DBs is pragmatic.

### Concerns
- **HIGH** — The seed in `_ensure_schema_extensions` calls `compute_logic_fingerprint()`, which `importlib.import_module()`s ~7 modules. The plan wraps it in `try/except duckdb.CatalogException`, but an `ImportError` from `compute_logic_fingerprint()` is NOT a `CatalogException` — a transient import error could break `from_connection()`. Mitigation: wrap the fingerprint call in its own `try/except Exception` (log-warn-skip, defer to next cycle), or seed only in the first `materialize_read_model_stage` call where all modules are guaranteed loaded.
- **HIGH** — 15-01 and 15-02 are both Wave 1 with `depends_on: []`, but 15-02's seed calls `compute_logic_fingerprint()` which does not exist until 15-01 completes. Set `depends_on: [15-01]`.
- **MEDIUM** — `current_metric_version()` fallback scans 4 UNION ALL'd fact tables; fine for one-time fallback but should be cached for the request lifetime; caching behavior unspecified.
- **MEDIUM** — If `_ensure_schema_extensions` runs `CREATE TABLE` before `create_schema()`, the new table DDL in `DUCKDB_SCHEMA_SQL` must use `CREATE TABLE IF NOT EXISTS read_model_logic_version` to stay idempotent. The plan omits `IF NOT EXISTS`.
- **LOW** — DuckDB doesn't support SQLite-style `INSERT OR REPLACE` semantics identically; specify the concrete upsert form for the `id=1` singleton.

### Risk Assessment: **MEDIUM** (drops to LOW if the seed is deferred out of `_ensure_schema_extensions`)

## Plan 15-03: Fingerprint trigger + rewiring

### Strengths
- Single chokepoint at `materialize_read_model_stage` — all materialize paths funnel through here.
- Wires the orphan `enqueue_metric_version_recompute` — fixes actual dead code.
- R11 aggregate version pin is critical and correctly identified.
- Structured log events are self-explanatory; `CURRENT_METRIC_VERSION` removal is thorough (grep verification step).

### Concerns
- **HIGH** — `update_activity_source_state_and_enqueue_dirty` (repository.py:408) has `metric_version: int = CURRENT_METRIC_VERSION` as a default. After deleting the constant this is a syntax error. The plan offers two options but must pick one. Recommendation: remove the default (make it required) and thread the explicit version from the sync callers, avoiding the repo resolving its own current version mid-sync.
- **HIGH** — `_where_clause` signature change (adding `metric_version: int`) must be stated explicitly and threaded from `query_training_aggregates`. The plan is ambiguous about where `metric_version` is resolved for aggregate queries (new parameter vs internal resolution). Specify: `query_training_aggregates` gains a `metric_version` parameter resolved by the caller in `aggregate_services.py`.
- **MEDIUM** — `enqueue_metric_version_recompute` enqueues ALL activities (correct for "bump all"), but with `limit=None` the materializer drains all dirty rows in one transaction. Acceptable at current DB size; note as a future long-transaction concern.

### Risk Assessment: **MEDIUM-HIGH** (two sharp HIGHs, easily resolved with explicit decisions)

## Plan 15-04: Walk TRIMP discount

### Strengths
- Pure domain function in `metrics.py` respects the Phase 10/12 boundary (no storage imports).
- Per-sport aggregation is the right granularity — applying discount before summing preserves `observed_trimp` separately.
- Doubles as the first real zero-knob proof.
- Clear TDD structure with well-specified cases.

### Concerns
- **MEDIUM** — `daily_load_points_between` needs a new per-sport method (e.g. `observed_trimp_history_by_sport` returning `dict[date → dict[sport → trimp]]`) sharing the same date range / `session_bounds` as `observed_trimp_history`. The plan doesn't specify parameter sharing.
- **MEDIUM** — The mechanism sensitivity is covered by 15-01, but no co-located end-to-end test proves a `WALK_TRIMP_DISCOUNT` change actually recomputes on the next cycle. Add an integration test: seed walk data, materialize, monkeypatch the constant, re-materialize, assert new `effective_trimp`.
- **LOW** — Name the new per-sport method and the pure function explicitly (e.g. `discounted_effective_trimp(by_sport) -> float`) to avoid ambiguity.

### Risk Assessment: **LOW**

## Plan 15-05: Workout time fields

### Strengths
- Follows the existing `ACTIVITY_METRIC_FACT_LATE_COLUMNS` + `ensure_provenance_columns` pattern.
- `relative_time` computed at read time (depends on `now`) — correct.
- Packaged-install smoke closes the `pip install /app` → `inspect.getsource` regression risk from 15-01.
- Additive column migration is well-understood (NULL on old rows until re-materialized).

### Concerns
- **MEDIUM** — `start_time_local` via `[11:16]` slice assumes Strava's datetime format. Parse `start_date_local` with `datetime.fromisoformat()` + `strftime("%H:%M")`, falling back to `None` on parse failure.
- **MEDIUM** — `relative_time` source field is unspecified (`activity_date` is a date, not datetime). Parse `start_date_local` to a full datetime at read time; omit/`None` when missing or unparseable.
- **LOW** — Explicitly update `_activity_payload` (add `now: datetime`) and both calling service signatures.
- **LOW** — Make the fingerprint smoke unconditional in `test_logic_fingerprint.py` (local editable install), with the Docker-specific smoke as a supplement, so `uv run pytest -q` also catches it.

### Risk Assessment: **LOW**

## Cross-Cutting Concerns

- **HIGH** — 15-02 missing `depends_on: [15-01]` (seed calls `compute_logic_fingerprint()` from 15-01).
- **MEDIUM** — No plan updates `aggregate_services.py` — its own `read_model_status` / aggregate call site needs the version pin too.
- **MEDIUM** — `update_activity_source_state_and_enqueue_dirty` sync callers must learn the current `metric_version` (via `repo.current_metric_version()`); the plan should say so.
- **MEDIUM** — Test gaps: end-to-end "change constant → recompute"; `_ensure_schema_extensions` + `compute_logic_fingerprint()` ImportError path.
- **LOW** — Large-DB single-transaction materialize; `resource_usage_facts` filter verification.

Architecture respects all stated constraints (domain boundary, no env config, MCP surface unchanged, data preservation via seed=current).

## Overall Risk Assessment: **MEDIUM**

The architecture is sound and the phased execution is well-structured. The HIGH-severity concerns are all mitigatable with small plan amendments — none are architectural blockers.

---

## Consensus Summary

Both reviewers independently agree the **architecture is sound and the phase goal is achievable**. The single-materialization chokepoint, whole-module source-text fingerprint, bigint `metric_version` sidecar, and pure-domain Walk discount are all well-chosen. Both also agree the plans are **not executable unchanged** — they require small, surgical amendments before execution. Codex rates overall risk HIGH-as-written (dropping to MEDIUM after fixes); OpenCode rates it MEDIUM. The divergence is about labeling, not substance: they converge on the same fix set.

### Agreed Strengths (raised by both reviewers)

- Single materialization chokepoint at `materialize_read_model_stage` is the correct place to wire the (currently orphaned) recompute enqueue.
- bigint `metric_version` sidecar preserves existing PK/read contracts while removing the manual version knob.
- Whole-module `sha256(inspect.getsource(...))` fingerprint is process-stable and `PYTHONHASHSEED`-independent.
- Walk discount is pragmatically scoped: a pure `metrics.py` function plus repository aggregation, no env config, respecting the Phase 10/12 domain boundary.
- The R11 aggregate version-pin gap is real and correctly identified.

### Agreed Concerns (raised by both — highest priority)

1. **[HIGH] 15-02 must declare `depends_on: [15-01]`.** Both reviewers independently flagged that 15-02's seed calls `compute_logic_fingerprint()` from 15-01, so the two cannot share Wave 1 with empty deps. This is the single most-agreed finding.
2. **[HIGH] Version pinning is incomplete / `_where_clause` threading is under-specified.** Codex: `_effective_range_for_metric()` (`aggregate_queries.py:607`) and status facts (`:252`) remain unpinned. OpenCode: `_where_clause` signature change and where `metric_version` is resolved for `query_training_aggregates` is ambiguous. Same gap, two angles — the version pin must be threaded through ALL aggregate/status read paths, not just `_where_clause`.
3. **[MEDIUM→HIGH] `CURRENT_METRIC_VERSION` deletion breaks the default arg on `update_activity_source_state_and_enqueue_dirty` and needs wider removal scope.** OpenCode rates the default-arg breakage HIGH (it is a literal syntax error after deletion); Codex flags the wider scope (`adapters/duckdb/__init__.py:5` re-export, `aggregate_services.py` unpinned call). The plan must pick the resolution (recommended: make `metric_version` required, thread from sync callers).
4. **[MEDIUM] Seed-path robustness.** Codex: seeding the sidecar in `from_connection()` before `create_schema()` risks partial schema on blank in-memory DBs. OpenCode: the seed's `compute_logic_fingerprint()` can raise `ImportError` (not a `CatalogException`), breaking `from_connection()`. Both point at the same fix: defer the seed to the first `materialize_read_model_stage` (where all modules are loaded and schema exists), or guard it independently.
5. **[MEDIUM] `relative_time` / `start_time_local` need datetime normalization, not string slicing.** Both: parse `start_date_local` to an aware/naive-normalized datetime; don't `[11:16]`-slice; handle mixed-offset and `Z` fixtures; `None`-fallback on parse failure.
6. **[MEDIUM] Packaged-install / zero-knob proof needs a real end-to-end test.** Codex: `test_docker_runtime.py` runs locally — add a `docker compose exec` check to prove `pip install /app` source availability. OpenCode: add a co-located "change constant → recompute" integration test rather than relying on the mechanism test.

### Divergent Views

- **Overall risk label.** Codex: HIGH as-written (driven by 15-03 potentially blending/missing versions); OpenCode: MEDIUM. Both agree the fix set is small and non-architectural — the disagreement is severity framing, and both land at MEDIUM post-fix.
- **Fingerprint module set — `metric_registry` inclusion.** Codex raises a HIGH that `COMPUTE_SOURCE_MODULES` omits `mcp_strava.metric_registry` while 15-05 assumes it is fingerprinted (registry-owned schema can change without invalidation). OpenCode does not flag this — it accepts the listed module set. Worth investigating: confirm whether registry-owned computed-field/schema changes are captured by the current module list.
- **Walk discount rounding.** Codex adds a specific suggestion (sum raw per-sport TRIMP, apply discount, round once) to avoid per-sport rounding drift; OpenCode focuses on method naming/return-type clarity instead. Complementary, not contradictory.
