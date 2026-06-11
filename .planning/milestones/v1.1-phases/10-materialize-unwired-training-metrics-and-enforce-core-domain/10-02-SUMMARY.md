---
phase: 10-materialize-unwired-training-metrics-and-enforce-core-domain
plan: "02"
subsystem: test-architecture
tags: [boundary-guard, import-scan, ast, domain-separation, ci]
dependency_graph:
  requires: [10-01]
  provides: [storage-adapter-import-boundary-guard-for-domain-modules]
  affects: [tests/test_security_guards.py]
tech_stack:
  added: []
  patterns: [ast-import-scan, boundary-guard, out-of-band-red-proof]
key_files:
  created: []
  modified:
    - tests/test_security_guards.py
decisions:
  - "Rename test_read_modules_do_not_import_strava_or_refresh to test_read_modules_do_not_import_storage_strava_or_refresh — wider name reflects the wider guard"
  - "Extend disallowed prefixes to include mcp_strava.db and mcp_strava.adapters.duckdb in addition to existing strava-adapter and refresh prefixes"
  - "Widen read_modules to five domain modules: training, metrics, cardiac_drift, hr_zones, sports"
  - "Out-of-band RED proof: transient import injected, test observed failing, import reverted — never committed"
metrics:
  duration: "~1 min"
  completed: "2026-05-29"
  tasks_completed: 2
  files_changed: 1
---

# Phase 10 Plan 02: Domain Import-Boundary Guard Summary

AST boundary guard widened to forbid `mcp_strava.db` and `mcp_strava.adapters.duckdb` imports across five domain modules, with out-of-band RED proof that the guard catches the storage-leak class that let the original violation ship green.

## What Was Built

- `test_read_modules_do_not_import_storage_strava_or_refresh` (renamed from `test_read_modules_do_not_import_strava_or_refresh`) — covers all five domain modules (training, metrics, cardiac_drift, hr_zones, sports) with a four-prefix disallow tuple: `mcp_strava.adapters.strava`, `mcp_strava.refresh`, `mcp_strava.db`, `mcp_strava.adapters.duckdb`.
- Reuses the existing `_import_violations` AST helper unchanged — handles `import X`, `from X import`, and `from mcp_strava import X` forms.
- Sibling domain imports (e.g. `metrics.py` importing `mcp_strava.cardiac_drift`) remain allowed: the disallowed prefixes are storage/adapter specific, not a broad `mcp_strava` prohibition.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend domain import-boundary guard to forbid storage/adapter imports | 53ba71c | tests/test_security_guards.py |
| 2 | Prove widened guard RED out-of-band (transient inject + revert) | — (no commit — transient only) | — |

## Verification Results

- `PYTHONPATH=src uv run python -m pytest tests/test_security_guards.py -k storage_strava_or_refresh -x -q` — 1 passed
- Working tree clean after revert (`git status --short` empty)

## Out-of-Band RED Proof (Task 2 Evidence)

**Setup:** transiently prepended `from mcp_strava.db import repository_from_connection  # TRANSIENT-RED-PROOF` to `src/mcp_strava/metrics.py`.

**Observed RED (RED_EXIT=1):**
```
FAILED tests/test_security_guards.py::test_read_modules_do_not_import_storage_strava_or_refresh
AssertionError: assert ['src/mcp_strava/metrics.py:1 from mcp_strava.db'] == []
```
Violations list named `metrics.py` importing `mcp_strava.db` — exactly the storage-leak class the guard is designed to catch.

**After revert:** same test passed, printed `REVERTED_GREEN`. Transient import never committed.

**Significance:** this closes the unfalsified-guard blind spot. The previous test only checked strava-adapter and refresh prefixes, so the `mcp_strava.db` import in metrics.py (removed by plan 10-01) was never caught by CI. The widened guard would have failed on the pre-10-01 tree.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — this plan adds only a test; no production code stubs.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. The test itself is the T-10-02 mitigation (domain re-couples to storage via architectural erosion).

## Self-Check: PASSED

- tests/test_security_guards.py: FOUND (contains `test_read_modules_do_not_import_storage_strava_or_refresh`)
- commit 53ba71c: FOUND (`feat(10-02): extend domain import-boundary guard`)
- Transient import absent from working tree: CONFIRMED (git status clean)
