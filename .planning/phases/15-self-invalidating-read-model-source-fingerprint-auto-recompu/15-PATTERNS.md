# Phase 15 — Pattern Map

> Closest existing analogs for each file this phase creates or modifies. The planner references these in task `<read_first>` and `<action>` fields so executors copy real patterns, not invent them.

## File Classification

| File | Create/Modify | Role | Data Flow | Closest Analog |
|------|---------------|------|-----------|----------------|
| `src/mcp_strava/metric_registry.py` | modify | registry/utility | transform (source→hash) | `repository.py::_semantic_json_hash` (135) — sha256 hashing idiom |
| `src/mcp_strava/adapters/duckdb/schema.py` | modify | migration/DDL | batch | `CREATE TABLE read_model_refresh_runs` (237) singleton-ish + `ensure_provenance_columns` (518) additive |
| `src/mcp_strava/adapters/duckdb/repository.py` | modify | model/storage | CRUD | `enqueue_metric_version_recompute` (534), `read_model_status` (649), `_ensure_schema_extensions` (195) |
| `src/mcp_strava/refresh/_sync_ops.py` | modify | service/orchestration | event-driven | `materialize_read_model_stage` (269) — the chokepoint |
| `src/mcp_strava/refresh/runtime.py` | modify | orchestration | event-driven | call sites (108, 179) passing `CURRENT_METRIC_VERSION` |
| `src/mcp_strava/refresh/worker.py` | modify | orchestration | event-driven | `_materialize_dirty_read_model` (62-79) |
| `src/mcp_strava/adapters/duckdb/read_model_materializer.py` | modify | service/storage | batch transform | `_materialize_daily_facts` (211), `materialize_read_model` (368) |
| `src/mcp_strava/adapters/duckdb/aggregate_queries.py` | modify | query builder | request-response | `_where_clause` (933) |
| `src/mcp_strava/constants.py` | modify | config | — | `Config.Zones.COEFF` / module-level `SPORT_WALK` (124) |
| `src/mcp_strava/metrics.py` | modify | domain/pure-fn | transform | `calc_hrr_pct` (240) — pure fn over plain inputs, no storage import |
| `src/mcp_strava/application/metric_services.py` | modify | service | request-response | `_activity_payload` (273), `_relative`/read-time formatting |
| `tests/test_logic_fingerprint.py` | create | test | — | `tests/test_metric_services.py` header (fixtures via `open_fixture_db` + `create_schema`) |

## Pattern Assignments

### Logic fingerprint — `metric_registry.py`
- **Analog:** `repository.py:135 _semantic_json_hash` — `hashlib.sha256(json.dumps(..., sort_keys=True).encode()).hexdigest()`. Mirror the `sha256` + `.hexdigest()` idiom; substitute `sorted(inspect.getsource(import_module(m)) for m in COMPUTE_SOURCE_MODULES)` as the input, delimited with `b"\x00"`.
- **Placement:** `COMPUTE_SOURCE_MODULES` tuple + `compute_logic_fingerprint()` belong in `metric_registry.py` (already the compute-surface inventory owner). `import_module` calls go **inside** the function (runtime import) to avoid the `repository → schema → metric_registry` cycle.
- **Completeness test analog:** `metric_registry.py:2085` `_validate_*` block already asserts registry/table set consistency with `raise RuntimeError` on drift — copy that poka-yoke style for the module-coverage assertion.

### Sidecar table + migration — `schema.py` + `repository.py`
- **DDL analog:** `read_model_refresh_runs` (`schema.py:237`) for a small bookkeeping table; new `read_model_logic_version(metric_version BIGINT, logic_fingerprint VARCHAR, changed_at VARCHAR)`. Add the table name to `DUCKDB_TABLES` (`schema.py:9`).
- **Additive-migration analog:** `ensure_provenance_columns` (`schema.py:518`) invoked from `_ensure_schema_extensions` (`repository.py:195`, wrapped in `try/except duckdb.CatalogException`). Seed the singleton row here (insert if absent, fingerprint=current) so the migration is idempotent and runs on every `from_connection`.
- **Helpers analog:** `read_model_status` (`repository.py:649`) for read helpers; `record_read_model_refresh_run` (637) and `_upsert_fact` (605) for the write/bump helper. Add `current_metric_version()`, `current_logic_version()`, `bump_logic_version(version, fingerprint, changed_at)`.

### Trigger + version sourcing — `_sync_ops.py`, `runtime.py`, `worker.py`, `read_model_materializer.py`
- **Chokepoint analog:** `materialize_read_model_stage` (`_sync_ops.py:269`) — insert the stored-vs-live fingerprint compare + bump + `enqueue_metric_version_recompute` BEFORE the `materialize_duckdb_read_model` call. Source `metric_version` from `repo.current_metric_version()` instead of the passed constant.
- **Orphan to wire:** `enqueue_metric_version_recompute` (`repository.py:534`) — call with `reason="logic_fingerprint_changed"`. It already walks `activity_source_state` and enqueues all activities.
- **Constant removal:** delete `CURRENT_METRIC_VERSION` (`repository.py:31`); update default args (`repository.py:408`, `read_model_materializer.py:370`) and call sites (`runtime.py:110,181,273`, `worker.py:62,69`, `metric_services.py:333,340,358,360,406`). Verify with `grep -rn CURRENT_METRIC_VERSION src/`.
- **Log emit analog:** `worker.py::_emit("read_model_materialize_started"/"_ok", ...)` (62-79) — match this structured-event emitter for the recompute event fields.

### R11 aggregate version filter — `aggregate_queries.py`
- **Analog:** `_where_clause` (`aggregate_queries.py:933`) builds the WHERE for all 3 aggregate query builders (numeric 693, distribution 781, 860). Append `metric_version = ?` with the current int. Source the current int via `repo.current_metric_version()` threaded through `query_training_aggregates` (152). Keep `COUNT(DISTINCT metric_version)` (723/805/893) as the tripwire.

### Walk discount — `constants.py`, `metrics.py`, `repository.py`, `read_model_materializer.py`
- **Constant analog:** module-level `SPORT_WALK = "Walk"` (`constants.py:124`) and `Config.Zones.COEFF` (21) — add `WALK_TRIMP_DISCOUNT = 0.5` as a module-level (or `Config`) constant. NO env.
- **Pure-fn analog:** `metrics.py:240 calc_hrr_pct` — pure fn, plain inputs, returns scalar/None, no storage import (respects Phase 10/12 domain boundary). Add a discounted-effective-TRIMP fn.
- **Aggregation analog:** `observed_trimp_history` (`repository.py:1118`, groups TRIMP by day) and `daily_load_points_between` (1208, sets `effective = observed` at line 1298). Add a **per-sport** daily grouping (day+sport_type), multiply the Walk portion by the discount, sum per day → `effective_trimp != observed_trimp`. The materializer consumes `point.effective_trimp` (`read_model_materializer.py:248,280`) unchanged once the repository returns discounted values.

### Time fields — `read_model_materializer.py`, fact registry, `metric_services.py`
- **Materialized-column analog:** `_activity_fact` (`read_model_materializer.py:155-200`) builds the fact dict; `MATERIALIZED_FACT_COLUMN_REGISTRY["activity_metric_facts"]` (`metric_registry.py:1730`) + `_MATERIALIZED_FACT_COLUMN_SQL_METADATA` (1574) define columns. Add `start_time_local VARCHAR` (HH:MM from `start_date_local`) following the `calories_kcal` late-column pattern (`schema.py:287` `ACTIVITY_METRIC_FACT_LATE_COLUMNS`) so it migrates additively.
- **Read-time field analog:** `_activity_payload` (`metric_services.py:273`) already computes `start_time` from `summary.get("start_date_local")[11:16]` (309). For `relative_time`, add a read-time helper that takes `activity` datetime + `now` (the service already has `checked_at`/`now`); follow the `<24h → "Hh Mm"` / `>=1d → "Nd Hh"` rule from RESEARCH.md Code Examples. `relative_time` is NOT materialized (depends on `now`).

## Shared Patterns

- **Hashing:** always `hashlib.sha256(...).hexdigest()` (never `hash()`); see `_semantic_json_hash` (`repository.py:135`).
- **Identifier safety:** any interpolated table/column name routes through `_safe_identifier` (`repository.py:41`); values use `?` placeholders.
- **Additive migration idempotency:** mutate schema only via the `_ensure_schema_extensions` path (`repository.py:195`), guarded by `try/except duckdb.CatalogException` for fresh-DB.
- **Domain boundary (Phase 10/12):** `metrics.py` / `constants.py` MUST NOT import `adapters/` or storage. Repository owns all SQL; pure fns take plain rows.
- **Test fixtures:** `open_fixture_db()` + `create_schema(conn)` then `DuckDBRepository.from_connection(conn)`; reuse helpers `_repo_with_facts` / `_aggregate_fixture` (imported in `tests/test_metric_services.py:21-22`).
- **Structured logs:** `_emit(event_name, **fields)` style (`worker.py`); additive fields, self-explanatory values (diagnostic codes/counts), not opaque booleans.
