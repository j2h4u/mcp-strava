---
phase: 06
slug: full-fidelity-strava-mirror
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-22
verified_at: 2026-05-24T13:58:53+05:00
---

# Phase 06 - Validation Audit

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest plus `just test` |
| Config file | `pyproject.toml` |
| Quick run command | `uv run pytest tests/test_full_fidelity_mirror.py tests/test_repository_boundary.py tests/test_refresh_runtime.py -q` |
| Full suite command | `uv run pytest -q` |
| Docker smoke command | `just test` |

## Nyquist Gap Audit Result

All Phase 6 verification-map rows were audited against executable behavioral tests and re-run in this validation pass.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | MIRROR-01, MIRROR-02, STREAM-02, TEST-05 | T-06-01 | Lossless schema can retain channel metadata and extra values | unit/migration | `uv run pytest tests/test_full_fidelity_mirror.py tests/test_sqlite_safety.py -q` | yes | COVERED (23 passed) |
| 06-01-02 | 01 | 1 | COVERAGE-01, TEST-05 | T-06-02 | Coverage inventory reports aggregate gaps without raw payload exposure | unit/cli | `uv run pytest tests/test_full_fidelity_mirror.py tests/test_cli_surface.py -q` | yes | COVERED (24 passed) |
| 06-02-01 | 02 | 2 | STREAM-01, STREAM-02, STREAM-03, TEST-05 | T-06-03 | Refresh preserves known and unknown stream channels | unit/refresh | `uv run pytest tests/test_refresh_runtime.py tests/test_repository_boundary.py -q` | yes | COVERED (37 passed) |
| 06-03-01 | 03 | 3 | GPS-01, GPS-02, TEST-05 | T-06-04 | GPS migration fills `lat`/`lng`, removes `latlng`, and preserves analytics parity | migration/unit | `uv run pytest tests/test_full_fidelity_mirror.py tests/test_sqlite_safety.py -q` | yes | COVERED (23 passed) |
| 06-04-01 | 04 | 4 | BACKFILL-01, COVERAGE-01, TEST-05 | T-06-05 | Backfill is resumable, rate-limit-aware, and not a full resync | unit/refresh | `uv run pytest tests/test_refresh_runtime.py tests/test_cli_surface.py -q` | yes | COVERED (35 passed) |
| 06-04-02 | 04 | 4 | MCP-02, COVERAGE-01, TEST-05 | T-06-06 | MCP remains read-only metrics only and excludes mirror admin surfaces | unit/source | `uv run pytest tests/test_mcp_surface.py tests/test_security_guards.py -q` | yes | COVERED (25 passed) |

## Critical Behavioral Tests Confirmed

- `tests/test_cli_surface.py::test_admin_mirror_coverage_json_output` validates aggregate-only mirror coverage output and rejects raw payload/secret leakage.
- `tests/test_full_fidelity_mirror.py::test_replace_stream_rows_and_channel_metadata_preserves_other_activities` validates activity-scoped stream replacement does not corrupt neighboring activities.

## Commands Executed In This Validation Run

- `uv run pytest tests/test_full_fidelity_mirror.py tests/test_sqlite_safety.py -q` -> `23 passed in 0.28s`
- `uv run pytest tests/test_full_fidelity_mirror.py tests/test_cli_surface.py -q` -> `24 passed in 0.23s`
- `uv run pytest tests/test_refresh_runtime.py tests/test_repository_boundary.py -q` -> `37 passed in 0.68s`
- `uv run pytest tests/test_refresh_runtime.py tests/test_cli_surface.py -q` -> `35 passed in 0.45s`
- `uv run pytest tests/test_mcp_surface.py tests/test_security_guards.py -q` -> `25 passed in 1.52s`
- `uv run pytest -q` -> `212 passed, 1 skipped in 12.84s`
- `just test` -> passed; Docker image built, `mcp-strava` container healthy, MCP smoke complete

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live mirror preflight on runtime DB | GPS-02 | Requires operator-controlled runtime DB under `/opt/docker/mcp-strava` | Run runtime preflight/coverage command against `/opt/docker/mcp-strava/data/strava.db` without mutating DB. |
| Live migration smoke | GPS-02 | Mutation against live/runtime copy must remain operator-approved | Run only after backup confirmation and verify backup path, integrity, row counts, GPS counts, analytics parity. |
| Live backfill dry-run estimate | BACKFILL-01 | Depends on current live mirror state and operator API budget | Run `admin backfill-streams --dry-run --json` and verify remaining-work estimate fields without mutation. |

## Validation Sign-Off

- [x] All map rows are now execution-backed (`pending` removed).
- [x] Automated coverage is present for every Phase 6 task row.
- [x] No implementation edits were required.
- [x] `nyquist_compliant: true` remains valid.

**Approval:** verified
