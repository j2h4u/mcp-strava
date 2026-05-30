---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
status: ready_to_plan
last_updated: 2026-05-30T11:17:44.689Z
last_activity: 2026-05-30
progress:
  total_phases: 13
  completed_phases: 12
  total_plans: 53
  completed_plans: 53
  percent: 92
stopped_at: Phase 12 complete (5/5) — ready to discuss Phase 13
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-26)

**Core value:** Preserve the local Strava mirror and keep trusted training analytics working while the service is refactored into clean core, repository, adapter, CLI, and MCP boundaries.
**Current focus:** Phase 13 — lint and type check cleanup (ruff residual + pyright)

## Current Position

Phase: 13
Plan: Not started
Status: Ready to plan
Last activity: 2026-05-30

## Performance Metrics

**Velocity:**

- Total plans completed: 45
- Average duration: 0 min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 4 | - | - |
| 03 | 4 | - | - |
| 04 | 4 | - | - |
| 05 | 6 | - | - |
| 06 | 4 | - | - |
| 07 | 6 | 247min | 41min |
| 09 | 4 | - | - |
| 10 | 4 | - | - |
| 11 | 1 | - | - |
| 12 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: n/a
- Trend: Stable

*Updated after each plan completion*
| Phase 01 P01 | 6m | 3 tasks | 18 files |
| Phase 01 P02 | 9m | 3 tasks | 4 files |
| Phase 02 P01 | 2100s | 2 tasks | 9 files |
| Phase 02 P02 | 21m | 2 tasks | 4 files |
| Phase 02 P04 | 41min | 3 tasks | 4 files |
| Phase 05-mcp-http-surface-docker-hardening P05-01 | 8 min | 3 tasks | 6 files |
| Phase 05 P05-02 | 3 min | 2 tasks | 6 files |
| Phase 05 P04 | completed in-session | 4 tasks | 11 files |
| Phase 05 P05 | 12 min | 3 tasks | 9 files |
| Phase 05 P06 | completed in-session | 4 tasks | 6 files |
| Phase 06 P01 | 3300 | 3 tasks | 10 files |
| Phase 06 P02 | 35min | 3 tasks | 5 files |
| Phase 06 P03 | 74min | 3 tasks | 8 files |
| Phase 06 P04 | 6 min | 4 tasks | 12 files |
| Phase 07 P07-01 | 44min | 2 tasks | 7 files |
| Phase 07 P07-02 | 10min | 2 tasks | 2 files |
| Phase 07 P07-03 | 8min | 2 tasks | 3 files |
| Phase 07 P07-04 | 78min | 4 tasks | 12 files |
| Phase 07 P07-05 | 45min | 2 tasks | 7 files |
| Phase 07 P07-06 | 62min | 3 tasks | 10 files |
| Phase 08 P08-01 | 7min | 2 tasks | 3 files |
| Phase 08-duckdb-primary-storage-aggregate-analytics-surface P08-02 | 12 min | 3 tasks | 10 files |
| Phase 08-duckdb-primary-storage-aggregate-analytics-surface P08-05 | 10 min | 3 tasks | 4 files |
| Phase 08-duckdb-primary-storage-aggregate-analytics-surface P08-03 | 20min | 3 tasks | 13 files |
| Phase 08-duckdb-primary-storage-aggregate-analytics-surface P08-04 | 9 min | 3 tasks | 15 files |
| Phase 08-duckdb-primary-storage-aggregate-analytics-surface P08-06 | 39min | 3 tasks | 5 files |
| Phase 08-duckdb-primary-storage-aggregate-analytics-surface P08-07 | 12min | 3 tasks | 9 files |
| Phase 09-product-factual-bundles-and-cli-read-model-consolidation P09-01 | 14 min | 3 tasks | 11 files |
| Phase 09-product-factual-bundles-and-cli-read-model-consolidation P09-02 | 12 min | 2 tasks | 4 files |
| Phase 09-product-factual-bundles-and-cli-read-model-consolidation P09-03 | 10 min | 2 tasks | 10 files |
| Phase 09-product-factual-bundles-and-cli-read-model-consolidation P09-04 | 15 min | 2 tasks | 6 files |
| Phase 10 P01 | 8min | 3 tasks | 3 files |
| Phase 10-materialize-unwired-training-metrics-and-enforce-core-domain P02 | 1min | 2 tasks | 1 files |
| Phase 10 P03 | 10min | 2 tasks | 2 files |
| Phase 10-materialize-unwired-training-metrics-and-enforce-core-domain P04 | 2min | 3 tasks | 4 files |
| Phase 12-decouple-db-py-into-focused-modules P01 | 6 | 2 tasks | 1 files |
| Phase 12 P02 | 7 | 3 tasks | 5 files |
| Phase 12 P03 | 8 | 4 tasks | 13 files |
| Phase 12-decouple-db-py-into-focused-modules P04 | 9 | 3 tasks | 8 files |
| Phase 12-decouple-db-py-into-focused-modules P05 | 20 | 2 tasks | 29 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Phase 1: Start with package/settings boundary before deeper adapter/MCP work.
- Phase 2: Treat `data/strava.db` as durable state with mandatory backup/preflight/parity checks.
- Phase 5: Keep MCP read-only and exclude sync/admin/debug capability surface.
- [Phase 01]: Established src/mcp_strava package boundary and module entrypoint via python -m mcp_strava
- [Phase 01]: Deferred console executable remains enforced with no [project.scripts] entry
- [Phase 02]: Runtime paths no longer execute schema-changing DDL; migration gate owns schema changes.
- [Phase 02]: Expected mirror DB open now fails closed with sqlite URI mode=rw.
- [Phase 02]: Repository boundary implemented with focused methods and AST direct-sqlite guard.
- [Phase 02]: Plan 02-04 enforces explicit DB safety commands and repository-backed sync writes.
- [Phase 05-mcp-http-surface-docker-hardening]: Use final MCP tool ids only in metric registry exposure. — Matches D-03 and blocks accidental tool-id drift.
- [Phase 05-mcp-http-surface-docker-hardening]: Exclude interpretation labels and preserve numeric/model metrics only. — Implements D-02 and D-18 by keeping MCP factual.
- [Phase 05]: 05-02 explicit metric projection for get_fitness_state payloads — Avoid serialize-then-filter of report outputs
- [Phase 05]: 05-02 closed safety warning code table — Keep warning contract machine-readable and bounded
- [Phase 05]: MCP HTTP surface restricted to exact five read-only metric tools. — Enforces D-03/D-06 and prevents sync/admin/debug/raw exposure.
- [Phase 05]: just test now runs through uv-managed python3. — Ensures pinned MCP SDK dependency resolves during full test execution.
- [Phase 05]: Docker runtime defaults use expose-only compose networking with no host ports by default.
- [Phase 05]: Container startup now fails closed through deploy preflight before MCP HTTP server exec.
- [Phase 05]: prepare_runtime writes canonical live.env paths under /opt/docker/mcp-strava for live CLI/admin alignment.
- [Phase 05]: Gateway live-path checks allow dry-run but require --apply + --confirm-live-gateway for mutation.
- [Phase 05]: Gateway registration mutates catalog/compose atomically with rollback restart on failure.
- [Milestone v1.1]: Make Strava stream mirroring lossless-normalized; analytics columns become hot-path projections, not the only stored copy.
- [Milestone v1.1]: Unify mixed GPS storage formats locally before relying on track data as a clean mirror surface.
- [Phase 06]: SQLite remains the primary mirror database; DuckDB is deferred as a possible future analytics/read-model layer.
- [Phase 06]: SQLite user_version advanced to 3 with lossless stream inventory — Phase 06-01 requirements MIRROR-01/STREAM-02 require stream metadata and extra channel retention.
- [Phase 06]: Schema inventory is version-aware by PRAGMA user_version — Keeps v3 latlng contract separate from reserved v4 migration scope.
- [Phase 06]: mirror-coverage is admin-only — Operational coverage controls must not cross into product/MCP boundaries.
- [Phase 06]: Use time as canonical point index for all-channel projection and tolerate uneven channel lengths. — Keeps refresh ingest resilient to sparse/uneven channels without dropping activity-level ingestion.
- [Phase 06]: Persist requested-but-absent channels as unavailable metadata rather than failing stream ingestion. — Preserves observability and supports planned backfill/merge flows without destructive replacement behavior.
- [Phase 06]: Phase 06-03 canonical runtime stream schema is v4 with lat/lng plus values_json and no streams.latlng
- [Phase 06]: Migration reports malformed/conflict counts from pre-migration scan while preserving scalar GPS precedence
- [Phase 06]: Stream-channel backfill runs only for activities with existing stream rows and streams endpoint only.
- [Phase 06]: Daily refresh and legacy backfill reject stream-channel backfill checkpoints explicitly.
- [Phase 06]: Runtime preflight accepts v3 intermediate and enforces v4 as final no-latlng schema.
- [Phase 07]: Runtime schema target is now user_version=5 for read-model tables.
- [Phase 07]: Pre-Phase-7 backups use a pinned filename class and are excluded from ordinary retention pruning.
- [Phase 07]: Dirty invalidation is owned by repository source-write methods, not refresh orchestration.
- [Phase 07]: Non-semantic timestamp and batch fields are excluded from source hashes.
- [Phase 07]: Materializer runs below MCP and writes metric-versioned SQLite facts from repository dirty rows.
- [Phase 07]: Dirty rows clear only in the same successful transaction as facts and run audit.
- [Phase 07]: Refresh, legacy backfill, and stream-channel backfill now call the same read-model materialization stage below MCP.
- [Phase 07]: Read-model materialization lease renewal must not commit an already-active materializer transaction.
- [Phase 07]: Read-model materialization remains runtime-owned automation only; MCP enforces the exact five product tools rather than a redundant forbidden-name list.
- [Phase 07]: Phase 7 self-UAT passed against Docker MCP with live v5 read-model facts and sub-500ms p95 for all product tools.
- [Quick 260524-v31]: Docker/runtime Python baseline is Python 3.14.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Use admin duckdb-cutover as the local admin storage migration command. — Keeps migration local-admin only and gives later plans a stable command name.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Create the final DuckDB runtime file only after backup, lease, cast, and parity gates pass. — Protects local data and avoids failed cutovers mutating the canonical target path.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Allow direct SQLite access outside the SQLite adapter only in the migration-only DuckDB cutover module. — Preserves direct-SQLite guard coverage while allowing stopped-source backup and parity migration reads.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Aggregate semantics stay in metric_registry.py through typed metadata instead of alternate pseudo metric ids. — Preserves current metric ids and keeps aggregate math centralized for DuckDB query builders.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Metric bundles are scenario-oriented registry data and do not change the existing five-tool MCP allowlist. — Keeps this plan as a registry prerequisite; the get_training_aggregates handler is added later.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Weighted heart-rate aggregate metadata requires explicit denominator and weight columns. — Prevents silent fallback to naive averages for HR aggregate rows.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: DuckDBRepository is the primary runtime repository for DuckDB MCP_STRAVA_DB_PATH values. — Plan 08-03 cut runtime repository routing over to DuckDB while preserving the neutral MCP_STRAVA_DB_PATH setting.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Explicit SQLite paths remain reachable only as rollback, migration, and test-fixture compatibility. — Full-suite verification still needs historical SQLite fixtures and rollback input paths, but runtime DuckDB paths must not shadow-write SQLite.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Refresh materialization statically routes live DuckDB repositories to the DuckDB materializer. — This satisfies Review H-1 by preventing live DuckDB storage from calling the SQLite materializer after cutover.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: DuckDB container runtime uses one owner process with in-process refresh scheduling and per-thread DuckDB connections. — Enforces D-13 and prevents multiple read-write DuckDB owners.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Docker healthcheck validates owner-process state and HTTP readiness instead of opening the live DuckDB file. — Keeps health probes from contending with the live DuckDB owner.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Standalone refresh.worker refuses live DuckDB container mode. — Refresh remains automatic below MCP through the owner process only.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Aggregate queries use DuckDB views and whitelisted registry metadata, not caller-supplied storage names or SQL.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: All-time buckets keep caller bounds when supplied and otherwise default start to the earliest local activity before the exclusive end.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Aggregate service validation happens before opening or executing query work for invalid product parameters.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Expose get_training_aggregates as the sixth and only new product MCP tool. — Implements D-15/D-16 while preserving the product-only MCP allowlist.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Format compare_periods from two bounded period_comparison aggregate requests with bucket=all_time. — Implements D-23 through D-25 and removes separate comparison row-scanning semantics.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Use aggregate scope=both internally for comparison bundles. — Allows global and per-sport aggregate rows to share one registry-backed comparison path without adding public MCP controls.
- [Phase 09-product-factual-bundles-and-cli-read-model-consolidation]: Product fact bundles are assembled in application services from existing aggregate, metric, status, and workout-detail services. — Keeps CLI and MCP consumers on the same factual read-model contract without adding MCP tools.
- [Phase 09-product-factual-bundles-and-cli-read-model-consolidation]: Aggregate service responses preserve rows and add bundle payloads only for daily_brief, weekly_digest, and historical_facts. — Keeps existing aggregate callers compatible while giving scenario bundles product-shaped sections.
- [Phase 09-product-factual-bundles-and-cli-read-model-consolidation]: Supported gear facts are emitted only from mirrored summary/detail fields with gear_data_not_mirrored completeness when absent. — Preserves the no-Strava-call and no-aggregate-gear-filter boundary.
- [Phase 09-product-factual-bundles-and-cli-read-model-consolidation]: CLI daily and weekly product reads now call product fact bundle services instead of legacy report recomputation. — Keeps CLI and MCP consumers on the same factual read-model contract.
- [Phase 09-product-factual-bundles-and-cli-read-model-consolidation]: CLI workout list/detail reads now call metric_services read-model services, including filter forwarding and detail-only kudos/gear facts. — Preserves product capability without reviving legacy activity, gear, or kudos commands.
- [Phase 09-product-factual-bundles-and-cli-read-model-consolidation]: Legacy application.reports and application.workouts modules were retired rather than retained as compatibility aliases. — The project has no current runtime compatibility need for old service names.
- [Phase 09-product-factual-bundles-and-cli-read-model-consolidation]: Direct MCP bundle smoke covers daily_brief, weekly_digest, and historical_facts through get_training_aggregates without adding MCP tools.
- [Phase 09-product-factual-bundles-and-cli-read-model-consolidation]: Scenario bundle smoke uses bounded start/end dates only; explicit as_of_day and window_days remain cache-identity inputs but are not valid shared parameters for mixed scenario bundle smoke.
- [Phase 09-product-factual-bundles-and-cli-read-model-consolidation]: Phase 9 verification uses direct server MCP smoke and excludes gateway registration, gateway mutation, sync, raw, token, log, and recompute commands from product verification.
- [Phase ?]: metrics.py is now a pure domain module — no storage import; four pure functions take plain dict rows; dead conn-coupled functions removed
- [Phase ?]: Domain import-boundary guard widened to forbid mcp_strava.db and mcp_strava.adapters.duckdb across five domain modules
- [Phase ?]: metric_version NOT bumped in 10-03 — only defaults replaced with computed values; no formula or column-set changes
- [Phase ?]: MirrorConn collapses _open_storage_connection alias — calls open_expected_mirror_db directly in adapters/duckdb/connection
- [Phase ?]: init_db NOT relocated to connection.py — dead code per RI-03, deleted with db.py in 12-05
- [Phase ?]: D-06 cred accessor in settings.py — load_settings stays cred-free; STRAVA_CLIENT_* NOT in _KEYS
- [Phase ?]: Single _build_strava_transport helper shared by StravaClient and build_refresh_collaborators
- [Phase ?]: StravaClient.api_request drops token= param (GP-02: zero live callers)
- [Phase ?]: RealClock/RealSleeper wave-3 compat aliases removed; cli.py fully migrated to MirrorConn/DuckDBRepository/StravaClient/SystemClock/SystemSleeper; init_db DDL guard removed
- [Phase ?]: constants.py re-export block uses noqa: E402,F401,I001 — ruff --fix is destructive on aliased re-exports at module tail

### Roadmap Evolution

- Phase 8 planned: DuckDB Primary Storage & Aggregate Analytics Surface
- Phase 9 added: Product factual bundles and CLI read-model consolidation
- Phase 10 added (2026-05-29): Materialize unwired training metrics + enforce core/domain storage boundary — completes the deferred 260525-jpo preserve-and-fix decision and closes the core/domain-separation requirement. Rich CONTEXT.md seeded; ready for /gsd-plan-phase 10.
- Phase 11 added (2026-05-29): Tidy materializer repository access — Phase 10 code-review cleanup (IN-03), swap 6 inline-SQL call sites in read_model_materializer.py for named DuckDBRepository methods. Cosmetic/low-risk.
- Phase 12 added (2026-05-29): Decouple db.py — split connection mgmt, repo factories, token/OAuth, and Strava HTTP out of the 237-line db.py grab-bag. The last real coupling hotspot; independent of Phase 11 (different files).

### Pending Todos

None yet.

### Blockers/Concerns

- RESOLVED (2026-05-27): Phase 08 08-08 100 ms p95 gate. Root cause was per-call DuckDB connection churn (~28 ms) + a duplicate read-model schema check. Fixed with thread-local read-connection reuse + per-instance memoization of `_read_model_enabled`. After Docker rebuild the gate passes with margin (formerly-failing tools now p95 34–50 ms vs the 100/118/132 ms failures); full suite 301 passed; 08-08-SUMMARY.md written.
- Deferred (non-blocking): `get_training_aggregates:weekly_digest` is the heaviest remaining tool (~77–81 ms p95). Next lever is the `read_model_status` envelope recompute per read (4× `SELECT DISTINCT metric_version`) — a cache-window-vs-liveness design call, not a regression.
- RESOLVED (2026-05-28): git-history PII filter. Two-pass `git filter-repo --replace-text` over consolidated `main`: targeted DOB forms (`1974-08-15`, `datetime(1974, 8, 15)`, `(1974, 8, 15)`, `15 авг 1974`, `born 1974`), name (`\bMaxim\b` regex + literal `Максим` second pass — `\b` does not match Cyrillic in byte-mode), `age 51`, and `Almaty`/`Алматы`. Verified zero hits across 365 rewritten commits; `uv.lock` `size = 1974605` and English word `Maximize` untouched (collateral checks passed).
- RESOLVED (2026-05-28; corrected 2026-05-29): HR_REST landmine. Operator value (53, as `MCP_STRAVA_HR_REST`) lives in the single canonical untracked `/opt/docker/mcp-strava/.env`, which the container mounts at `/runtime/.env` and Settings loads via `MCP_STRAVA_TOKEN_PATH=/runtime/.env` — physiology stays out of git. (The earlier separate `/opt/docker/mcp-strava/runtime.env` + `env_file:` directive were removed as DRY/YAGNI; config is now the one `.env`.) Owner process still fails fast at startup if the refresh worker is enabled and HR_REST is unset (`deploy/service.py::_require_hr_config_for_worker`), so a misconfigured runtime aborts on boot instead of failing lazily on first materialization. Read-only deployments (worker disabled) are not blocked. Three focused tests cover the three paths.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-05-30T11:01:01.010Z
Stopped at: context exhaustion at 79% (2026-05-30)
Resume file: None

### Post-milestone admin-CLI cleanup (tasks 10-13) — CLOSED 2026-05-28

- Task 10 (spike): ATTACH READ_ONLY does NOT bypass DuckDB's cross-process writer lock — confirmed.
- Task 11 (commit 3b38f59): friendly `MirrorDbLocked` error + `just admin <cmd>` wrapper.
- Task 12 (commit 9f11af5): merged `admin backfill` + `admin backfill-streams` -> `admin catchup`; removed `admin mirror-refresh` (daily refresh is worker-owned). Renamed runtime fns `run_backfill -> run_catchup`, `run_backfill_stream_channels -> run_stream_channel_catchup` (kept public — the refresh worker calls the stream variant). Persisted Stage enum strings unchanged.
- Task 13 (commit 3571eba): `admin compact` reclaims DuckDB disk via `COPY FROM DATABASE` + atomic swap + pre-compact backup. Deliberately NOT auto-invoked from catchup — fetching (network) and compaction (disk) are orthogonal; catchup inserts rows and creates no reclaimable dead space. The 764 MB bloat is one-time Phase-8 migration aftermath; run `just admin compact` once to shrink it.
- Full suite: 307 passed.

## Quick Tasks Completed

| Quick Task | Date | Summary |
|------------|------|---------|
| 260522-ra3 set default Strava mirror refresh cadence to one hour | 2026-05-22 | `.planning/quick/260522-ra3-set-default-strava-mirror-refresh-cadenc/260522-ra3-SUMMARY.md` |
| 260524-kiy add persistent MCP test client and tool-call logging | 2026-05-24 | `.planning/quick/260524-kiy-add-persistent-mcp-test-client-tool-call/260524-kiy-SUMMARY.md` |
| 260524-p6j remove read-model materialization admin surface | 2026-05-24 | `.planning/quick/260524-p6j-remove-read-model-materialization-admin-/260524-p6j-SUMMARY.md` |
| 260524-u5f live Phase 7 DB cutover | 2026-05-24 | `.planning/quick/260524-u5f-live-phase-7-db-cutover-backup-opt-docke/SUMMARY.md` |
| 260524-v31 bump Docker/runtime Python baseline to 3.14 | 2026-05-24 | `.planning/quick/260524-v31-bump-docker-runtime-python-baseline-to-3/260524-v31-SUMMARY.md` |
| 260524-xa9 add metric registry calculation descriptions | 2026-05-25 | `.planning/quick/260524-xa9-add-metric-registry-calculation-descript/260524-xa9-SUMMARY.md` |
| 260525-ng3 Hermes prompts and metric polish | 2026-05-25 | `.planning/quick/260525-ng3-hermes-prompts-metric-polish/260525-ng3-SUMMARY.md` |
| 260526-lal centralize materialized analytic fact registry and add drift audit | 2026-05-26 | `.planning/quick/260526-lal-centralize-materialized-analytic-fact-re/260526-lal-SUMMARY.md` |
| 260527-nbq compute HR zones on the fly and drop hardcoded athlete HR constants | 2026-05-27 | `.planning/quick/260527-nbq-wire-hr-zone-computation-on-the-fly-into/260527-nbq-SUMMARY.md` |
