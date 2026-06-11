# Phase 15: Self-Invalidating Read-Model — Research

**Researched:** 2026-06-03
**Domain:** DuckDB materialized read-model versioning; Python source-hash logic fingerprinting (`inspect.getsource`); Banister load-model domain math
**Confidence:** HIGH (codebase facts grounded at file:line; stdlib behavior verified against CPython docs)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Zero-knob auto-recompute** is the headline. Change a constant/formula/computed field → affected facts recompute automatically on the next refresh cycle. No manual version bump, no manual recompute trigger.
- **Logic fingerprint = whole-module source hash.** `COMPUTE_SOURCE_MODULES` is an explicit tuple in `metric_registry.py` naming the compute surface as **modules**: `metrics`, `cardiac_drift`, `training`, `hr_zones`, `constants`, `adapters.duckdb.read_model_materializer`, `adapters.duckdb.repository`. `compute_logic_fingerprint()` = `sha256` over the concatenated `inspect.getsource(import_module(m))` per module, sorted. Text-based (NOT `co_code`, NOT builtin `hash()`).
- **Keep the int.** `metric_version` stays a `BIGINT` (load-bearing in 4 composite PKs + every read filter + `v_metric_version_status`). New singleton table `read_model_logic_version(metric_version BIGINT, logic_fingerprint VARCHAR, changed_at VARCHAR)`. Delete the hand-maintained `CURRENT_METRIC_VERSION = 1`; reads/materializer source the int from the table via `repo.current_metric_version()`.
- **Trigger at a single chokepoint:** top of `materialize_read_model_stage` (`refresh/_sync_ops.py:269`). Compare stored vs live fingerprint; on mismatch bump int + `bump_logic_version` + wire the orphan `enqueue_metric_version_recompute(new, reason="logic_fingerprint_changed", ...)`. Materialize at `repo.current_metric_version()`.
- **Migration seeds fingerprint = current** so the first run after deploy does NOT spuriously recompute. Empty/fresh DB → adopt-current silently, no recompute.
- **R11 fix (required):** add `metric_version = current` to the aggregate query `WHERE` (`aggregate_queries.py`) so weekly/monthly digests pin the current version and never blend old+new mid-recompute. Keep `metric_version_count` as a tripwire.
- **Observability:** on auto-recompute emit a log event with `stored_fingerprint`, `current_fingerprint`, `reason`, `activities_enqueued`, `queued_at`; extend materialize-ok event with `metric_version` + `duration_ms`; stamp `trigger_reason="logic_fingerprint_changed"` on the refresh-run record.
- **Walk discount:** `WALK_TRIMP_DISCOUNT = 0.5` internal constant in `constants.py` (NO env). Pure domain function in `metrics.py` computing discounted daily effective TRIMP; per-sport daily aggregation in `repository` (group by day+sport, multiply Walk by discount, sum); wired in the materializer so `effective_trimp != observed_trimp` for Walk. Because `constants.py` is in `COMPUTE_SOURCE_MODULES`, changing the discount flips the fingerprint → history auto-recomputes (first real proof of the zero-knob outcome).
- **Time fields:** `start_time_local` (HH:MM) materialized fact column derived from `start_date_local`; surfaced in the workout payload. `relative_time` computed at READ time in the service layer (depends on `now`): `< 24h → "Hh Mm"`; `>= 1 day → "Nd Hh"` (minutes dropped).

### Claude's Discretion
- Exact migration mechanism (additive `CREATE TABLE IF NOT EXISTS` in the `_ensure_schema_extensions` path vs `schema_migration_log` entry) — pick the one consistent with the existing additive-migration pattern.
- Log event field names / emitter (must match existing structured-log conventions in the refresh layer).
- Helper placement for `current_metric_version()` / `current_logic_version()` / `bump_logic_version()` on the repository.

### Deferred Ideas (OUT OF SCOPE — do NOT build)
- Per-metric fingerprinting (whole-model epoch only).
- AST import-walk auto-discovery of the module set (explicit tuple + completeness test instead).
- Synchronous blocking recompute on read (async dirty-queue path only).
- Second entrypoint trigger (single chokepoint only).
- Old-version reaper (deferred; over-retention is a non-concern on a single dev DB).
- Manifest-of-constant-values fingerprint (OVERRULED — reintroduces the hand-maintained knob).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-ZEROKNOB | Zero-knob read-model auto-invalidation: change a constant/field/logic → affected facts recompute automatically | `compute_logic_fingerprint()` over `inspect.getsource` of `COMPUTE_SOURCE_MODULES`; sidecar `read_model_logic_version` table; trigger at `materialize_read_model_stage`; wire orphan `enqueue_metric_version_recompute` (`repository.py:534`); R11 aggregate version filter (`aggregate_queries.py:_where_clause`) |
| REQ-WALK | Port forgotten Hermes `WALK_TRIMP_DISCOUNT` so walks stop counting at full TRIMP in the Banister load model | `WALK_TRIMP_DISCOUNT=0.5` in `constants.py`; pure fn in `metrics.py`; per-day-per-sport aggregation in `daily_load_points_between`/`observed_trimp_history` (`repository.py:1118,1208`); materializer `effective != observed` for Walk |
| REQ-TIME | Finer workout time granularity (start HH:MM + relative "Nd Hh"/"Hh Mm" ago) | `start_time` already read at read-time (`metric_services.py:309`); decision is to **materialize** `start_time_local` as a fact column + add read-time `relative_time` in service layer |
</phase_requirements>

## Summary

This is a **pure internal refactor + 3 features** phase against a DuckDB materialized read-model. No new packages, no external services, no network. The headline mechanism replaces a hand-maintained `CURRENT_METRIC_VERSION = 1` integer with a self-bumping monotonic counter driven by a **source-text logic fingerprint**: a `sha256` over `inspect.getsource()` of an explicit tuple of "compute surface" modules. When any constant, formula, SQL-builder, or computed field inside those modules changes, the concatenated source text changes, the fingerprint changes, and a single chokepoint at `materialize_read_model_stage` bumps the version and enqueues every activity for recompute — wiring the already-written-but-orphan `enqueue_metric_version_recompute` (`repository.py:534`).

The existing infrastructure is almost entirely in place: a dirty-queue (`metric_dirty_activities`), a drain loop (`materialize_read_model`), per-activity source-hash invalidation, and read filters that already pin `metric_version` by exact equality on the **point-read** paths. The two real gaps are (1) the version is a frozen constant nobody bumps, and (2) the **aggregate** read path does NOT filter by version (it only counts `COUNT(DISTINCT metric_version)` as a diagnostic — `aggregate_queries.py:723,805,893`), so a weekly/monthly digest read mid-recompute could blend old+new rows (R11). Both are surgical fixes.

**Primary recommendation:** Two waves. Wave 1 builds the auto-invalidation infrastructure (sidecar table + fingerprint fn + trigger + version-sourcing + R11 aggregate filter + completeness/determinism tests). Wave 2 adds the two features that *ride* the mechanism (Walk discount, time fields) — both flip the fingerprint, which exercises the auto-recompute end-to-end and is the acceptance proof for Wave 1.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Logic fingerprint computation | Domain/registry (`metric_registry.py`) | — | `inspect.getsource` over module set; no storage; `metric_registry` already owns the compute-surface inventory |
| `WALK_TRIMP_DISCOUNT` constant | Domain (`constants.py`) | — | All tunables live in `Config`/module-level constants; in `COMPUTE_SOURCE_MODULES` so changes auto-invalidate |
| Walk discount pure fn | Domain (`metrics.py`) | — | Pure function over plain rows; domain layer cannot import storage (Phase 10/12 boundary) |
| Per-sport daily TRIMP aggregation | Storage (`adapters/duckdb/repository.py`) | — | SQL group-by-day+sport lives at the repository boundary |
| Sidecar version table + helpers | Storage (`repository.py` + `schema.py`) | — | Persistence + DDL belong at the adapter |
| Trigger / version sourcing | Refresh orchestration (`refresh/_sync_ops.py`, `runtime.py`, `worker.py`) | Storage | The chokepoint is the materialize stage; runtime/worker are call sites |
| R11 aggregate version filter | Storage (`aggregate_queries.py::_where_clause`) | — | WHERE-clause builder for digest reads |
| `start_time_local` materialized column | Storage (materializer + fact-column registry) | — | New fact column derived from source `start_date_local` |
| `relative_time` read-time field | Application (`metric_services.py`) | — | Depends on `now`, not materialized — pure read-layer formatting |

## Standard Stack

No new dependencies. The mechanism uses only the Python standard library and the existing DuckDB adapter.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `hashlib` (stdlib) | py3.14 | `sha256` over concatenated module source | Deterministic across processes/PYTHONHASHSEED; already used in `repository.py:3` for `_semantic_json_hash` |
| `inspect` (stdlib) | py3.14 | `inspect.getsource(module)` to read compute-surface source text | Reads `.py` source; works under `pip install /app` because source ships in site-packages |
| `importlib` (stdlib) | py3.14 | `import_module(name)` to resolve module objects from the explicit tuple | Avoids hard import cycles; resolve lazily inside the fingerprint fn |
| `duckdb` | >=1.5.3,<1.6 | Sidecar table, version filter, fact column | Existing adapter |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `inspect.getsource` source hash | `function.__code__.co_code` bytecode hash | REJECTED in CONTEXT: `co_code` is not guaranteed stable across CPython point releases and excludes constants/SQL-string literals' *semantic* placement; source text is the stable, complete unit |
| `inspect.getsource` | builtin `hash()` of source | REJECTED: `hash()` of str is salted by PYTHONHASHSEED per-process → non-deterministic across processes. `sha256` is stable |
| Explicit module tuple | AST import-walk auto-discovery | REJECTED in CONTEXT (over-engineered); explicit tuple + a completeness test (poka-yoke) is the chosen safety net |

**Installation:** None — stdlib + existing deps.

## Architecture Patterns

### System Architecture Diagram

```
                        ┌─────────────────────────────────────────────┐
   refresh cycle ──────▶│  materialize_read_model_stage (_sync_ops.py) │  ◀── SINGLE CHOKEPOINT
   (runtime.py:108/179, │                                              │
    worker.py:69)       │  stored = repo.current_logic_version()       │
                        │  live   = compute_logic_fingerprint()        │
                        │  if stored.fingerprint != live:              │
                        │     new = stored.metric_version + 1          │
                        │     repo.bump_logic_version(new, live, now)  │──▶ read_model_logic_version (sidecar)
                        │     repo.enqueue_metric_version_recompute(new)│──▶ metric_dirty_activities (all rows)
                        │  materialize_read_model(repo,                │
                        │      metric_version=repo.current_metric_version())
                        └───────────────────┬──────────────────────────┘
                                            │
                          ┌─────────────────▼─────────────────┐
                          │  materialize_read_model            │  drains dirty queue, writes facts
                          │  (read_model_materializer.py)      │  at the new metric_version
                          └─────────────────┬─────────────────┘
                                            │
         point reads ────────┐    ┌─────────▼──────────┐    ┌──── aggregate reads (digests)
         (list_workouts,     │    │  fact tables       │    │     query_training_aggregates
          get_fitness_state) │    │  *_facts / _daily  │    │     ── R11 FIX: WHERE metric_version = current
         WHERE metric_version│───▶│  (versioned PKs)   │◀───│        in _where_clause
            = current (exact)│    └────────────────────┘    │
                             └─────── either zero-new OR complete-new, never blended ───────┘

  compute_logic_fingerprint() = sha256( sorted( inspect.getsource(import_module(m))
                                                 for m in COMPUTE_SOURCE_MODULES ) )
```

### Pattern 1: Source-text logic fingerprint (dbt `state:modified` analog)
**What:** Hash the *source text* of a fixed set of compute modules. Any edit (constant value, formula, SQL string, new field) moves the hash. The unit is the **module**, so coverage is automatic-by-construction — adding a symbol inside a hashed module needs zero list edits.
**When to use:** "Recompute when the logic changed" without a hand-maintained version int or per-symbol registry.
**Example (verified stdlib behavior):**
```python
# Source: CPython docs — inspect.getsource / hashlib
import hashlib
from importlib import import_module
import inspect

COMPUTE_SOURCE_MODULES = (
    "mcp_strava.metrics",
    "mcp_strava.cardiac_drift",
    "mcp_strava.training",
    "mcp_strava.hr_zones",
    "mcp_strava.constants",
    "mcp_strava.adapters.duckdb.read_model_materializer",
    "mcp_strava.adapters.duckdb.repository",
)

def compute_logic_fingerprint() -> str:
    sources = sorted(inspect.getsource(import_module(m)) for m in COMPUTE_SOURCE_MODULES)
    digest = hashlib.sha256()
    for src in sources:
        digest.update(src.encode("utf-8"))
        digest.update(b"\x00")  # delimiter so concatenation is unambiguous
    return digest.hexdigest()
```
**Note:** `import_module("mcp_strava.adapters.duckdb.repository")` from inside `metric_registry.py` is a runtime (not top-level) import — it is resolved lazily inside the function to avoid a circular import (repository imports schema which imports metric_registry).

### Pattern 2: Singleton sidecar table seeded at current (no spurious first recompute)
**What:** A one-row `read_model_logic_version` table. The migration seeds `(metric_version=<current max present, else 1>, logic_fingerprint=compute_logic_fingerprint(), changed_at=now)`. Because stored == live by construction on first run, the trigger's `!=` is false → no recompute. Only a *subsequent* source edit flips it.
**When to use:** Self-bumping counter that must not fire on the deploy that introduces it.
**Existing analog:** `_ensure_schema_extensions` (`repository.py:195`) runs additive migrations in `from_connection`; `read_model_refresh_runs` shows the singleton/append table style.

### Pattern 3: Atomic cutover via versioned PKs
**What:** New facts land at the new int; the 4 fact tables carry `metric_version` in their composite PK (`schema.py:153,178,202,234`). Point reads pin the current int by exact equality (`repository.py:789,814,842,868,901`), so they see either zero-new or complete-new. The R11 fix extends this guarantee to aggregate reads.
**Anti-Pattern to avoid:** Aggregating across all versions present (current `aggregate_queries.py` behavior) — harmless at one version, a blend risk after the first bump.

### Anti-Patterns to Avoid
- **Hand-maintained version int** (`CURRENT_METRIC_VERSION = 1`) — the exact knob this phase deletes.
- **Manifest of constant *values*** — reintroduces the hand-maintained list. Whole-module source hashing covers constants by construction.
- **Hashing too narrow a surface** — if a compute module is omitted, edits there silently fail to invalidate (under-invalidation = correctness bug). The completeness test is the guard.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Detecting which modules import the compute path | AST import-walker | Explicit `COMPUTE_SOURCE_MODULES` tuple + completeness test | CONTEXT decision; AST walk is fragile and over-engineered |
| Stable cross-process hash | `hash()` of source | `hashlib.sha256` | `hash()` is PYTHONHASHSEED-salted |
| Version blending guard | New reconciliation logic | Exact `metric_version = current` equality in WHERE (point reads already do this) | Reuse the existing pin pattern; atomic cutover is free |
| Recompute fan-out | New mass-enqueue method | Wire the existing orphan `enqueue_metric_version_recompute` (`repository.py:534`) | Already written, zero callers; just call it |

**Key insight:** Almost everything exists. The phase is mostly *wiring* an orphan method to a trigger and *deleting* a constant, plus two domain features that prove the wiring works.

## Runtime State Inventory

> This phase deletes the `CURRENT_METRIC_VERSION` symbol (a rename/removal of a load-bearing identifier). State audit:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | DuckDB fact rows carry `metric_version` (currently all `1`). New sidecar `read_model_logic_version` row. Existing rows stay at version 1; first real edit bumps to 2 and recomputes. | Migration seeds the sidecar; no rewrite of existing rows on deploy (seed=current ⇒ no spurious recompute). |
| Live service config | None — internal constants only, no env, no external config store. | None. |
| OS-registered state | None — no scheduler/process names embed `CURRENT_METRIC_VERSION`. | None. |
| Secrets/env vars | None — `WALK_TRIMP_DISCOUNT` is an internal constant, NOT an env var (explicit CONTEXT decision). | None. |
| Build artifacts / installed packages | `pip install /app` (`deploy/Dockerfile:19`) ships `.py` source into site-packages, so `inspect.getsource` works in-container. Verified as non-blocker (CONTEXT R9). | Add a packaged-install smoke test to prevent regression. |

**Symbol-removal call sites for `CURRENT_METRIC_VERSION`** (every reference must move to `repo.current_metric_version()` or accept the int as a parameter): `repository.py:31` (def, delete), `408` (default arg), `read_model_materializer.py:8,370` (import + default arg), `_sync_ops.py` (passes through), `runtime.py:110,181,273` (call sites), `worker.py:62,69` (call sites), `metric_services.py:333,340,358,360,406` (and `_rolling_by_window`). Confirm with `grep -rn CURRENT_METRIC_VERSION src/`.

## Common Pitfalls

### Pitfall 1: Circular import when fingerprinting from `metric_registry`
**What goes wrong:** `COMPUTE_SOURCE_MODULES` includes `adapters.duckdb.repository`, but `repository.py` → `schema.py` → `metric_registry.py`. A top-level `import_module` of repository inside metric_registry would cycle.
**How to avoid:** Do the `import_module` calls **inside** `compute_logic_fingerprint()` (runtime, not module top-level). By the time the fingerprint is computed (during a refresh cycle), all modules are fully imported.
**Warning signs:** `ImportError: partially initialized module` at startup.

### Pitfall 2: Comment/format-only edit triggers a recompute
**What goes wrong:** Source-text hashing is sensitive to whitespace and comments. A docstring tweak in a hashed module flips the fingerprint → a sub-second recompute.
**How to avoid:** Accept it (CONTEXT: "Accepted tradeoff" — over-invalidation costs sub-second compute; under-invalidation costs correctness). Do NOT try to normalize/strip comments — that re-introduces fragility.

### Pitfall 3: Forgetting the R11 aggregate filter
**What goes wrong:** Point reads pin the version, but the digest/aggregate path (`_where_clause`) does not. Mid-recompute, a weekly digest blends version-1 and version-2 rows.
**How to avoid:** Add `metric_version = <current>` to `_where_clause` for the versioned sources. The current int must be sourced from `repo.current_metric_version()` and threaded into `query_training_aggregates` / the request. Keep `COUNT(DISTINCT metric_version)` as a tripwire (should always be ≤1 after the fix).

### Pitfall 4: Completeness gap — a new compute module not listed
**What goes wrong:** Someone adds `mcp_strava.new_metric_math` and uses it in the materializer path, but forgets to add it to `COMPUTE_SOURCE_MODULES`. Edits there won't invalidate.
**How to avoid:** The completeness test (see Validation Architecture) walks the modules transitively imported by `read_model_materializer`'s compute path and asserts each is present in `COMPUTE_SOURCE_MODULES` → CI fails on a gap. This closes the one residual knob.

### Pitfall 5: Walk discount applied at the wrong grain
**What goes wrong:** `observed_trimp_history` (`repository.py:1118`) groups TRIMP by day only — applying a discount there to the daily total would discount mixed Run+Walk days incorrectly. The discount must be **per-sport** (group by day+sport, multiply Walk's TRIMP by the discount, then sum per day).
**How to avoid:** Add a per-sport daily aggregation; apply the discount only to the Walk-sport portion; produce `effective_trimp` distinct from `observed_trimp`. Pure-fn lives in `metrics.py`; the SQL group-by-day+sport lives in `repository`.

## Code Examples

### relative_time formatting (read-time, service layer)
```python
# rule: < 24h -> "Hh Mm"; >= 1 day -> "Nd Hh" (minutes dropped); boundary at 24h
def _relative_time(activity_dt, now) -> str:
    delta = now - activity_dt
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, rem_hours = divmod(hours, 24)
    return f"{days}d {rem_hours}h"
```

### Trigger block (chokepoint, _sync_ops.materialize_read_model_stage)
```python
# pseudo — exact repo helper names at Claude's discretion
stored = repo.current_logic_version()          # {metric_version, fingerprint} or None on fresh DB
live = compute_logic_fingerprint()
if stored is not None and stored.fingerprint != live:
    new_version = stored.metric_version + 1
    repo.bump_logic_version(new_version, live, now_iso)
    enqueued = repo.enqueue_metric_version_recompute(new_version, reason="logic_fingerprint_changed", queued_at=now_iso)
    _emit("read_model_logic_recompute", stored_fingerprint=stored.fingerprint,
          current_fingerprint=live, reason="logic_fingerprint_changed",
          activities_enqueued=enqueued, queued_at=now_iso)
current_version = repo.current_metric_version()
return materialize_duckdb_read_model(repo, metric_version=current_version, now=now_iso, renew_lease=renew_lease, limit=limit)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hand-bumped `CURRENT_METRIC_VERSION` int | Source-fingerprint auto-bump | This phase | Zero developer knob; matches dbt `state:modified` / `.pyc` hash-invalidation |
| Walks count at full TRIMP (`effective = observed`) | `WALK_TRIMP_DISCOUNT` applied per-sport | This phase | Ports forgotten Hermes edit; corrects inflated fatigue/ACWR/form |
| `start_time` read from `summary_json` at read-time | `start_time_local` materialized + `relative_time` at read | This phase | Stable workout time-of-day; relative recency on the payload |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `inspect.getsource(module)` succeeds under `pip install /app` (source in site-packages) | Runtime State Inventory | If wheels were zip-imported or `.py` stripped, getsource raises `OSError` — but Dockerfile does a plain source install (CONTEXT R9 verified). Packaged-install smoke test guards this. |
| A2 | The Walk discount belongs at the daily per-sport grain, not per-activity `activity_metric_facts.trimp` | Pitfall 5 | If applied per-activity, `trimp` (the raw per-activity metric) would be polluted; CONTEXT is explicit it lives at the **daily** grain (`effective_trimp`), leaving per-activity `trimp` raw. |

**Note:** All other claims are VERIFIED against codebase file:line or CPython stdlib docs.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python stdlib (`hashlib`, `inspect`, `importlib`) | fingerprint | ✓ | 3.14 | — |
| DuckDB | sidecar table, version filter | ✓ | 1.5.3 | — |
| `uv` / `pytest` | test suite | ✓ | pytest>=9 | — |
| Docker (`just test` full path) | packaged-install smoke + MCP smoke | ✓ (deploy/docker-compose.yml) | — | unit-only `uv run pytest -q` if Docker unavailable |

No missing dependencies. No external services.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 9 (`[tool.pytest.ini_options]`, `pythonpath=["src"]`) |
| Config file | `pyproject.toml` |
| Quick run command | `uv run pytest -q` |
| Full suite command | `just test` (pytest + `docker compose build` + live MCP smoke); unit-only: `uv run pytest -q` |
| Existing baseline | 348 passed (per CONTEXT); 37 test files in `tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-ZEROKNOB | Change a constant → next materialize auto-bumps version + recomputes, no manual step | integration | `uv run pytest tests/test_logic_fingerprint.py -k zero_knob -x` | ❌ Wave 0 |
| REQ-ZEROKNOB | Every module transitively imported by the materializer's compute path is in `COMPUTE_SOURCE_MODULES` (CI fails on gap) | unit | `uv run pytest tests/test_logic_fingerprint.py -k completeness -x` | ❌ Wave 0 |
| REQ-ZEROKNOB | sha256 over source text identical across processes / PYTHONHASHSEED-varied subprocesses | unit | `uv run pytest tests/test_logic_fingerprint.py -k determinism -x` | ❌ Wave 0 |
| REQ-ZEROKNOB | Fingerprint computes without `OSError` under the `pip install /app` Docker image | smoke | `just test` (Docker build + smoke) or a getsource smoke in-container | ❌ Wave 0 (or fold into existing docker smoke) |
| REQ-ZEROKNOB | Seed old-version facts, bump fingerprint → point AND aggregate reads return only-current-or-empty, never blended (R10/R11) | integration | `uv run pytest tests/test_metric_services.py -k no_blend -x` | ⚠️ extend existing |
| REQ-ZEROKNOB | Migration seeds fingerprint=current → first run after deploy does NOT recompute | integration | `uv run pytest -k seed_no_recompute -x` | ❌ Wave 0 |
| REQ-WALK | A day with a Walk yields discounted daily `effective_trimp`; non-walk days unaffected; Banister series consumes the discounted value | unit+integration | `uv run pytest tests/test_metrics_pure.py tests/test_duckdb_repository.py -k walk_discount -x` | ⚠️ extend existing |
| REQ-TIME | `relative_time`: `<24h → "Hh Mm"`, `>=1 day → "Nd Hh"` (minutes dropped); boundary at 24h | unit | `uv run pytest tests/test_metric_services.py -k relative_time -x` | ⚠️ extend existing |
| REQ-TIME | `start_time_local` materialized fact column populated from `start_date_local`; surfaced in payload | integration | `uv run pytest tests/test_metric_services.py -k start_time -x` | ⚠️ extend existing |

### Sampling Rate
- **Per task commit:** `uv run pytest -q tests/<touched_test_file>.py`
- **Per wave merge:** `uv run pytest -q` (full unit suite) + `uv run ruff check src tests` + `uv run ruff format --check src tests` + `uv run pyright src`
- **Phase gate:** `just test` green (unit + Docker build + live MCP smoke) before verify-work.

### Wave 0 Gaps
- [ ] `tests/test_logic_fingerprint.py` — zero-knob, completeness, determinism, seed-no-recompute (REQ-ZEROKNOB)
- [ ] Extend `tests/test_metric_services.py` — no-blend (R11), relative_time, start_time_local
- [ ] Extend `tests/test_metrics_pure.py` / `tests/test_duckdb_repository.py` — walk discount per-sport
- [ ] Packaged-install getsource smoke — fold into existing Docker smoke (`tests/test_docker_runtime.py`) or add a targeted test

## Security Domain

Single-user, single dev instance; no network input introduced; no auth surface. ASVS L1, block on high.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface added |
| V3 Session Management | no | None |
| V4 Access Control | no | Single-user local mirror |
| V5 Input Validation | partial | `WALK_TRIMP_DISCOUNT` and module names are developer-authored literals, never Strava-sourced; sidecar writes use parameterized SQL |
| V6 Cryptography | no | `sha256` used as a **content fingerprint**, not a security primitive — no key material, no secret |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via identifier interpolation | Tampering | New sidecar table/column names are schema-defined literals; route any identifier interpolation through the existing `_safe_identifier` guard (`repository.py:41`). Values use `?` placeholders. |
| Code execution via `import_module` of attacker-controlled name | Tampering / Elevation | `COMPUTE_SOURCE_MODULES` is a hard-coded tuple of in-repo module names — never derived from input. No dynamic/user-supplied module names. |
| `inspect.getsource` `OSError` (DoS on refresh) | Denial of Service | Packaged-install smoke test verifies getsource works under the Docker image; refresh already records failed runs (`_record_failed_run`) rather than crashing the process. |

## Sources

### Primary (HIGH confidence)
- Codebase (file:line, this session): `repository.py:31,205,408,534,789,1118,1208`; `read_model_materializer.py:8,248,280,370`; `_sync_ops.py:269`; `runtime.py:108,179`; `worker.py:69`; `schema.py:153,178,202,234,503`; `aggregate_queries.py:723,805,893,933`; `metric_services.py:273,309,333,358,406`; `constants.py`; `metric_registry.py:1730`; `Dockerfile:19`; `pyproject.toml`; `Justfile`.
- CPython stdlib docs — `inspect.getsource`, `hashlib.sha256`, `importlib.import_module` (behavior is stable, well-documented; ASSUMED-not-needed to re-fetch — standard library semantics).

### Secondary (MEDIUM confidence)
- dbt `state:modified` / Python `.pyc` source-hash invalidation as the named design pattern (CONTEXT-cited; conceptual analog, not a dependency).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — stdlib only, verified against existing usage (`hashlib` already imported in repository).
- Architecture: HIGH — all integration points grounded at file:line; mechanism reuses existing dirty-queue/drain infra.
- Pitfalls: HIGH — circular-import, R11, completeness, and walk-grain risks each traced to specific code.

**Research date:** 2026-06-03
**Valid until:** 2026-07-03 (stable internal domain; no fast-moving external deps)
