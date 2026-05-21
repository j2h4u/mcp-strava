---
phase: 03
slug: strava-adapter-refresh-runtime
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-21
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python3 -m pytest tests/test_strava_adapter.py tests/test_refresh_runtime.py tests/test_security_guards.py tests/test_repository_boundary.py -q` |
| **Full suite command** | `just test` |
| **Estimated runtime** | ~30 seconds (no live network) |

---

## Sampling Rate

- **After every task commit:** Run the focused pytest command named by that task.
- **After every plan wave:** Run `just test`.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 30 seconds for focused tests.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | STRAVA-01/STRAVA-02/TEST-02 | T-03-01/T-03-02 | Adapter tests assert token provider is single-writer/atomic, transport raises typed errors, rate-limit policy tracks both window pairs | unit | `python3 -m pytest tests/test_strava_adapter.py -q` | ❌ Wave 0 | pending |
| 03-01-02 | 01 | 1 | STRAVA-01/STRAVA-02/TEST-02 | T-03-01/T-03-02/T-03-03 | `adapters/strava/` package implements TokenProvider, StravaTransport, RateLimitPolicy; never logs tokens | unit | `python3 -m pytest tests/test_strava_adapter.py -q` | ❌ Wave 0 | pending |
| 03-02-01 | 02 | 2 | REFRESH-01/REFRESH-03/STRAVA-03/TEST-02 | T-03-04/T-03-05 | Refresh-runtime tests prove checkpoint resume, lease atomicity, dual-window rate-limit backoff, freshness state machine | unit | `python3 -m pytest tests/test_refresh_runtime.py -q` | ❌ Wave 0 | pending |
| 03-02-02 | 02 | 2 | REFRESH-01/REFRESH-03/STRAVA-03 | T-03-04/T-03-05 | `refresh/` package implements runtime, checkpoints, freshness state machine; uses repository for all SQLite writes | unit | `python3 -m pytest tests/test_refresh_runtime.py -q` | ❌ Wave 0 | pending |
| 03-03-01 | 03 | 2 | REFRESH-02/REFRESH-03/STRAVA-03 | T-03-06 | Repository methods for `refresh_state` and `refresh_requests` are atomic, idempotent, and exposed through `SQLiteRepository`; migration v2 adds tables through Phase 2 migration gate | unit | `python3 -m pytest tests/test_repository_boundary.py -q` | ❌ Wave 0 | pending |
| 03-04-01 | 04 | 3 | STRAVA-01/REFRESH-02/TEST-02 | T-03-07 | Read modules (report, analytics, trends, training, metrics) do not import `mcp_strava.adapters.strava` or `mcp_strava.refresh`; sync.py replaced with thin compatibility layer using the new adapter; CLI `db-refresh` wired | integration | `just test` | exists / extended | pending |

*Status: pending · green · red · flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_strava_adapter.py` — covers STRAVA-01, STRAVA-02, TEST-02. Tests token provider concurrency (subprocess or threaded flock), atomic write under crash injection, rate-limit policy across both header pairs, transport retry/backoff with fake clock/sleeper, never-log-token assertion.
- [ ] `tests/test_refresh_runtime.py` — covers STRAVA-03, REFRESH-01, REFRESH-02, REFRESH-03. Tests checkpoint resume per stage, lease acquisition atomicity, freshness state machine over fixture rows, idempotent refresh_requests dedupe, run_once() reaches `complete`.
- [ ] Extend `tests/test_security_guards.py` — add boundary tests proving `report.py`, `analytics.py`, `trends.py`, `training.py`, `metrics.py` do not import `mcp_strava.adapters.strava` or `mcp_strava.refresh`; sync.py only imports the adapter through dependency injection in the entrypoint.
- [ ] Extend `tests/test_repository_boundary.py` — assert SQLiteRepository exposes `get_refresh_state`, `acquire_refresh_lease`, `release_refresh_lease`, `set_checkpoint`, `record_refresh_attempt`, `record_refresh_success`, `record_refresh_failure`, `enqueue_refresh_request`, `pending_refresh_requests`, `mark_refresh_requests_consumed` (exact names per planner discretion); no direct sqlite3 import added outside adapters.

*If existing tests already cover behavior:* `tests/test_repository_boundary.py` is extended rather than replaced.

---

## Requirement Coverage

| Requirement | Status | Automated Evidence |
|-------------|--------|--------------------|
| STRAVA-01 | covered | `tests/test_strava_adapter.py`, `tests/test_security_guards.py`, `just test` |
| STRAVA-02 | covered | `tests/test_strava_adapter.py::test_token_provider_is_single_writer`, `tests/test_strava_adapter.py::test_token_provider_atomic_write_survives_crash`, `just test` |
| STRAVA-03 | covered | `tests/test_refresh_runtime.py::test_resume_from_checkpoint`, `tests/test_refresh_runtime.py::test_rate_limit_backoff_then_resume`, `just test` |
| REFRESH-01 | covered | `tests/test_refresh_runtime.py::test_daily_completion`, `just test` |
| REFRESH-02 | covered | `tests/test_refresh_runtime.py::test_freshness_signal`, `tests/test_refresh_runtime.py::test_refresh_request_dedupe`, `tests/test_security_guards.py` boundary tests, `just test` |
| REFRESH-03 | covered | `tests/test_refresh_runtime.py::test_lease_concurrency`, `tests/test_repository_boundary.py`, `just test` |
| TEST-02 | covered | `python3 -m pytest tests/test_strava_adapter.py tests/test_refresh_runtime.py -q` (no internet required), `just test` |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Strava OAuth refresh | STRAVA-01/STRAVA-02 | Default tests must not make live HTTP calls (D-16, TEST-02). | Run `python3 -m mcp_strava db-refresh` against the real `.env` only when the operator intentionally wants a live sync; verify `data/strava.db` mirror updates and `refresh_state.last_success_at` advances. |
| Daily-completion scheduler integration | REFRESH-01 | Phase 5 owns container/supervisor; Phase 3 only ships `run_once()`. | Phase 5 operator wires systemd timer / docker entrypoint; manual sanity check that one `run_once()` per local day reaches the `complete` checkpoint. |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies.
- [ ] Sampling continuity: every task includes an `<automated>` command.
- [ ] Wave 0 covers all MISSING test files.
- [ ] No watch-mode flags; all tests run headlessly.
- [ ] Feedback latency < 30 seconds for focused commands.
- [ ] `nyquist_compliant: true` set in frontmatter once Wave 0 tasks land.

**Approval:** pending (set to `approved YYYY-MM-DD` after Wave 0 lands)
