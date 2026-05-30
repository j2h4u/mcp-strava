---
phase: "13"
plan: "03"
subsystem: "type-checking"
tags: ["pyright", "config", "noqa", "hygiene"]
dependency_graph:
  requires: ["13-01", "13-02"]
  provides: ["D-05 typeCheckingMode pin", "D-07 noqa hygiene"]
  affects: ["pyproject.toml pyright config", "refresh/worker.py", "refresh/health.py"]
tech_stack:
  added: []
  patterns: ["explicit pyright mode pin for reproducibility", "no dead noqa suppressions"]
key_files:
  created: []
  modified:
    - pyproject.toml
    - src/mcp_strava/refresh/worker.py
    - src/mcp_strava/refresh/health.py
decisions:
  - "typeCheckingMode = standard pinned explicitly in [tool.pyright] — makes zero-error state version-drift-proof (D-05)"
  - "BLE001 noqa comments removed — BLE001 not in ruff select set, so they suppressed nothing (D-07)"
  - "health.py except clause retains inline comment explaining intent, stripped only the dead noqa: BLE001 tag"
metrics:
  duration: "5 min"
  completed: "2026-05-30"
  tasks_completed: 2
  files_modified: 3
---

# Phase 13 Plan 03: pyright Config Pin and noqa Hygiene Summary

**One-liner:** Pinned `typeCheckingMode = "standard"` in pyproject.toml and removed 3 dead `noqa: BLE001` comment suffixes from refresh/worker.py and refresh/health.py.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Pin typeCheckingMode in pyproject.toml — D-05/D-06 | c837a0f | pyproject.toml |
| 2 | Remove vestigial noqa: BLE001 comments — D-07 | 51a58d0 | src/mcp_strava/refresh/worker.py, src/mcp_strava/refresh/health.py |

## What Was Done

**Task 1 (D-05/D-06):** Added `typeCheckingMode = "standard"` as a new key in `[tool.pyright]`. The section previously relied on the implicit default. `include = ["src"]` and `pythonVersion = "3.14"` are unchanged (D-06 scope lock). `uv run pyright src` exits 0 after the change.

**Task 2 (D-07):** Removed the `# noqa: BLE001` suffix from three `except` lines:
- `worker.py:108` — `except Exception as exc:` (mirror_storage_error handler)
- `worker.py:248` — `except Exception as exc:` (refresh_worker_error handler)
- `health.py:62` — `except Exception:` (kept the explanatory comment, stripped only the dead tag)

`BLE001` (blind except) is not in the project's ruff `select` set (`E4,E7,E9,F,I,B,UP`), so all three were suppressing nothing. The `except Exception` clauses themselves are intentional catch-all behavior and are unchanged.

Live noqa comments confirmed untouched:
- `interfaces/mcp_http.py:26` — `# noqa: F401` (re-export suppression)
- `constants.py:118` — `# noqa: E402, F401, I001` (namespace re-export block)

## Verification Results

- `grep 'typeCheckingMode = "standard"' pyproject.toml` — 1 match in `[tool.pyright]`
- `rg 'noqa: BLE001' src/` — 0 matches
- `grep 'noqa: F401' src/mcp_strava/interfaces/mcp_http.py` — line 26 intact
- `grep 'noqa: E402' src/mcp_strava/constants.py` — line 118 intact
- `uv run ruff check src tests` — All checks passed!
- `uv run pyright src` — 0 errors, 0 warnings, 0 informations

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — config key addition and comment-suffix removals only. No new runtime surface, no new network endpoints, no schema changes.

## Self-Check: PASSED

- `pyproject.toml` modified — `typeCheckingMode = "standard"` confirmed at line 48
- `src/mcp_strava/refresh/worker.py` modified — no BLE001 noqa present
- `src/mcp_strava/refresh/health.py` modified — no BLE001 noqa present
- Commit c837a0f exists (Task 1)
- Commit 51a58d0 exists (Task 2)
- pyright: 0 errors confirmed
- ruff: all checks passed confirmed
