---
phase: 01-package-foundation-settings
reviewed: 2026-05-20T15:31:46Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - Justfile
  - pyproject.toml
  - src/mcp_strava/__init__.py
  - src/mcp_strava/__main__.py
  - src/mcp_strava/analytics.py
  - src/mcp_strava/api_schema.py
  - src/mcp_strava/cardiac_drift.py
  - src/mcp_strava/cli.py
  - src/mcp_strava/constants.py
  - src/mcp_strava/db.py
  - src/mcp_strava/metrics.py
  - src/mcp_strava/report.py
  - src/mcp_strava/settings.py
  - src/mcp_strava/sports.py
  - src/mcp_strava/strava_api_reference.py
  - src/mcp_strava/sync.py
  - src/mcp_strava/training.py
  - src/mcp_strava/trends.py
  - src/mcp_strava/types.py
  - tests/test_settings.py
  - tests/test_smoke.py
findings:
  critical: 2
  warning: 2
  info: 0
  total: 4
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-05-20T15:31:46Z  
**Depth:** standard  
**Files Reviewed:** 21  
**Status:** issues_found

## Summary

Phase 1 packaging/settings refactor compiles and tests pass, but it introduces two ship-blocking configuration defects and two workflow/robustness regressions. The blockers are both in the new settings boundary and can redirect or invalidate runtime state paths in ways that violate the local-mirror preservation goal.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Default root derivation breaks installed-runtime paths and can redirect DB/token files away from the real mirror

**Classification:** BLOCKER  
**File:** `src/mcp_strava/settings.py:82`  
**Issue:** `load_settings()` defaults `project_root` to `Path(__file__).resolve().parents[2]`. In an installed package, this resolves under site-packages, not the actual repo/runtime working directory. That makes default `database_path`/`token_path` (lines 94-95) point outside the intended local mirror (`data/strava.db` + `.env`), creating path regressions and possible write failures or accidental new DB creation in the wrong location.

**Fix:** Resolve root from explicit env/config first, then from CWD for local runtime, and only fall back to module path as a last resort.

```python
# src/mcp_strava/settings.py
runtime_root = env_map.get('MCP_STRAVA_PROJECT_ROOT')
if runtime_root:
    root = Path(runtime_root)
elif project_root is not None:
    root = Path(project_root)
else:
    root = Path.cwd()
```

### CR-02: Freshness settings accept impossible state (`warn_age_hours > max_age_hours`)

**Classification:** BLOCKER  
**File:** `src/mcp_strava/settings.py:66-73`  
**Issue:** Range validation checks non-negative values but does not enforce `warn_age_hours <= max_age_hours`. This allows contradictory configs (warn threshold after max threshold), which breaks freshness semantics and can produce inverted alert behavior in downstream logic.

**Fix:** Add invariant validation and test coverage.

```python
# src/mcp_strava/settings.py
if warn_age_hours > max_age_hours:
    raise ValueError(
        'Invalid freshness settings: MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS '
        'must be <= MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS'
    )
```

## Warnings

### WR-01: Global settings cache ignores later call arguments, causing hidden path/config leakage across callers

**Classification:** WARNING  
**File:** `src/mcp_strava/settings.py:123-131`  
**Issue:** After first `get_settings()` call, all future calls ignore provided `environ/env_file/project_root` arguments. This is already visible in tests where manual resets are required to avoid wrong DB path reuse. In multi-command processes this can silently pin stale config.

**Fix:** Either make `get_settings()` arg-less (and fail if args are passed after initialization), or key cache by normalized `(environ, env_file, project_root)` tuple.

### WR-02: Phase-1 tests miss validation for freshness ordering invariant

**Classification:** WARNING  
**File:** `tests/test_settings.py:111-124`  
**Issue:** Parameterized validation tests cover integer parsing/range, but no test asserts that `warn_age_hours` cannot exceed `max_age_hours`. This gap allowed CR-02 to pass unnoticed.

**Fix:** Add a targeted failing-case test.

```python
def test_load_settings_rejects_warn_age_greater_than_max_age() -> None:
    with pytest.raises(ValueError, match='WARN_AGE_HOURS'):
        load_settings(
            environ={
                'MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS': '25',
                'MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS': '24',
            },
            project_root=Path('/tmp/project'),
        )
```

---

_Reviewed: 2026-05-20T15:31:46Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: standard_
