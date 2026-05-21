---
phase: 02-sqlite-safety-repository-layer
reviewed: 2026-05-21T11:14:37Z
depth: deep
files_reviewed: 20
files_reviewed_list:
  - src/mcp_strava/adapters/__init__.py
  - src/mcp_strava/adapters/sqlite/__init__.py
  - src/mcp_strava/adapters/sqlite/backup.py
  - src/mcp_strava/adapters/sqlite/connection.py
  - src/mcp_strava/adapters/sqlite/migrations.py
  - src/mcp_strava/adapters/sqlite/repository.py
  - src/mcp_strava/adapters/sqlite/schema.py
  - src/mcp_strava/analytics.py
  - src/mcp_strava/cli.py
  - src/mcp_strava/db.py
  - src/mcp_strava/metrics.py
  - src/mcp_strava/report.py
  - src/mcp_strava/sync.py
  - src/mcp_strava/trends.py
  - src/mcp_strava/types.py
  - tests/test_load_status.py
  - tests/test_phase01_validation.py
  - tests/test_repository_boundary.py
  - tests/test_security_guards.py
  - tests/test_sqlite_safety.py
findings:
  critical: 3
  warning: 2
  info: 0
  total: 5
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-05-21T11:14:37Z  
**Depth:** deep  
**Files Reviewed:** 20  
**Status:** issues_found

## Summary

Phase 2 SQLite safety/repository changes were reviewed end-to-end, including cross-file call chains (`cli` -> `sync`/`db` -> `repository` -> SQLite adapters). The implementation improves structure, but it still contains blocker-level safety and runtime defects in backup validation and stream refresh/write atomicity, plus migration/parity guard gaps.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Backup Integrity Check Result Is Ignored

**File:** `src/mcp_strava/adapters/sqlite/backup.py:37`  
**Issue:** `create_timestamped_backup()` executes `PRAGMA integrity_check` but never verifies that the result is `"ok"`. Corrupt backups can be reported as successful and later fail restore, which is a direct data-loss recovery risk.
**Fix:**
```python
with sqlite3.connect(str(target)) as verify_conn:
    row = verify_conn.execute("PRAGMA integrity_check").fetchone()
if not row or str(row[0]).lower() != "ok":
    raise RuntimeError(f"Backup integrity check failed for {target}: {row[0] if row else 'unknown'}")
```

### CR-02: Quick Sync Can Crash on Legacy `activities.date` Values

**File:** `src/mcp_strava/sync.py:150`  
**Issue:** Quick sync parses `MAX(date)` strictly with `'%Y-%m-%d'`. Existing mirrors may contain full timestamps (for example `YYYY-MM-DDTHH:MM:SSZ`), causing `ValueError` and aborting sync.
**Fix:**
```python
latest_raw = row[0] if row and row[0] else "2000-01-01"
latest_day = str(latest_raw)[:10]
safe_date = (datetime.strptime(latest_day, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
```

### CR-03: Backfill Stream Refresh Is Non-Atomic and Can Lose Stream Data

**File:** `src/mcp_strava/sync.py:288`  
**Issue:** Backfill deletes existing stream rows (`delete_stream_rows_for_activity`) before inserting replacement rows, and repository chunk inserts commit per chunk (`repository.py:536-564`). If insertion fails mid-run, an activity can be left with partial or empty streams.
**Fix:**
```python
# repository.py
def replace_stream_rows_chunked(...):
    self.conn.execute("BEGIN")
    try:
        self.conn.execute("DELETE FROM streams WHERE activity_id = ?", (activity_id,))
        # insert chunks without intermediate commits
        ...
        self.conn.commit()
    except Exception:
        self.conn.rollback()
        raise
```
Use this method in `backfill_activities()` instead of separate delete+insert calls.

## Warnings

### WR-01: Parity Snapshot Field Is Never Validated

**File:** `src/mcp_strava/adapters/sqlite/migrations.py:21`  
**Issue:** `ParitySnapshot` carries `banister_series_tail`, but `evaluate_parity()` never compares it. This leaves a declared parity signal unenforced and can miss migration regressions.
**Fix:** Compare series length and pointwise values (with tolerance for numeric fields), and fail parity when they diverge.

### WR-02: Fail-Closed Open Test Passes for the Wrong Reason

**File:** `tests/test_sqlite_safety.py:152`  
**Issue:** `open_expected_mirror_db()` is called without a required `path` argument. The test passes due to `TypeError`, not due to fail-closed missing-file behavior, so the safety contract is not truly validated.
**Fix:**
```python
with pytest.raises(sqlite3.OperationalError):
    open_expected_mirror_db(missing)
```
and keep the `assert not missing.exists()` postcondition.

---

_Reviewed: 2026-05-21T11:14:37Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: deep_
