---
phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu
reviewed: 2026-06-03T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - src/mcp_strava/metric_registry.py
  - src/mcp_strava/constants.py
  - src/mcp_strava/metrics.py
  - src/mcp_strava/adapters/duckdb/schema.py
  - src/mcp_strava/adapters/duckdb/repository.py
  - src/mcp_strava/adapters/duckdb/read_model_materializer.py
  - src/mcp_strava/adapters/duckdb/aggregate_queries.py
  - src/mcp_strava/adapters/duckdb/__init__.py
  - src/mcp_strava/application/metric_services.py
  - src/mcp_strava/application/aggregate_services.py
  - src/mcp_strava/application/product_facts.py
  - src/mcp_strava/refresh/_sync_ops.py
  - src/mcp_strava/refresh/runtime.py
  - src/mcp_strava/refresh/worker.py
findings:
  critical: 0
  warning: 4
  info: 0
  total: 4
status: issues_found
orchestrator_verification:
  cr_01: dismissed_false_positive  # PEP 758, valid under Python 3.14 (project requires-python >=3.14)
  in_02: dismissed_false_positive  # same — pre-existing PEP 758 syntax in non-phase-15 files
  verified_by: execute-phase orchestrator (compiled + imported on .venv/bin/python 3.14.2; 385 pytest passed)
---

# Phase 15: Code Review Report

**Reviewed:** 2026-06-03
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found (4 WARNING, advisory/non-blocking)

> **⚠ ORCHESTRATOR VERIFICATION NOTE (added post-review).** The reviewer's headline
> **CR-01 BLOCKER** and **IN-02** are **DISMISSED as false positives.** They assert that
> `except A, B:` is a Python-2 `SyntaxError`. This project is **hard-pinned to Python ≥3.14**
> (`pyproject.toml: requires-python = ">=3.14"`, ruff `target-version = "py314"`, CI
> `python-version: "3.14"`, `deploy/Dockerfile: FROM python:3.14-slim`), where
> **[PEP 758](https://peps.python.org/pep-0758/)** makes `except A, B:` valid bare-tuple
> syntax that catches **both** exception types (empirically confirmed: both branches
> reachable, `TypeError` not shadowed). The files compile and import cleanly on
> `.venv/bin/python` (3.14.2), and the full suite is **385 passed** — directly refuting the
> reviewer's claim that "the test suite cannot have passed against this tree." The four
> WARNING findings below (WR-01..04) stand as advisory logic concerns and are folded into
> phase verification. **Net actionable: 0 blocking, 4 advisory warnings.**

## Summary

Phase 15 wires a source-text logic fingerprint into the materialize chokepoint so
the read model self-invalidates and auto-recomputes when compute-path source
changes. The fingerprint/bump/enqueue flow and the R11 version-pinning across
aggregate and status reads are logically sound and consistent: `bump_logic_version`
correctly invalidates the `current_metric_version` memo, and the chokepoint
re-resolves the version POST-bump so enqueued dirty rows and the materialize
version agree at N+1. Version pinning (`metric_version = ?` bound, never
formatted) is present on every fact SELECT I traced.

However, the phase ships **hard Python syntax errors** (`except A, B:` — Python-2
syntax that does not parse under Python 3) in THREE of the changed files. These are
committed at HEAD (clean working tree), so every affected module fails to import
and the application cannot start. This is a release blocker that supersedes all
other findings — the feature literally cannot run, and the test suite for the phase
cannot have passed against this tree.

Secondary findings concern transaction atomicity of the bump+enqueue+materialize
sequence (it spans three independent commits, not one transaction) and a
local-vs-UTC timestamp inconsistency that skews age-based staleness on this
non-UTC server.

## Critical Issues

### CR-01: ~~Python-2 `except A, B:` syntax — SyntaxError~~ — DISMISSED (false positive)

> **DISMISSED by orchestrator verification.** Not a SyntaxError: PEP 758 (Python 3.14)
> makes `except A, B:` valid and the project requires Python ≥3.14. Compiles, imports,
> 385 tests pass. The original finding text is retained below for the record only.

**File:** `src/mcp_strava/metrics.py:45`
**Also:** `src/mcp_strava/adapters/duckdb/read_model_materializer.py:79,85,104`
**Also:** `src/mcp_strava/application/metric_services.py:168,263,290`

**Issue:** Multiple `except` clauses use the Python-2 comma form
`except ValueError, TypeError:` instead of the Python-3 tuple form
`except (ValueError, TypeError):`. Under Python 3 this is a hard `SyntaxError`, not a
runtime error — the module fails at compile/import time. Verified directly:

```
$ python3 -m py_compile src/mcp_strava/metrics.py
  File "src/mcp_strava/metrics.py", line 45
    except ValueError, TypeError:
           ^^^^^^^^^^^^^^^^^^^^^
SyntaxError: multiple exception types must be parenthesized
```

These lines are committed at HEAD (the working tree is clean; `git show HEAD:` shows
the broken line) and were introduced by the actual phase-15 feature commits
(`a8d44f1` 15-05 start_time_local, `4e02fd4`, `823d88a`, `e4511a3` 15-04 Walk
discount). `metrics.py` and `read_model_materializer.py` are BOTH members of
`COMPUTE_SOURCE_MODULES`, and `metric_services.py` backs the MCP tool payloads — so
the fingerprint feature, the Walk discount, the workout-time fields, and every
read-time tool service are all dead on arrival. The package does not import.

Impact radius is wider than the three in-scope files: the same antipattern also
exists pre-existing in `adapters/strava/transport.py:114` and
`refresh/health.py:138` (out of phase-15 scope — see IN-02), so 5 source files
total fail to compile. Whatever ran the phase-15 tests was NOT this tree.

**Fix:** Parenthesize every multi-type except across all occurrences:

```python
# src/mcp_strava/metrics.py:45
    try:
        parsed = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
```

Apply identically at read_model_materializer.py:79, :85, :104 (`except (ValueError,
TypeError):`) and metric_services.py:168 (`except (TypeError, ValueError):`), :263,
:290. Add a CI gate that runs `python -m compileall src/` (or `ruff check`, which
catches this) so a non-parsing tree can never merge again — the existing CI claim of
running `ruff format --check` + pytest cannot be true against this commit.

## Warnings

### WR-01: bump + enqueue + materialize span three independent commits, not one transaction

**File:** `src/mcp_strava/refresh/_sync_ops.py:324-345`

**Issue:** On a fingerprint mismatch the chokepoint runs, in sequence and OUTSIDE any
caller transaction: `repo.bump_logic_version(...)` (commits via
`_commit_if_standalone`), then `repo.enqueue_metric_version_recompute(...)` (commits
via `_commit_if_standalone`), then `materialize_duckdb_read_model(...)` which opens
its own `repo.begin()` block (read_model_materializer.py:434). Because
`_transaction_depth == 0` at each call, each step commits independently. If the
process dies (lease loss, OOM, crash) AFTER the bump commits but BEFORE enqueue
finishes — or after enqueue but before materialize — the sidecar is durably at N+1
while the dirty queue and facts are partially or not populated.

The next cycle then sees `stored == live` (fingerprint already advanced) and will
NOT re-enqueue, so the mass-recompute is silently lost: reads pin to N+1, find few
or no N+1 facts, and degrade. The design comments claim the flow "recomputes within
this same call," but there is no atomic boundary guaranteeing bump and enqueue land
together.

**Fix:** Wrap the bump+enqueue (at minimum) in a single `repo.begin()/commit()` so
the version advance and the dirty-row enqueue are atomic:

```python
elif stored["logic_fingerprint"] != live:
    new_version = int(stored["metric_version"]) + 1
    repo.begin()
    try:
        repo.bump_logic_version(new_version, live, now_iso)
        enqueued = repo.enqueue_metric_version_recompute(
            new_version, reason="logic_fingerprint_changed", queued_at=now_iso
        )
    except Exception:
        repo.rollback()
        raise
    repo.commit()
```

If full bump+enqueue+materialize atomicity is wanted, hoist the whole chokepoint
into one transaction. Note `bump_logic_version`/`enqueue_*` call
`_commit_if_standalone`, which no-ops inside a transaction, so this composes.

### WR-02: `computed_at` / `finished_at` written in LOCAL time while staleness compares against UTC

**File:** `src/mcp_strava/adapters/duckdb/read_model_materializer.py:27,380`

**Issue:** `_now_parts` (line 27, `datetime.now()`) and `_record_failed_run` (line
380, `datetime.now().isoformat(...)`) stamp `computed_at` and `finished_at` in the
server's LOCAL timezone. But the chokepoint receives `now_iso` from
`runtime._now_iso` which is UTC-naive (`datetime.fromtimestamp(..., tz=UTC)`), and
`repository._now_iso` (used for the sidecar `changed_at`) is also UTC-naive
(`datetime.now(UTC)`). The `stale_read_model_facts` status fact and
`build_freshness_metadata` compute age as `as_of - last_materialized_day`. On this
server (Asia/Almaty, UTC+5/+6 per CLAUDE.md) the local-stamped `computed_at` runs
~5-6h ahead of UTC `as_of`, so freshly materialized facts can read as "from the
future" or mask/inflate the staleness threshold by up to a day near midnight.

Note the same `materialize_read_model` path is invoked from the worker with
`worker._now_iso()` (also local `datetime.now()`), so within the worker path the two
agree — but the runtime path (`run_once`/`run_catchup`) passes UTC `now_iso` while
the materializer's internal `_now_parts(None)` and `_record_failed_run` still stamp
local. The sources are not consistent.

**Fix:** Use a single UTC-naive clock everywhere facts are stamped. In the
materializer:

```python
def _now_parts(now: str | datetime | None) -> tuple[str, str]:
    if now is None:
        dt = datetime.now(UTC).replace(tzinfo=None)
    ...
# and _record_failed_run:
        "finished_at": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
```

Better: thread the caller-provided `now_iso` (already UTC) into `_record_failed_run`
instead of re-deriving a fresh local timestamp.

### WR-03: `_record_failed_run` commits/rolls back via `repo.conn` directly, bypassing the process lock

**File:** `src/mcp_strava/adapters/duckdb/read_model_materializer.py:392-394`

**Issue:** Every other write in the repository goes through `_execute` /
`_commit_if_standalone`, which acquire `duckdb_process_lock()` to serialize against
other processes/threads sharing the single-writer DuckDB file. `_record_failed_run`
instead calls `repo.conn.commit()` / `repo.conn.rollback()` raw, with no lock. It
runs in the `except` path right after `repo.rollback()` (which released the lock), so
the failed-run INSERT (`record_read_model_refresh_run` → `_execute`, which DOES take
the lock) followed by a bare `repo.conn.commit()` can interleave with another
writer's transaction. On the documented single-owner live runtime this is unlikely to
corrupt, but it violates the locking contract the rest of the module relies on and is
a latent hazard for the worker/owner split.

**Fix:** Route the commit/rollback through the repository's locked helpers:

```python
    try:
        repo.record_read_model_refresh_run({...})
        repo._commit_if_standalone()
    except Exception:
        repo.rollback()
```

### WR-04: partial-batch recompute clears only the limited dirty rows but reports rolling/daily facts as fully materialized

**File:** `src/mcp_strava/adapters/duckdb/read_model_materializer.py:413-484`

**Issue:** `dirty_activity_rows_for_materialization(metric_version, limit=limit)`
fetches at most `limit` dirty rows, and `clear_dirty_activity_rows(dirty_rows)`
clears exactly those. But `_materialize_daily_facts` / `_materialize_model_facts` /
`_materialize_rolling_facts` recompute over `start_day..end_day` derived from the
LIMITED batch's min day to `today` — and the daily/model/rolling sums read
`metric_version` facts that, on a mass fingerprint recompute, are only partially
populated for the new version (only `limit` activities materialized so far). The
returned `daily_facts_materialized` / `rolling_facts_materialized` counts and the
"ok" run record imply a complete window, but daily aggregates for days whose
activities are still queued at N+1 will under-count until later batches land. The
worker loops on `dirty_count`, so it eventually converges, but intermediate cycles
write daily/model/rolling facts that are silently wrong for the new version and are
not re-flagged dirty.

**Fix:** Either (a) only materialize daily/model/rolling facts for days whose
activities are ALL out of the dirty queue at the target version, or (b) on a
fingerprint-driven mass recompute, do not apply `limit` to the activity pass for a
given day — process whole days atomically so daily rollups never read a half-migrated
day. At minimum, mark daily/model/rolling rows `completeness_status` partial while
upstream activity rows for that day remain dirty, so reads can detect the transient.

## Info

### IN-01: Pre-existing per_sport rolling scope mismatch (`scope='sport'` read vs `scope='all'` written)

**File:** `src/mcp_strava/adapters/duckdb/aggregate_queries.py:1002-1006`

**Issue:** `_where_clause` filters per-sport rolling reads with `scope = 'sport'`
(line 1003), but `_materialize_rolling_facts` only ever writes
`rolling_period_facts` rows with `scope = 'all'` (read_model_materializer.py:343).
A per-sport rolling aggregate therefore always matches zero rows. This is NOT a
phase-15 regression — `git blame` attributes the predicate to commit `2eed32e7`
(2026-05-26), before this phase's diff base, and the materializer never wrote
per-sport rolling facts before either. Flagged for visibility only; out of scope for
this review's verdict.

**Fix:** Out of scope. Track separately: either materialize per-sport rolling facts
under `scope='sport'`, or drop the unreachable per-sport rolling read branch.

### IN-02: Same `except A, B:` syntax error in two out-of-scope files

**File:** `src/mcp_strava/adapters/strava/transport.py:114`
**Also:** `src/mcp_strava/refresh/health.py:138`

**Issue:** The CR-01 antipattern also appears in two files outside the phase-15
change set (pre-existing per `git blame`). They are listed here because they
contribute to the "package does not compile" reality and must be fixed before any
release, but they are not phase-15 defects.

**Fix:** Parenthesize as in CR-01: `except (TypeError, ValueError):`.

---

_Reviewed: 2026-06-03_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
