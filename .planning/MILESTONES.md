# Milestones

## v1.1 DuckDB Analytics (Shipped: 2026-06-11)

**Phases completed:** 16 phases, 71 plans, 131 tasks

**Key accomplishments:**

- Setuptools src-layout package with migrated runtime modules and a working python -m mcp_strava entrypoint
- Typed settings boundary with lazy DB/token path usage, delivered via RED/GREEN/REFACTOR TDD gates
- Fail-closed SQLite mirror open, explicit migration safety gate, and hermetic parity tests for preflight/backup/user_version control.
- SQLite repository boundary now covers activity/stream/zone/kudos/sync metadata access with typed contracts, chunked writes, and AST policy enforcement.
- Repository daily-load contract now exposes REST/UNKNOWN/PARTIAL/OBSERVED while report/analytics/trends/metrics consume repository methods and keep observed training-load parity.
- CLI now exposes explicit DB safety commands while sync/backfill writes are repository-backed and full verification proves no real mirror mutation.
- Dedicated Strava adapter with safe token refresh, dual quota tracking, typed failures, and hermetic fake-collaborator tests
- Lease-backed refresh runtime with daily idempotency, force refresh, backfill stages, freshness states, and hermetic orchestration tests
- SQLite refresh control-plane with v2 migration, lease/checkpoint repository methods, and pending refresh-request dedupe
- Production wiring now routes legacy sync/db/CLI entrypoints through the new adapter and refresh-runtime boundaries
- Shared product service envelope and local freshness metadata with idempotent first-use refresh signaling
- Daily and weekly training analytics wrapped in shared service envelopes with fixture-backed parity tests
- Recent workout and per-workout analytics now run through the application service envelope
- CLI now routes product commands through application services and isolates local operator commands under `admin`
- Complete MCP-facing metric registry with comparison metadata, interpretation exclusions, and anti-drift tests/docs coverage
- Registry-aligned metric services for fitness state, workout list, and workout detail with factual metadata and closed safety warning codes
- Non-root MCP backend Docker runtime with fail-closed SQLite preflight, persistent deploy data mount, and backup-first runtime bootstrap helper
- SQLite v3 mirror foundation now stores stream extra channels losslessly with atomic stream+metadata replacement and admin aggregate coverage reporting.
- Refresh ingestion now requests all configured Strava stream channels, preserves unknown channel content in SQLite, and maintains hot-path analytics projections with atomic row+metadata writes.
- SQLite migration v4 now rebuilds streams to canonical `lat`/`lng`, removes `latlng`, and keeps analytics/runtime parity without Strava API calls.
- Admin-only stream-channel backfill now supports resumable, rate-limit-aware merge updates with dry-run coverage estimates while MCP remains read-only.
- SQLite v5 read-model inventory with pinned migration backup and wide fact-table contracts
- Repository source writes now atomically update source provenance and queue read-model recompute work
- Offline materializer persists activity, daily, training-model, and rolling facts from dirty source rows
- Refresh and backfill now materialize read-model facts below the MCP surface
- MCP metric services now read materialized facts instead of recomputing from raw mirror data
- The read-model MCP path now has explicit latency, query-shape, and Docker validation gates
- DuckDB 1.5.3 is approved, pinned, locked, and guarded by Python 3.14 runtime tests.
- One-shot SQLite backup-to-DuckDB cutover with typed tables, parity checks, active-lease blocking, and admin-only CLI control
- DuckDB primary runtime repository with transactional read-model materialization and SQLite limited to explicit rollback compatibility paths
- DuckDB runtime now starts as one owner process with in-process refresh scheduling, offline startup preflight, and HTTP/owner health checks
- Registry-owned aggregate semantics with typed denominators, bundles, quantiles, and drift-tested metric documentation
- DuckDB bucket and rolling aggregate service over prepared metric facts with registry-owned math, validated product parameters, and factual D-42 metadata
- Six-tool MCP surface with get_training_aggregates and aggregate-backed period comparison over bounded all-time buckets
- Registry-backed daily, weekly, historical, status, kudos, and gear facts over DuckDB read-model aggregates
- Daily, weekly, historical, status, kudos, and mirrored gear fact bundles with explicit completeness contracts over prepared read-model data
- Product CLI daily, weekly, workout, and freshness reads now share read-model-backed application services with MCP-facing code
- Direct MCP product bundle smoke, six-tool boundary guards, and Phase 9 verification docs for factual read-model-backed product surfaces
- 1. [Rule 1 - Bug] _decoupling_invalid and calc_decoupling not removed in Task 2 draft
- transiently prepended `from mcp_strava.db import repository_from_connection  # TRANSIENT-RED-PROOF` to `src/mcp_strava/metrics.py`.
- `src/mcp_strava/adapters/duckdb/read_model_materializer.py`
- Moved 6 inline SQL call sites from read_model_materializer.py into named DuckDBRepository public methods, closing IN-03 (boundary-crossing private helper calls).
- DuckDB connection-lifetime helpers (MirrorConn, ReadConn, thread-local read pool, reset_thread_connections, _db_path) added verbatim into adapters/duckdb/connection.py beside open_expected_mirror_db as the D-01/D-02/D-03 additive step.
- settings.py — D-06 credential accessor
- 1. [Rule 1 - Bug] Fixed Python 2 bare except syntax in metric_services.py
- 1. [Rule 1 - Bug] ruff auto-fix (`--fix`) was destructive on constants.py re-export block
- Widened DuckDB fetch return types to `Row = dict[str, Any]` and annotated `dc_to_dict -> Any`, dropping pyright errors from 359 to 211 (148 cleared).
- Swept all 211 post-Plan-01 pyright errors to 0 by widening `dict[str, object]` → `dict[str, Any]` across 16 files, changing `conn: object` → `conn: Any` in the DuckDB repository, and applying targeted None-guards and one-off D-04 fixes.
- Pinned `typeCheckingMode = "standard"` in pyproject.toml and removed 3 dead `noqa: BLE001` comment suffixes from refresh/worker.py and refresh/health.py.
- Ran the D-08 green gates (`just check` + `just test`) confirming Phase 13 pyright/ruff cleanup is complete with 0 errors, 328 tests passed, Docker build clean, and MCP smoke green.
- Registry-owned SQL metadata and deterministic activity_metric_facts DDL helpers without runtime schema changes.
- DuckDB activity_metric_facts creation and late-column migration SQL now render from registry-owned fact metadata.
- Full local quality gates and scope scan passed for the registry-owned activity fact schema slice.
- 1. [Rule 3 / plan-delegated] COMPUTE_SOURCE_MODULES is the full recursive closure (14 modules), not the plan's literal 8-module compute subset
- 1. [Rule 2 - Missing critical functionality] Structured `_emit` diagnostic for the seed-skip path
- The materialize chokepoint now self-invalidates: a live-vs-stored source-fingerprint mismatch bumps metric_version, mass-enqueues every activity, and recomputes at the just-bumped version — the hand-maintained `CURRENT_METRIC_VERSION` constant is gone and all aggregate/status reads pin to the current version (R11), so a logic edit recomputes itself with no manual step and a mixed-version DB never blends.
- WALK_TRIMP_DISCOUNT (0.5) now discounts the Walk-sport portion of each day's effective TRIMP via a pure per-sport domain fn, so effective_trimp < observed_trimp on walk days and the Banister load model stops counting walks at full load — and because the constant lives in a fingerprinted compute module, editing it auto-recomputes the read model end-to-end (proven by a forced stored!=live fingerprint mismatch driving a real version bump + mass-enqueue + re-materialize).
- The workout read model now carries finer time granularity: `start_time_local` (HH:MM) is materialized as an additive fact column parsed from `start_date_local` with `fromisoformat` + `strftime` (never a `[11:16]` slice) and surfaced on the payload with a pure-helper fallback, while a read-time `relative_time` ("Hh Mm" / "Nd Hh") is computed against the service clock and never stored — and because the new column + helper live in fingerprinted compute modules, the read model recomputes itself to backfill the column with no manual version bump; an unconditional local `inspect.getsource` smoke plus a real `docker compose exec` smoke prove the fingerprint computes under both the editable and the packaged `pip install /app` layouts.
- Closed all four phase-15 review/verification WARNINGs as real bugs via TDD: atomic fingerprint bump+enqueue (no silent under-invalidation), UTC-end-to-end freshness clock (no Almaty-offset staleness skew), lock-honoring failed-run bookkeeping, and whole-day recompute batches (no partial-batch under-count).
- xfail regression guard for kudos window_days branch + Assumption A1 confirmation before 16-02 rewrites the dead SQLite date('now', ?) SQL
- Remove `activities.date VARCHAR` (SQLite dead weight), rewrite kudos `window_days` branch to native DuckDB `CURRENT_DATE - INTERVAL` arithmetic, rename `RepositoryActivityRow.date` → `activity_day`; xfail test from 16-01 now passes.
- Convert `refresh_requests.requested_for_day` from VARCHAR to native DATE; update `enqueue_refresh_request` signature and both callers to pass `datetime.date` objects directly.
- 1. [Rule 2 - Missing critical] Remove unused `cast` import from aggregate_rows.py
- 1. [Rule 1 - Bug] Fix 3 stale test expectations from Phase 16-05

---
