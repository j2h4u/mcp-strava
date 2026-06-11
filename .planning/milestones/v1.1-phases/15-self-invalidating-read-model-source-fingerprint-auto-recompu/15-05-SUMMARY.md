---
phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu
plan: 05
subsystem: metric-platform
tags: [read-model, materialized-column, start-time, relative-time, fingerprint, getsource, zero-knob, time-fields]
requires:
  - phase: 15-01
    provides: "compute_logic_fingerprint() + COMPUTE_SOURCE_MODULES (metrics/registry/schema/materializer are in the closure, so the new column + helper flip the fingerprint)"
  - phase: 15-03
    provides: "materialize chokepoint that recomputes facts on a stored-vs-live fingerprint mismatch (auto-backfills start_time_local by construction)"
provides:
  - "parse_local_hhmm(start_date_local) pure-domain helper in metrics.py (fromisoformat + strftime, Z/offset-normalizing, None-safe; NOT a [11:16] slice)"
  - "activity_metric_facts.start_time_local materialized fact column (nullable VARCHAR; additive-late-column migration via ensure_provenance_columns)"
  - "start_time_local on the workout payload sourced from the fact column with a parse_local_hhmm fallback for un-rematerialized rows"
  - "relative_time read-time payload field ('Hh Mm' under 24h; 'Nd Hh' from one day on; '1d 0h' at the 24h boundary); now: datetime threaded into _activity_payload"
  - "Unconditional local inspect.getsource smoke over every COMPUTE_SOURCE_MODULES module + a real docker compose exec packaged-install fingerprint smoke"
affects:
  - "future computed fields added to a fingerprinted module recompute themselves the same way (no manual version bump)"
tech-stack:
  added: []
  patterns:
    - "Materialized column + read-time field split: a stable time-of-day is materialized (start_time_local); a now-dependent recency string (relative_time) is computed at read time and never stored"
    - "One shared pure-domain parser (parse_local_hhmm) reused by both the adapter (materializer) and the application layer (payload), sourced from the layering-neutral metrics.py to avoid an import-direction violation"
    - "Two-tier getsource proof: an unconditional editable-install smoke catches regressions locally; a container-gated docker compose exec smoke proves the packaged pip-install /app layout"
key-files:
  created: []
  modified:
    - "src/mcp_strava/metrics.py"
    - "src/mcp_strava/metric_registry.py"
    - "src/mcp_strava/adapters/duckdb/schema.py"
    - "src/mcp_strava/adapters/duckdb/read_model_materializer.py"
    - "src/mcp_strava/application/metric_services.py"
    - "tests/test_metrics_pure.py"
    - "tests/test_read_model_materialization.py"
    - "tests/test_metric_services.py"
    - "tests/test_metric_registry.py"
    - "tests/test_duckdb_repository.py"
    - "tests/test_logic_fingerprint.py"
    - "tests/test_docker_runtime.py"
key-decisions:
  - "parse_local_hhmm lives in metrics.py (pure-domain, already in COMPUTE_SOURCE_MODULES, already imported by the adapter and importable by the application) so both consumers share it without an import-direction violation"
  - "Renamed the registry metric/payload key start_time -> start_time_local (matches the materialized column and the plan's field name); EnrichedActivity.start_time was a dead field and left untouched (out of scope)"
  - "relative_time is read-time only (now: datetime param threaded into _activity_payload); a future-dated start clamps to '0h 0m' rather than rendering negative"
  - "start_time_local on the payload prefers the materialized fact column, falling back to parse_local_hhmm(summary.start_date_local) ONLY on a NULL un-rematerialized row — the [11:16] slice is gone"
  - "The container-gated docker smoke skips cleanly locally and is exercised by `just test` (which brings the container up first)"
patterns-established:
  - "Pattern 1: a stable derived value is materialized; a now-relative value is computed at read time, never stored"
  - "Pattern 2: a single pure parser shared across the storage boundary, sourced from the pure-domain module to keep layering clean"
requirements-completed: [REQ-TIME, REQ-ZEROKNOB]
duration: 38min
completed: 2026-06-03
---

# Phase 15 Plan 05: Workout Time Fields + Packaged-Install Fingerprint Smoke Summary

**The workout read model now carries finer time granularity: `start_time_local` (HH:MM) is materialized as an additive fact column parsed from `start_date_local` with `fromisoformat` + `strftime` (never a `[11:16]` slice) and surfaced on the payload with a pure-helper fallback, while a read-time `relative_time` ("Hh Mm" / "Nd Hh") is computed against the service clock and never stored — and because the new column + helper live in fingerprinted compute modules, the read model recomputes itself to backfill the column with no manual version bump; an unconditional local `inspect.getsource` smoke plus a real `docker compose exec` smoke prove the fingerprint computes under both the editable and the packaged `pip install /app` layouts.**

## Performance

- **Duration:** ~38 min
- **Started:** 2026-06-03T15:46:00Z (approx)
- **Completed:** 2026-06-03T16:14:00Z
- **Tasks:** 3
- **Files modified:** 12

## Accomplishments
- Added `parse_local_hhmm(start_date_local)` to `metrics.py` — a pure, layering-neutral helper that parses with `datetime.fromisoformat` and formats `strftime("%H:%M")`, normalizing a trailing `Z` to `+00:00`, accepting naive/aware forms, and returning `None` on missing/garbage. It replaces the fragile `[11:16]` slice and is shared by the materializer and the payload.
- Registered `start_time_local` (nullable VARCHAR) in the fact-column registry + SQL metadata and added it to `ACTIVITY_METRIC_FACT_LATE_COLUMNS`, so it migrates additively on live DBs (NULL on old rows until re-materialized) and is generated into the fresh-schema table DDL.
- Populated `start_time_local` in the materializer's `_activity_fact` from `summary_json.start_date_local` via the shared helper.
- Renamed the `start_time` registry metric/payload key to `start_time_local`, added a `relative_time` metric, and exposed both to `list_workouts` + `get_workout_detail`.
- Surfaced `start_time_local` on the payload (fact column source-of-truth, parse fallback on NULL rows) and added a read-time `relative_time` with correct 24h-boundary formatting, threading `now: datetime` through both service signatures and into the compact-rows key set.
- Added an unconditional local `inspect.getsource` smoke over every `COMPUTE_SOURCE_MODULES` module plus a real `docker compose exec` packaged-install fingerprint smoke (gated behind a container-running check).
- Verified end-to-end via `just test`: the live MCP `list_workouts` smoke payload now includes `relative_time` and `start_time_local` in its key set.

## Task Commits

1. **Task 1: materialize start_time_local as an additive fact column** - `a8d44f1` (feat) — helper + registry/metadata/late-column registration + materializer wiring + pure-helper and materializer/migration tests.
2. **Task 2: surface start_time_local + read-time relative_time on workout payloads** - `adace28` (feat) — registry rename + relative_time metric, payload wiring, `now` threading, compact-rows keys, and formatting/boundary tests (plus updated registry/late-column expectation tuples).
3. **Task 3: packaged-install fingerprint getsource smokes** - `7b6e3b7` (test) — unconditional local smoke + container-gated docker compose exec smoke.

## Files Created/Modified
- `src/mcp_strava/metrics.py` - `parse_local_hhmm` pure helper (fromisoformat + strftime, Z/offset-normalizing, None-safe).
- `src/mcp_strava/metric_registry.py` - `start_time_local` fact-column registration (registry + SQL metadata); renamed `start_time` metric to `start_time_local`; added `relative_time` metric; both exposed to `list_workouts` + `get_workout_detail`; plain-language catalog descriptions.
- `src/mcp_strava/adapters/duckdb/schema.py` - `start_time_local` added to `ACTIVITY_METRIC_FACT_LATE_COLUMNS`.
- `src/mcp_strava/adapters/duckdb/read_model_materializer.py` - `_start_time_local` extractor + populated `start_time_local` in the activity fact dict via the shared helper.
- `src/mcp_strava/application/metric_services.py` - `_relative_time` + `_parse_start_dt` read-time helpers; `_activity_payload` gains `now: datetime`, sets `start_time_local` (column → parse fallback) and `relative_time`; `now` threaded into `list_workouts_service`/`get_workout_detail_service`; both keys added to compact_rows.
- `tests/test_metrics_pure.py` - `parse_local_hhmm` cases (naive/Z/offset/microseconds/garbage/date-only).
- `tests/test_read_model_materialization.py` - materializer populates `06:00`; additive migration adds the column and is idempotent.
- `tests/test_metric_services.py` - `_relative_time` formatting + 24h boundary + Z/offset/garbage; payloads carry both fields; no legacy `start_time` key.
- `tests/test_metric_registry.py` - `REQUIRED_METRIC_IDS` updated (`start_time` → `start_time_local`, `+relative_time`).
- `tests/test_duckdb_repository.py` - expected late-column tuple + provenance-column query include `start_time_local`.
- `tests/test_logic_fingerprint.py` - unconditional getsource smoke over every compute module.
- `tests/test_docker_runtime.py` - container-gated real `docker compose exec` packaged-install fingerprint smoke.

## Decisions Made
See `key-decisions` frontmatter. Headline: one shared pure parser sourced from `metrics.py` (no import-direction violation); the materialized stable value (`start_time_local`) is split from the now-relative read-time value (`relative_time`); the registry metric was renamed to match the column.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Live dev DB lacked the Phase-15 `read_model_logic_version` table, crash-looping the rebuilt container**
- **Found during:** Task 3 — bringing the freshly-built container up to run the real `docker compose exec` fingerprint smoke (the plan's Task 3 done criterion).
- **Issue:** `read_model_logic_version` (added to the schema + `DUCKDB_TABLES` in 15-02) is enforced by deploy preflight, but the live dev mirror at `/runtime/data/strava.duckdb` was created before Phase 15 and lacks it. Preflight fails closed BEFORE the repository's idempotent self-heal seed can run, so the rebuilt container crash-looped (`Missing required DuckDB runtime table: read_model_logic_version`). The live DB also lacked the new `start_time_local` column.
- **Fix:** Backed up the live mirror (`strava.duckdb.pre-15-05-sidecar.bak`), stopped the container to release the DuckDB writer lock, and applied the project's OWN migration by opening the DB once via `DuckDBRepository.from_path` (its constructor runs `ensure_provenance_columns` → adds `start_time_local`, and `_seed_logic_version` → creates + adopt-current-seeds the sidecar at the live fingerprint, metric_version=1). No ad-hoc DDL. Recreated the container (healthy) and the smoke passed.
- **Files modified:** none (data migration on the live dev DB only, via the in-code seed path).
- **Commit:** n/a (no source change).
- **Scope note:** This is a Phase-15 *deployment* migration gap (latent since 15-02), not introduced by 15-05. It is logged below under Deferred Issues because the underlying ordering (preflight enforces a table the self-heal seed would create, but runs first) is an architectural decision for the deploy layer, outside this plan's scope.

**Total deviations:** 1 blocking issue auto-resolved (Rule 3, data migration only — no source change). All three tasks executed as written.
**Impact on plan:** None to the code; the live dev instance now boots on the Phase-15 schema and serves the new time fields (confirmed by the live `just test` MCP smoke).

## Deferred Issues

| Category | Item | Status |
|----------|------|--------|
| deploy/preflight | Deploy preflight enforces `read_model_logic_version` (15-02) but runs BEFORE the repository's idempotent self-heal seed that would create it, so a pre-Phase-15 live DB crash-loops instead of self-migrating. Worked around for the dev instance by applying the in-code seed once (see Deviation 1). A durable fix (run the additive sidecar migration before/within preflight, or make preflight tolerant of the self-heal) is an architectural change to the deploy layer, outside 15-05's scope. | Worked around (dev DB migrated); durable fix deferred |

## Issues Encountered
- The running dev container was 2 days old (pre-Phase-15) and unhealthy; rebuilding surfaced the preflight migration gap above. Resolved by migrating the live DB via the in-code seed path and recreating the container.
- Note for reviewers running on a host Python < 3.14: several modules use PEP 758 parenthesis-less `except A, B:` (valid on the project's 3.14 runtime, a `SyntaxError` on 3.13). Always run via `uv run` (3.14), not the host interpreter.

## User Setup Required
None — the live dev DB migration was applied during execution; the container is healthy and serving the new fields.

## Next Phase Readiness
- This is the last plan in Phase 15. The zero-knob auto-recompute now covers a newly-added materialized column by construction, and the workout payload exposes finer time-of-day + recency. The live dev instance boots on the Phase-15 schema.
- One deferred deploy-layer item (preflight vs self-heal ordering) is logged for a future quick task or phase.

## Threat Flags

None — `start_time_local` and `relative_time` introduce no new network/auth/file surface. The two threats in the plan's register (T-15-10 parsing, T-15-11 getsource) are mitigated as specified: parsing is `fromisoformat`/`strftime` in a try/except returning `None`, no eval/format injection; the getsource smokes (local + docker) prove no OSError under either layout.

## Self-Check: PASSED

- FOUND: `src/mcp_strava/metrics.py` (parse_local_hhmm)
- FOUND: `src/mcp_strava/adapters/duckdb/read_model_materializer.py` (start_time_local populated)
- FOUND: `src/mcp_strava/application/metric_services.py` (relative_time + start_time_local on payload)
- FOUND: `tests/test_logic_fingerprint.py` (unconditional getsource smoke)
- FOUND: `tests/test_docker_runtime.py` (docker compose exec packaged-install smoke)
- FOUND commit: `a8d44f1` (Task 1 feat)
- FOUND commit: `adace28` (Task 2 feat)
- FOUND commit: `7b6e3b7` (Task 3 test)
- Gates: `ruff check` clean, `ruff format --check` clean (105 files), `pyright src` 0 errors, full `pytest` 385 passed (was 374 in 15-04; +11 new, no regressions), and `just test` green (unit + Docker build + container healthy + live MCP smoke showing `relative_time`/`start_time_local` in the list_workouts payload).

---
*Phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu*
*Completed: 2026-06-03*
