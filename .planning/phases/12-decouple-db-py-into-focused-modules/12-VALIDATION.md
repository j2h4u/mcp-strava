---
phase: 12
slug: decouple-db-py-into-focused-modules
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-30
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) |
| **Quick run command** | `uv run pytest -q tests/<touched>.py -x` |
| **Full suite command** | `uv run pytest -q` (323 tests) then `just test` (Docker build + container smoke) |
| **Estimated runtime** | ~5–15 s local pytest; ~90 s `just test` smoke |

---

## Sampling Rate

- **After every task commit:** Run targeted `uv run pytest -q tests/<touched>.py -x`
- **After every plan wave:** Run `uv run pytest -q` (full local suite, 323 tests)
- **Before `/gsd-verify-work`:** `uv run pytest -q` green AND `just test` (Docker smoke) green — both required before `db.py` deletion
- **Max feedback latency:** ~15 s (local pytest)

---

## Per-Task Verification Map

> Tasks are placeholders keyed to the planned waves; the planner finalizes exact IDs.
> No behavior change in this phase — every command re-runs EXISTING tests against relocated code.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-* | 01 | 1 | Core/domain separation | T-12-01 | Connection helpers behave identically after relocation | unit | `uv run pytest -q tests/test_repository_boundary.py tests/test_metric_services.py -x` | ✅ | ⬜ pending |
| 12-01-* | 01 | 1 | Core/domain separation | — | Thread-local read pool reuse + reset preserved verbatim | unit | `uv run pytest -q tests/test_metric_services.py::test_read_path_reuses_connection_and_checks_schema_once -x` | ✅ | ⬜ pending |
| 12-02-* | 02 | 1 | Core/domain separation | T-12-02 | StravaClient maps StravaUnavailable→RuntimeError, secret never echoed | unit | `uv run pytest -q tests/test_security_guards.py -x` | ✅ | ⬜ pending |
| 12-03-* | 03 | 2 | Core/domain separation | T-12-01 | Migrated callers import from new homes; read paths still network-isolated | unit | `uv run pytest -q tests/test_security_guards.py tests/test_repository_boundary.py -x` | ✅ | ⬜ pending |
| 12-04-* | 04 | 3 | Core/domain separation | — | Tests + conftest retargeted; smoke/phase01 use new connection home | unit | `uv run pytest -q tests/test_smoke.py tests/test_phase01_validation.py -x` | ✅ | ⬜ pending |
| 12-05-* | 05 | 4 | Core/domain separation | — | db.py deleted; full behavior parity incl. MCP surface | smoke | `uv run pytest -q && just test` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.* The 323-test suite is the regression net (CONTEXT.md D-10: no new characterization tests — no behavior change). Test edits in this phase are **retargeting** existing tests to new import paths, not adding coverage.

---

## Manual-Only Verifications

*All phase behaviors have automated verification.* The `just test` smoke gate exercises the live MCP surface in a container; no human-only step is required.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none — existing suite suffices)
- [x] No watch-mode flags
- [x] Feedback latency < 15s (local pytest)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
