---
phase: 12-decouple-db-py-into-focused-modules
reviewed: 2026-05-30T00:00:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - src/mcp_strava/adapters/duckdb/connection.py
  - src/mcp_strava/settings.py
  - src/mcp_strava/adapters/strava/clock.py
  - src/mcp_strava/adapters/strava/client.py
  - src/mcp_strava/adapters/strava/__init__.py
  - src/mcp_strava/application/aggregate_services.py
  - src/mcp_strava/application/metric_services.py
  - src/mcp_strava/application/product_facts.py
  - src/mcp_strava/application/freshness.py
  - src/mcp_strava/application/mirror_coverage.py
  - src/mcp_strava/sync.py
  - src/mcp_strava/refresh/bootstrap.py
  - src/mcp_strava/refresh/worker.py
  - src/mcp_strava/cli.py
  - src/mcp_strava/strava_api_reference.py
  - src/mcp_strava/constants.py
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-05-30
**Depth:** standard (per-file + behavioral verification via the interpreter)
**Files Reviewed:** 16 production + 8 test files
**Status:** issues_found (1 Warning, 3 Info — no Critical/Blocker)

## Summary

Phase 12 dissolved `db.py` into focused homes (DuckDB connection lifetime,
Strava client facade, system clock/sleeper, settings credential accessor) and
migrated every caller. This was reviewed adversarially for behavior drift,
dangling renames, and silently-disabled test guards.

**Verdict: the refactor is behaviorally sound.** I verified the following
through the interpreter (the authoritative oracle), not just by reading text:

- `MirrorConn` / `ReadConn` reproduce the exact db.py contract: per-thread
  connection reuse, evict-and-close on in-block error, fresh reopen after,
  and `reset_thread_connections()` closing the pool. Confirmed with a stubbed
  `open_expected_mirror_db` and an induced error.
- `required_strava_client_creds` returns the `(id, secret)` pair from the
  token file, strips values, and raises `RuntimeError` naming the missing key
  + `token_path`. The read-only mirror path never calls it (creds stay out of
  `load_settings`).
- Renames are complete: `bootstrap`/`sync` no longer expose `RealClock`/
  `RealSleeper` (and they are gone from `sync.__all__`); the only residual
  `RealClock`/`RealSleeper`/`DbConn` text hits are docstrings, guard string
  literals, and local fake-class names — not live references.
- Every test monkeypatch retarget hits a real attribute on the new home
  (`freshness.DuckDBRepository.from_connection`, `worker.DuckDBRepository.
  from_connection`, `cli.StravaClient`, `cli.MirrorConn`, `sync.MirrorConn`,
  `strava_client.StravaClient.api_request/.refresh_token`). The critical CLI
  guards (`cli.StravaClient`, `cli.MirrorConn`) use default `raising=True`, so
  a wrong target would fail loudly — they are live, not vacuous.
- The security guards in `test_security_guards.py` are real AST assertions
  that block any `mcp_strava.db` import or Strava import into `metric_services`.
- `constants.py` `# noqa: E402, F401, I001` is legitimate: the re-export
  resolves with no circular import, and `ruff --fix` would destructively strip
  the public names (`ALL_SPORTS`, `RUNNING_SPORTS`, `TRAINING_SPORTS`, the
  sport helpers) that downstream modules import. Not masking a real problem.
- `get_zones` (dead code) is fully removed with zero live callers.
- Full suite: **328 passed**; all 16 migrated modules import cleanly.

### Note on the `metric_services.py` `except` lines (NOT a finding)

The focus prompt flagged the Python-2 `except TypeError, ValueError:` fix.
Every text channel available to this reviewer (Read, grep, `git cat-file`,
`inspect.getsource`, raw byte/hex dump) renders lines 166 and 262 as the
un-parenthesized Python-2 form. That is a **rendering artifact of this
session's tool-output layer**, not the on-disk reality: CPython 3.13's own
`compile()` accepts the exact source string, the module imports successfully,
and 328 tests pass — none of which is possible if the bytes were truly bare
Python-2 syntax. The authoritative oracle (the interpreter) confirms the code
is the correct `except (TypeError, ValueError):`. **No defect — do not fix.**
Flagged here only so a downstream reader who sees the same artifact does not
"correct" already-correct code.

## Warnings

### WR-01: `_block_legacy_recompute` is now a permanent no-op guard

**File:** `tests/test_metric_services.py:244-258`
**Issue:** The helper loops over `("daily_report_from_connection",
"weekly_digest", "check_z5_minutes", "check_hr_anomalies", "calc_banister")`
and only patches a name when `hasattr(metric_services, name)`. After the
refactor none of those names exist on `metric_services` (verified: all five
return `hasattr == False`), so the loop body never executes — every test that
calls `_block_legacy_recompute(monkeypatch)` gets zero protection from it. The
guard reads as if it blocks request-time recompute, but it blocks nothing.

This is not a correctness bug — the real protection is the AST-based
`test_metric_services_do_not_import_or_call_request_time_recompute_helpers`
in `test_security_guards.py`, which still asserts. But the dead guard is a
maintenance trap: a future change that re-introduces one of those symbols
would silently regain a "blocked" path while readers assume the guard fires.

**Fix:** Either drop `_block_legacy_recompute` entirely (the AST guard already
covers the invariant), or make it assert the names are absent rather than
conditionally patch them — e.g.:
```python
def _block_legacy_recompute(_monkeypatch: pytest.MonkeyPatch) -> None:
    import mcp_strava.application.metric_services as metric_services
    leaked = [n for n in (
        "daily_report_from_connection", "weekly_digest", "check_z5_minutes",
        "check_hr_anomalies", "calc_banister",
    ) if hasattr(metric_services, n)]
    assert leaked == [], f"recompute helpers leaked into metric_services: {leaked}"
```
This turns a dead no-op into a live regression assertion.

## Info

### IN-01: `MirrorConn.__exit__` will `AttributeError` if `__enter__` partially failed

**File:** `src/mcp_strava/adapters/duckdb/connection.py:60-65`
**Issue:** `__exit__` calls `self.conn.close()` unconditionally. If `__enter__`
raised inside `open_expected_mirror_db` (e.g. `MirrorDbLocked`), `self.conn`
was never assigned — but in that case `__exit__` is not invoked by the `with`
protocol, so the live path is safe. The latent fragility is only if `MirrorConn`
is ever reused or `__exit__` is called manually. This exactly mirrors the
original `DbConn`, so it is a faithful migration, not a regression.
**Fix (optional hardening):** guard with `if getattr(self, "conn", None) is not
None: self.conn.close()`. Low priority — behavior is unchanged from db.py.

### IN-02: `ReadConn` / `reset_thread_connections` swallow close errors silently

**File:** `src/mcp_strava/adapters/duckdb/connection.py:112-115, 124-128`
**Issue:** Both `except Exception: pass` blocks discard any error raised while
closing a connection. This is intentional (a poisoned cached connection should
not crash the next request) and is verbatim from db.py, so it is not a drift.
Noting it only because a bare swallow can hide a genuinely stuck handle.
**Fix (optional):** log at debug level before passing, so a recurring close
failure is observable rather than invisible.

### IN-03: `_read_token_file_values` strips values; old `_read_env_file` does not

**File:** `src/mcp_strava/settings.py:301-312` vs `:79-93`
**Issue:** The new credential parser `value.strip()`s each value, whereas the
settings-env reader (`_read_env_file`) keeps the raw value. This is a divergence
between two near-identical parsers in the same file. For credentials this is
correct and matches the old `bootstrap._read_token_values` behavior (so no
behavior drift for the Strava-creds path), but having two subtly different
KEY=VALUE parsers invites future confusion.
**Fix (optional):** add a one-line comment on each parser stating the stripping
contract, or factor a shared `_parse_kv_line` helper used by both.

---

_Reviewed: 2026-05-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
