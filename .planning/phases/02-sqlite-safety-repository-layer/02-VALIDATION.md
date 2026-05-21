---
phase: 02
slug: sqlite-safety-repository-layer
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-21
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python3 -m pytest tests/test_sqlite_safety.py tests/test_repository_boundary.py tests/test_load_status.py -q` |
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
| 02-01-01 | 01 | 1 | SAFE-01/SAFE-04/TEST-01 | T-02-01/T-02-02 | Missing/corrupt expected DB fails closed before writes | unit | `python3 -m pytest tests/test_sqlite_safety.py -q` | W0 creates | pending |
| 02-01-02 | 01 | 1 | SAFE-02/SAFE-03/TEST-01 | T-02-03 | Backup is openable and parity can be checked before/after migration | unit | `python3 -m pytest tests/test_sqlite_safety.py -q` | W0 creates | pending |
| 02-02-01 | 02 | 2 | REPO-01/REPO-02 | T-02-04 | Repository connection owns WAL/busy-timeout policy | unit | `python3 -m pytest tests/test_repository_boundary.py -q` | W0 creates | pending |
| 02-02-02 | 02 | 2 | REPO-01/REPO-02 | T-02-05 | Activities, streams, zones, kudos, sync log flow through focused repository methods | unit | `python3 -m pytest tests/test_repository_boundary.py -q` | W0 creates | pending |
| 02-03-01 | 03 | 2 | REPO-03/SAFE-03 | T-02-06 | Missing HR/stream sessions are not collapsed into rest days | unit | `python3 -m pytest tests/test_load_status.py -q` | W0 creates | pending |
| 02-04-01 | 04 | 3 | SAFE-01/SAFE-02/SAFE-03/SAFE-04/REPO-01/REPO-02/REPO-03/TEST-01 | T-02-07 | Runtime paths use repository/migration gates and keep operator SQL isolated | integration | `just test` | existing + prior plans | pending |

## Wave 0 Requirements

- [ ] `tests/test_sqlite_safety.py` — failing tests for preflight, fail-closed open, backup, post-check, parity, and retention.
- [ ] `tests/test_repository_boundary.py` — failing tests for WAL/busy-timeout repository connection policy, repository methods, boundary guard, and no live network.
- [ ] `tests/test_load_status.py` — failing tests for `REST`, `UNKNOWN`, `PARTIAL`, `OBSERVED`, and observed numeric load preservation.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real mirror operator check | SAFE-01/SAFE-02/SAFE-03/SAFE-04 | Must be explicit and must not run in default tests | Run the planned local CLI preflight/check command against the configured DB after reviewing that it reports only and does not apply migrations unless requested. |

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify.
- [ ] Wave 0 covers all MISSING references.
- [ ] No watch-mode flags.
- [ ] Feedback latency < 30 seconds for focused tests.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
