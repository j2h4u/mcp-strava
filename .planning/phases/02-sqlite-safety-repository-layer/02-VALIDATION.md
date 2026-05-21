---
phase: 02
slug: sqlite-safety-repository-layer
status: completed
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-21
validated: 2026-05-21
gaps_found: 0
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python3 -m pytest tests/test_sqlite_safety.py tests/test_repository_boundary.py tests/test_load_status.py tests/test_security_guards.py -q` |
| **Full suite command** | `just test` |
| **Estimated runtime** | ~30 seconds |

## Sampling Rate

- **After every task commit:** Run the focused pytest command named by that task.
- **After every plan wave:** Run `just test`.
- **Before `$gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 30 seconds for focused tests.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | SAFE-01/SAFE-04/TEST-01 | T-02-01/T-02-02 | Missing/corrupt expected DB fails closed before writes | unit | `python3 -m pytest tests/test_sqlite_safety.py -q` | exists | covered |
| 02-01-02 | 01 | 1 | SAFE-02/SAFE-03/TEST-01 | T-02-03 | Backup is openable and synthetic migration proves row/load parity helpers with frozen `as_of` inputs | unit | `python3 -m pytest tests/test_sqlite_safety.py -q` | exists | covered |
| 02-02-01 | 02 | 2 | REPO-01/REPO-02 | T-02-04 | Repository connection owns WAL/busy-timeout policy | unit | `python3 -m pytest tests/test_repository_boundary.py -q` | exists | covered |
| 02-02-02 | 02 | 2 | REPO-01/REPO-02 | T-02-05 | Activities, streams, zones, kudos, sync log flow through focused repository methods | unit | `python3 -m pytest tests/test_repository_boundary.py -q` | exists | covered |
| 02-03-01 | 03 | 2 | REPO-03/SAFE-03 | T-02-06 | Missing HR/stream sessions are not collapsed into rest days and `training.py` consumes deterministic effective TRIMP inputs | unit | `python3 -m pytest tests/test_load_status.py -q` | exists | covered |
| 02-04-01 | 04 | 3 | SAFE-01/SAFE-02/SAFE-03/SAFE-04/REPO-01/REPO-02/REPO-03/TEST-01 | T-02-07 | Runtime paths use repository/migration gates, `init_db()` is absent or assertion-only, `metrics.py` is behind repository helpers, and operator SQL stays isolated | integration | `just test` | exists | covered |

## Wave 0 Requirements

- [x] `tests/test_sqlite_safety.py` — covers preflight, fail-closed open, backup, post-check, synthetic migration parity, frozen `as_of` numeric parity, and retention.
- [x] `tests/test_repository_boundary.py` — covers WAL/busy-timeout repository connection policy, repository methods, AST boundary guard, and no live network.
- [x] `tests/test_load_status.py` — covers `REST`, `UNKNOWN`, `PARTIAL`, `OBSERVED`, `effective_trimp=0.0` on missing-data statuses, and observed numeric load preservation through `training.py`.
- [x] `tests/test_security_guards.py` — covers runtime/sync paths not calling schema-changing `init_db()` and `metrics.py` having no direct stream/activity SQL after repository adoption.

## Requirement Coverage

| Requirement | Status | Automated Evidence |
|-------------|--------|--------------------|
| SAFE-01 | covered | `tests/test_sqlite_safety.py`, `tests/test_security_guards.py`, `just test` |
| SAFE-02 | covered | `tests/test_sqlite_safety.py`, `tests/test_security_guards.py`, `just test` |
| SAFE-03 | covered | `tests/test_sqlite_safety.py`, `tests/test_load_status.py`, `just test` |
| SAFE-04 | covered | `tests/test_sqlite_safety.py`, `tests/test_security_guards.py`, `just test` |
| REPO-01 | covered | `tests/test_repository_boundary.py`, `tests/test_security_guards.py`, `just test` |
| REPO-02 | covered | `tests/test_repository_boundary.py`, `tests/test_security_guards.py`, `just test` |
| REPO-03 | covered | `tests/test_load_status.py`, `tests/test_security_guards.py`, `just test` |
| TEST-01 | covered | `python3 -m pytest tests/test_sqlite_safety.py tests/test_repository_boundary.py tests/test_load_status.py tests/test_security_guards.py -q`, `just test` |

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real mirror operator check | SAFE-01/SAFE-02/SAFE-03/SAFE-04 | Must remain explicit and outside default tests by D-18 | Run `python3 -m mcp_strava db-preflight` or `python3 -m mcp_strava db-check` against the configured DB when the operator intentionally wants a live mirror check. |

## Validation Audit 2026-05-21

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Requirements covered by automated verification | 8/8 |

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all MISSING references.
- [x] No watch-mode flags.
- [x] Feedback latency < 30 seconds for focused tests.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** verified 2026-05-21
