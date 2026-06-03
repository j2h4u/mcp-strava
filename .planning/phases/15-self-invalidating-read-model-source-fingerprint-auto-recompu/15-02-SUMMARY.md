---
phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu
plan: 02
subsystem: metric-platform
tags: [read-model, self-invalidation, metric-version, sidecar, seed-migration, tdd]
requires:
  - "compute_logic_fingerprint() in metric_registry.py (15-01)"
  - "DuckDBRepository + _ensure_schema_extensions construction path"
  - "create_schema DUCKDB_SCHEMA_SQL / DUCKDB_TABLES inventory"
provides:
  - "read_model_logic_version singleton table (DuckDB) + DUCKDB_TABLES entry"
  - "DuckDBRepository.current_metric_version() / current_logic_version() / bump_logic_version()"
  - "current_metric_version memo (one-shot) that bump_logic_version() invalidates"
  - "adopt-current seed in _ensure_schema_extensions (deploy = no recompute)"
affects:
  - "15-03 rewires the materialize chokepoint to read current_metric_version() and bump on fingerprint drift; owns the stored-is-None self-heal branch"
tech-stack:
  added: []
  patterns:
    - "singleton sidecar row id=1 with DuckDB ON CONFLICT(id) DO UPDATE upsert"
    - "one-shot memo attribute cleared at end of the mutator (bump) — single guaranteed invalidation point"
    - "runtime import inside seed + separate inner try/except Exception (log-warn-skip) so a non-CatalogException does not break from_connection()"
    - "structured JSON _emit diagnostic event (mirrors refresh/schema_drift.py)"
key-files:
  created: []
  modified:
    - "src/mcp_strava/adapters/duckdb/schema.py"
    - "src/mcp_strava/adapters/duckdb/repository.py"
    - "tests/test_duckdb_repository.py"
decisions:
  - "Seed adopts the CURRENT live fingerprint (version = fact-table max, else 1) so deploying this phase is a no-op recompute"
  - "bump_logic_version() is the single guaranteed memo-invalidation point (cycle-2 HIGH) — callers never reset the cache"
  - "Fingerprint compute in the seed is guarded by its own try/except Exception; on failure the sidecar is left unseeded and reads fall back, with 15-03's chokepoint owning the self-heal"
metrics:
  duration: "~16 min"
  completed: "2026-06-03"
---

# Phase 15 Plan 02: read_model_logic_version Sidecar + Version Helpers Summary

A `read_model_logic_version` singleton table turns `metric_version` into a system-managed counter sourced from the live logic fingerprint: the repository now reads/bumps the version through `current_metric_version()` / `current_logic_version()` / `bump_logic_version()`, and an idempotent adopt-current seed in `_ensure_schema_extensions` writes the *current* fingerprint at construction so deploying this phase triggers no recompute.

## What Was Built

- **`read_model_logic_version` table** (`schema.py`) — singleton (`id BIGINT PRIMARY KEY`, always `id=1`) with `metric_version BIGINT`, `logic_fingerprint VARCHAR`, `changed_at VARCHAR`. Created with `CREATE TABLE IF NOT EXISTS` in `DUCKDB_SCHEMA_SQL` (alongside `read_model_refresh_runs`) and registered in `DUCKDB_TABLES`. The `IF NOT EXISTS` makes the `create_schema` DDL and the repository seed path idempotent and order-independent — both can run on fresh and live (pre-15-02) DBs.
- **Three repository helpers** (`repository.py`):
  - `current_logic_version() -> dict | None` — the seeded row (`{metric_version, logic_fingerprint, changed_at}`), or `None` when empty/absent (catches `CatalogException` for a partially-migrated DB).
  - `current_metric_version() -> int` — sidecar value, else fall back to `MAX(metric_version)` across the four fact tables, else `1`. Memoized on the instance (`_current_metric_version_cache`, sentinel `None`) to avoid re-scanning the 4-table `UNION ALL` per call.
  - `bump_logic_version(metric_version, logic_fingerprint, changed_at)` — DuckDB `ON CONFLICT (id) DO UPDATE` upsert of the singleton, then **clears the memo** so a post-bump read returns the new int (cycle-2 HIGH).
- **Adopt-current seed** in `_ensure_schema_extensions` (`_seed_logic_version`) — creates the table if missing, and if no `id=1` row exists, inserts `metric_version = fact-table max (else 1)`, `logic_fingerprint = compute_logic_fingerprint()`, `changed_at = now`. Seed = current by construction → first refresh sees `stored == live` → no recompute.
- **Seed robustness** — `compute_logic_fingerprint` is imported at runtime *inside* the seed and the compute + INSERT are wrapped in a dedicated `try/except Exception` that emits a structured `read_model_logic_version_seed_skipped` event and skips seeding. An `ImportError`/`OSError` here is **not** a `CatalogException`, so the constructor guard would not catch it — this independent guard keeps `from_connection()` from breaking. Left-unseeded reads fall back to the fact-table max/1; 15-03's materialize chokepoint owns the `stored is None` self-heal.
- **`_emit` helper** — module-level structured-JSON diagnostic emitter mirroring `refresh/schema_drift.py` / `refresh/worker.py`.
- **Tests** (`tests/test_duckdb_repository.py`, 5 added) — seed adopts the live fingerprint on a fresh DB; bump round-trips both fields; memo invalidation (cycle-2 HIGH); idempotent seed (singleton across repeated `from_connection`); `ImportError` seed-skip + fact-table fallback.

## TDD Gate Compliance

Task 3 is the test-authoring task; the behavior it covers was implemented in Task 2 (committed `8195d53`) immediately before. To prove the new tests are RED-meaningful rather than vacuous, the memo-invalidation test was run against a temporarily-neutered `bump_logic_version` (memo reset removed): it **failed** as expected, then **passed** once the reset was restored. The remaining four tests exercise behavior that does not exist without Task 2's table/helpers. Commit sequence: `feat(15-02)` schema → `feat(15-02)` helpers/seed → `test(15-02)` coverage.

## Deviations from Plan

### Auto-fixed / additive

**1. [Rule 2 - Missing critical functionality] Structured `_emit` diagnostic for the seed-skip path**

- **Found during:** Task 2 — the plan says "log a warning and skip seeding" but the repository module had no logger.
- **Issue:** A silent `except: pass` would hide a transient seed failure, leaving an operator no signal for why the sidecar is unseeded (and reads are on the fallback path).
- **Fix:** Added a module-level `_emit(event, **fields)` that prints a structured JSON event (`read_model_logic_version_seed_skipped` with `error_type` + truncated `error`), matching the existing house style in `refresh/schema_drift.py` and `refresh/worker.py`. Surfaces the diagnostic code/value rather than an opaque skip.
- **Files modified:** `src/mcp_strava/adapters/duckdb/repository.py`
- **Commit:** `8195d53`

**2. [Rule 3 - Blocking detail] `_commit_if_standalone()` after the bump upsert**

- **Found during:** Task 2 — `_execute` does not commit outside an open transaction.
- **Issue:** A standalone `bump_logic_version()` (no surrounding `begin()/commit()`) would otherwise leave the upsert uncommitted; the memo is cleared *after* `_commit_if_standalone()` so the post-bump read sees the persisted row.
- **Fix:** Call `self._commit_if_standalone()` before resetting the memo. No-op inside an open transaction (15-03's recompute path keeps the bump in its materialize transaction), correct for standalone callers/tests.
- **Files modified:** `src/mcp_strava/adapters/duckdb/repository.py`
- **Commit:** `8195d53`

Everything else executed exactly as written.

## Verification

- `uv run pytest -q tests/test_duckdb_repository.py -k "logic_version or seed"` — 5 passed.
- `uv run pytest -q tests/test_duckdb_repository.py` — 13 passed.
- Full suite `uv run pytest -q` — **363 passed** (was 358; +5 new tests, no regressions).
- `uv run ruff check src tests` — clean.
- `uv run ruff format --check src tests` — clean (105 files).
- `uv run pyright src` — 0 errors, 0 warnings.
- Manual: fresh in-memory DB seeds exactly one row whose fingerprint == `compute_logic_fingerprint()`; bump + memo invalidation, idempotent re-seed (singleton), and `ImportError` seed-skip + fallback all verified directly.
- RED-sanity: the memo test fails when `bump_logic_version`'s cache reset is removed, passes when restored.

## Known Stubs

None. The seed writes a live fingerprint; the helpers read/bump real sidecar rows. The `bump_logic_version()` caller (the recompute chokepoint) is intentionally wired in 15-03 — this plan deliberately ships only the version source-of-truth, per the plan's task split and the artifact list.

## Threat Flags

None new. Table/column names are schema-defined literals; all values go through `?` placeholders (matches threat register T-15-01 `mitigate`). The seed's `import_module`/`getsource` targets come from the hard-coded in-repo `COMPUTE_SOURCE_MODULES` tuple, never from runtime or Strava input.

## Self-Check: PASSED

- FOUND: `src/mcp_strava/adapters/duckdb/schema.py` (modified — `read_model_logic_version` DDL + `DUCKDB_TABLES`)
- FOUND: `src/mcp_strava/adapters/duckdb/repository.py` (modified — helpers + seed + memo)
- FOUND: `tests/test_duckdb_repository.py` (modified — 5 logic-version tests)
- FOUND commit: `022e446` (feat: schema table)
- FOUND commit: `8195d53` (feat: helpers + seed)
- FOUND commit: `ece0587` (test: coverage)
