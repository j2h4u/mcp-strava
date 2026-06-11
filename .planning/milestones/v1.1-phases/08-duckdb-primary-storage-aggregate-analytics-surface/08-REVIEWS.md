# Phase 8 Review Convergence

Phase: 08 — DuckDB Primary Storage & Aggregate Analytics Surface
Cycle: 1
Reviewers: claude, opencode
Generated: 2026-05-25

CYCLE_SUMMARY: current_high=2

## Current HIGH Concerns

1. OpenCode H-1: read-model materializer is not explicitly migrated/refit for DuckDB, so refresh/materialization may continue writing SQLite facts or fail after cutover.
2. OpenCode H-2: canonical DuckDB runtime file path is not pinned consistently across migration, settings, Docker, and live cutover plans.

## Claude Review

I reviewed all eight Phase 8 plans against the context, research, patterns, validation strategy, and the current codebase. Overall this is a strong, well-sequenced plan set: dependency waves are coherent (01→{02,05}→03→{04,06}→07→08), data-preservation and rate-limit constraints are respected (migration is local-only, rollback explicitly forbids resync, original SQLite is never mutated), the DuckDB single-owner concurrency risk is correctly identified and assigned to 08-04, and the MCP six-tool boundary is enforced with forbidden-parameter tests. Below are the findings.

## Findings

### MEDIUM

**M1 — 08-02: pinned-backup retention behavior requires `backup.py` but that file is not in scope.**
- Affected: `08-02-PLAN.md` Task 2 acceptance criterion "Pinned SQLite backup remains outside ordinary retention behavior" and pinned naming `strava-pre-phase-8-*.db`.
- Problem: `src/mcp_strava/adapters/sqlite/backup.py:31` hardcodes `_is_pinned_backup` to match only `strava-pre-phase-7-`. A `pre-phase-8` backup would be classified as a regular backup and is prunable by `enforce_backup_retention` once 5+ regular backups exist. The plan's `files_modified` omits `backup.py`, so the acceptance criterion cannot be satisfied as written.
- Mitigating factor (why not HIGH): the live `strava.db` is never mutated by the one-shot migration (DuckDB is a new file), so the original SQLite remains the true rollback source even if the dedicated pinned backup were pruned. The risk is a narrow window before the first accepted refresh.
- Remediation: add `src/mcp_strava/adapters/sqlite/backup.py` to 08-02 `files_modified` and either extend `_is_pinned_backup` to recognize the `strava-pre-phase-8-` prefix (or generalize to `strava-pre-phase-*`), or add a `create_pre_phase_8_backup` helper analogous to `create_pre_phase_7_backup`, with a retention test mirroring `test_safe02_backup_retention_preserves_pinned_pre_phase_7_backup`.

**M2 — 08-07: removing `COMPARE_PERIODS_HANDLERS` will break `test_metric_registry.py`, which is in the verify set but not in `files_modified`.**
- Affected: `08-07-PLAN.md` Task 3 ("Remove or shrink `COMPARE_PERIODS_HANDLERS`, `ACTIVITY_SCALAR_FACTS`, `MODEL_FACTS`, `ROLLING_FACTS`") and its verify command `uv run pytest -q ... tests/test_metric_registry.py`.
- Problem: `tests/test_metric_registry.py:205` (`test_compare_periods_registry_metrics_are_mapped_without_skip_bucket`) asserts `metric_services.COMPARE_PERIODS_HANDLERS` and `COMPARE_PERIODS_SKIP_REASONS` exist and map every compare-exposed registry metric. Removing those symbols per D-25 deterministically fails the verify step, but `test_metric_registry.py` is not listed in Task 3 `files_modified`.
- Remediation: add `tests/test_metric_registry.py` to 08-07 scope and replace the handler-mapping assertion with an equivalent "every compare_periods registry metric resolves through the aggregate layer" assertion, or keep a registry-derived mapping that is not a separate recompute path (satisfying D-25's intent while preserving the contract test).

**M3 — `bucket=all_time` end-bound semantics for `compare_periods` are underspecified.**
- Affected: `08-06-PLAN.md` Task 2 ("`all_time` as one synthetic bucket using caller start or earliest activity day") and `08-07-PLAN.md` D-24 delegation.
- Problem: D-28 only defines the all-time *start* (earliest activity unless caller supplies start). `compare_periods` needs a single bucket bounded by *both* `period_x_start` and `period_x_end`. If `all_time` ignores an explicit end date, period A/B comparisons will silently aggregate beyond the requested window.
- Remediation: state explicitly in 08-06 that `all_time` honors both caller `start_date` and `end_date` as the single half-open bucket bounds, and add a 08-06/08-07 test asserting a bounded `all_time` call does not include activities after `end_date`.

### LOW

- **L1 — 08-03 verify runs `tests/test_settings.py`**, which is not referenced elsewhere and not confirmed to exist; if absent, the verify command errors. Confirm the file exists or adjust the verify set.
- **L2 — Justfile parametrized perf invocation.** Several plans and the validation doc use `just mcp-read-model-perf samples=20 warmup=2 p95_ms=100`. `just` uses positional recipe arguments, so `samples=20` is passed as the literal first positional value, not a named override. The no-arg form (which already defaults to `p95_ms="100"`) is what actually exercises the 100 ms gate. Use positional form `just mcp-read-model-perf 20 2 100` or rely on defaults.
- **L3 — No planned contingency if the 100 ms p95 gate fails.** D-09 defers physical aggregate tables "only if benchmarks prove needed," but no plan covers that fallback. Given the small dataset (~600 activities, ~516 daily facts) and persisted DuckDB views, this is very likely a non-issue, but the roadmap has no insertion point if 08-08 fails the gate.
- **L4 — Phase 8 requirement IDs are not added to `REQUIREMENTS.md`/traceability.** Plans use planning IDs (P8-SC-01..05, P8-D-ALL) covered by `08-SOURCE-AUDIT.md`, but the formal requirements doc still shows Phase 8 "Requirements: TBD." Cosmetic/process gap, not an execution blocker.

## Notes on areas that are correctly handled (no action)
- DuckDB single-owner concurrency: correctly identified; 08-04 removes the separate refresh child process and refits healthcheck to HTTP/owner-process validation (currently `healthcheck.py:60` opens the DB read-write via `validate_runtime_db(quick=True)`, which would conflict under DuckDB — the plan fixes this).
- D-27 Monday week buckets: consistent with DuckDB `time_bucket` week-width default origin (Monday 1970-01-05).
- Migration safety, lease gate (D-03), parity/cast-failure reporting (D-14), and rollback-without-resync (D-06) are thorough.
- SQL-injection surface: aggregate query builders are registry-whitelisted with parameterized values and no caller-supplied table/column/SQL; forbidden-parameter MCP tests cover the boundary.

## Current HIGH Concerns

None.


## OpenCode Review

Now I have all 8 plans. Let me provide a structured review.

---

## Phase 8 Review: DuckDB Primary Storage & Aggregate Analytics Surface

### Overall Assessment

The plans are well-researched and thorough. The dependency graph (Waves 1-6), threat models, verification commands, and acceptance criteria are properly specified. All 46 locked decisions (D-01 through D-46) are traceably covered. Data preservation, MCP boundary, and Strava rate-limit safety are respected throughout.

Below are findings at each severity level.

---

### HIGH Findings

**H-1: Missing read-model materializer migration — read-model facts may not reach DuckDB after cutover**

- **Blocking reason:** After SQLite cutover, the refresh/materialization pipeline must write read-model facts (`activity_metric_facts`, `daily_load_facts`, `training_model_daily`, `rolling_period_facts`) into DuckDB. The current `src/mcp_strava/adapters/sqlite/read_model_materializer.py` writes to SQLite. No plan's `files_modified` list includes this file, and no explicit task creates or refits a DuckDB equivalent. PATTERNS.md lists `src/mcp_strava/adapters/duckdb/read_model_materializer.py` as a planned new file (line 963, "role-match" analog), but no plan assigns a task to create it.
- **Affected plan/files:**
  - 08-03-PLAN.md: The plan modifies `repository.py` and `sync.py` but not the materializer. Task 2 says "DuckDBRepository exposes repository methods consumed by refresh, materializer" — but the materializer itself is never refitted.
  - 08-04-PLAN.md Task 3 says "refresh scheduling runs through the owner process" — but still no explicit materializer task.
  - 08-01 through 08-08: None of the `files_modified` sections include `src/mcp_strava/adapters/sqlite/read_model_materializer.py` or an equivalent new DuckDB file.
- **Concrete remediation:** Add an explicit task to either 08-03 (repository cutover wave) or a net-new plan between 08-03 and 08-04 that: (a) audits the current materializer for SQLite-specific calls, (b) creates `src/mcp_strava/adapters/duckdb/read_model_materializer.py` (or refactors the existing file to accept a repository interface), and (c) adds targeted tests proving fact upserts, dirty-queue clearing, and refresh-run logging all write to DuckDB. Update `files_modified` accordingly.

**H-2: DuckDB runtime file path is ambiguous across plans**

- **Blocking reason:** The concrete DuckDB runtime path is never pinned consistently. RESEARCH.md mentions `/runtime/data/strava.duckdb` (line 678), 08-03 references `.duckdb` generically, 08-04 Task 2 says "the chosen `.duckdb` runtime file", and 08-08 expects `.duckdb`. During live cutover, `MCP_STRAVA_DB_PATH` must point at the exact file. Ambiguity risks the service starting against the wrong file or a missing path on first run.
- **Affected plan/files:**
  - 08-02-PLAN.md: `run_duckdb_cutover(source_sqlite_path, target_duckdb_path, ...)` accepts a target path but doesn't standardize it.
  - 08-03-PLAN.md Task 3: "accept `.duckdb` runtime paths" — no default, no single canonical value.
  - 08-04-PLAN.md Task 2: "Docker env defaults use a `.duckdb` runtime DB path."
  - 08-08-PLAN.md: "the runtime DB path is `.duckdb`" — relative path, not absolute.
- **Concrete remediation:** Pin exactly one canonical DuckDB file path — recommend `/runtime/data/strava.duckdb` (matching the existing `data/` volume pattern and Docker mount point). Add this as the default in settings, assert it in migration docstrings, reference it in Dockerfile/env, and test it in `test_docker_runtime.py`. Document it in `must_haves.truths` of 08-02 or 08-04.

---

### MEDIUM Findings

**M-1: No Docker image version pinning for rollback**

- **Description:** D-06 says rollback means "restore or repoint to the pinned SQLite DB plus previous runtime config/image." But the plan doesn't specify tagging the pre-cutover Docker image so it remains available. If the image is rebuilt during cutover testing, the previous image may be lost.
- **Affected plan:** 08-08-PLAN.md Task 2 (deployment runbook).
- **Remediation:** Add to 08-08 runbook: before cutover, tag the current running image (e.g., `mcp-strava:pre-phase-8`) so rollback can `docker compose` with that image tag, not just the latest build.

**M-2: In-process refresh scheduling needs explicit thread-safety acknowledgement**

- **Description:** 08-04 moves refresh scheduling into the single DuckDB-owning process (from separate child processes). DuckDB's Python client supports multiple threads sharing a connection, but concurrent writes need coordination. The current plan says "in-process refresh scheduling" (08-04 Task 2) but doesn't specify how thread-safe access is assured.
- **Affected plan:** 08-04-PLAN.md Task 2, Task 3.
- **Remediation:** Add a brief note in 08-04 Task 2 behavior section: refresh work runs on a background thread that acquires an explicit lock or uses a dedicated DuckDB connection/cursor; MCP request handlers use a separate read-only cursor or the same connection with appropriate locking. Reference DuckDB's documented thread safety (connection-per-thread or read-only parallel access).

**M-3: `compare_periods` rewrite may silently change public response shape**

- **Description:** 08-07 Task 3 says "Preserve public response fields that existing tests require, but source their values from aggregate rows." The existing `compare_periods` service hand-builds comparison maps with specific keys. Replacing those values with aggregate-row-sourced data could change field names, nesting, or ordering even if intent is preserved.
- **Affected plan:** 08-07-PLAN.md Task 3.
- **Remediation:** Extend `tests/test_metric_services.py` with explicit snapshot/comparison tests of the pre-rewrite and post-rewrite `compare_periods` response shape. Add a step in 08-07 Task 3 to run existing metric services tests before changing the implementation, capture the expected shape, and assert parity.

**M-4: Healthcheck fallback for DuckDB offline mode is underspecified**

- **Description:** 08-04 Task 2 says "Entrypoint validates DuckDB offline before service ownership begins" and "Healthcheck uses HTTP/owner-process readiness." If the DuckDB file is corrupt or inaccessible, the owner process never starts, and the healthcheck can't reach HTTP. There's no explicit startup-healthcheck loop or timeout behavior described for this failure mode.
- **Affected plan:** 08-04-PLAN.md Task 2.
- **Remediation:** Add to 08-04 Task 2 behavior: when the DB owner process fails to start due to DB corruption, entrypoint logs a structured error and exits non-zero. Healthcheck (in compose/Docker context) should have a maximum retry count with backstop exit.

**M-5: `sqlite_scan` / SQLite extension version compatibility risk**

- **Description:** 08-02 Task 2 uses the DuckDB SQLite extension (`sqlite_scan` or `ATTACH ... TYPE sqlite`) for migration. The extension must match the DuckDB version. While RESEARCH.md verified `duckdb 1.5.3` supports this, a version mismatch between the bundled extension and the Python package could cause migration failures.
- **Affected plan:** 08-02-PLAN.md Task 2.
- **Remediation:** Add to 08-02 Task 2 a verification step: after importing `duckdb`, assert `duckdb.sql("SELECT * FROM duckdb_extensions() WHERE extension_name = 'sqlite' AND loaded").fetchone()` succeeds before attempting migration.

---

### LOW Findings

**L-1: 08-06 Task 3 mentions `docs/metrics.md` but 08-05 already updated it.** Both plans touch the docs. No conflict because of wave ordering (wave 4 vs wave 2), but possible merge friction if 08-05 adds content 08-06 then needs.

**L-2: `test_duckdb_concurrency_guards.py` inspects deploy modules at import time.** 08-04 Task 1 says tests "inspect deploy modules and assert no separate refresh child process is launched." Static inspection won't catch dynamic subprocess launches. Consider also a process-level test that starts the service and verifies no child `python` processes with `refresh.worker` arguments appear.

**L-3: 08-01 Task 1 human checkpoint is semi-manual.** The `docker run --rm python:3.14-slim` commands will download a Docker image and run containers — this is slow and may not be feasible in all CI/execution environments. Noted, but acceptable given the explicit `autonomous: false` and `blocking-human` gate.

---

### Current HIGH Concerns

1. **H-1:** Read-model materializer is never migrated to DuckDB — refresh pipeline will write to wrong storage or fail.
2. **H-2:** DuckDB runtime file path is not pinned — risk of misconfiguration at cutover.

`None` if both are resolved per their remediation sections above.

---

# Phase 8 Review Convergence

Phase: 08 — DuckDB Primary Storage & Aggregate Analytics Surface
Cycle: 2
Reviewers: claude, opencode
Generated: 2026-05-25

CYCLE_SUMMARY: current_high=0

## Current HIGH Concerns

None.

## Claude Review

Claude rechecked the revised plans against the previous Cycle 1 HIGHs and found both blocking issues resolved.

- OpenCode H-1, DuckDB read-model materializer/refit: resolved. `08-03-PLAN.md` now creates or explicitly refits `src/mcp_strava/adapters/duckdb/read_model_materializer.py`, requires the post-cutover import path to resolve to the DuckDB writer, and adds tests proving fact writes and dirty clearing land in DuckDB. `08-04-PLAN.md` routes refresh/backfill materialization through that 08-03 entrypoint.
- OpenCode H-2, canonical DuckDB runtime path: resolved. `/runtime/data/strava.duckdb` is now pinned across migration, settings/runtime cutover, Docker/healthcheck/topology, live cutover, rollback, and tests.

New current findings are not HIGH:

- MEDIUM: `avg_hr` and `max_hr` aggregate-source semantics should be pinned explicitly in `08-06`/`08-05` so `compare_periods` parity is not accidentally lost when the row-scanning path is removed.
- MEDIUM: `08-VALIDATION.md` per-task verification map has some mislabeled owning plan numbers, but individual plan verify commands are correct.
- LOW: document that rolling window `42` is computed from `daily_load_facts`, not read from the existing physical `rolling_period_facts` table.
- LOW: DuckDB schema/DML porting details such as sequences, upsert syntax, and row-helper behavior are implied by the plans but should be kept visible during execution.

Claude's conclusion:

## Current HIGH Concerns

None.

## OpenCode Review

OpenCode also rechecked the revised plans and found both Cycle 1 HIGHs resolved.

- H-1 resolved: `08-03` now includes `src/mcp_strava/adapters/duckdb/read_model_materializer.py`, explicitly creates/refits it, and `08-04` routes owner-process refresh through that DuckDB materializer.
- H-2 resolved: `/runtime/data/strava.duckdb` is pinned in `08-02`, `08-03`, `08-04`, and `08-08` for migration, runtime, Docker, healthcheck, live validation, and rollback.

New current findings are not HIGH:

- MEDIUM: `08-04` should state that background refresh exceptions are contained, logged, lease-failed/expired, and retried later without killing the MCP serving thread.
- MEDIUM: `08-03` should specify the repository factory detection rule for `.duckdb` versus SQLite compatibility paths.
- MEDIUM: `08-01` should make the Python 3.14 test-runner guard explicit so developers do not accidentally run tests under system Python 3.13.
- LOW: document the `all_time` bounded-bucket asymmetry.
- LOW: note execution ordering around CLI versus MCP surface file changes.
- LOW: consider the semantic naming of bounded `bucket='all_time'` calls during implementation.

OpenCode's conclusion:

## Current HIGH Concerns

None.
