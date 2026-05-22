---
phase: 06
slug: full-fidelity-strava-mirror
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-22
---

# Phase 06 - Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest plus `just test` |
| Config file | `pyproject.toml` |
| Quick run command | `python3 -m pytest tests/test_full_fidelity_mirror.py tests/test_repository_boundary.py tests/test_refresh_runtime.py -q` |
| Full suite command | `just test` |
| Live/runtime smoke | Docker/runtime-safe checks against `/opt/docker/mcp-strava` only when explicitly run by the operator |

## Sampling Rate

- After each task commit: run the narrow pytest file for the touched surface.
- After each wave: run all accumulated Phase 6 pytest files.
- Before phase verification: run `just test` and the Docker/runtime-safe smoke command planned in `06-04`.
- Max feedback latency: one task.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | MIRROR-01, MIRROR-02, STREAM-02, TEST-05 | T-06-01 | Lossless schema can retain channel metadata and extra values | unit/migration | `python3 -m pytest tests/test_full_fidelity_mirror.py tests/test_sqlite_safety.py -q` | W0 | pending |
| 06-01-02 | 01 | 1 | COVERAGE-01, TEST-05 | T-06-02 | Coverage inventory reports aggregate gaps without raw payload exposure | unit/cli | `python3 -m pytest tests/test_full_fidelity_mirror.py tests/test_cli_surface.py -q` | W0 | pending |
| 06-02-01 | 02 | 2 | STREAM-01, STREAM-02, STREAM-03, TEST-05 | T-06-03 | Refresh preserves known and unknown stream channels | unit/refresh | `python3 -m pytest tests/test_refresh_runtime.py tests/test_repository_boundary.py -q` | W0 | pending |
| 06-03-01 | 03 | 3 | GPS-01, GPS-02, TEST-05 | T-06-04 | GPS migration fills `lat`/`lng`, removes `latlng`, and preserves analytics parity | migration/unit | `python3 -m pytest tests/test_full_fidelity_mirror.py tests/test_sqlite_safety.py -q` | W0 | pending |
| 06-04-01 | 04 | 4 | BACKFILL-01, COVERAGE-01, TEST-05 | T-06-05 | Backfill is resumable, rate-limit-aware, and not a full resync | unit/refresh | `python3 -m pytest tests/test_refresh_runtime.py tests/test_cli_surface.py -q` | W0 | pending |
| 06-04-02 | 04 | 4 | MCP-02, COVERAGE-01, TEST-05 | T-06-06 | MCP remains read-only metrics only and excludes mirror admin surfaces | unit/source | `python3 -m pytest tests/test_mcp_surface.py tests/test_security_guards.py -q` | W0 | pending |

## Wave 0 Requirements

- `tests/test_full_fidelity_mirror.py` covers lossless stream schema, channel metadata, values JSON, GPS migration, coverage aggregation, and parity.
- `tests/test_repository_boundary.py` extends repository stream write tests for `values_json`, `lat`, `lng`, and channel metadata.
- `tests/test_refresh_runtime.py` covers all-channel ingest and resumable backfill with fake Strava transport.
- `tests/test_cli_surface.py` covers admin-only mirror coverage and stream backfill commands.
- `tests/test_mcp_surface.py` and `tests/test_security_guards.py` prove no MCP/admin boundary regression.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live mirror preflight | GPS-02, D-23 | Uses runtime DB under `/opt/docker/mcp-strava` | Run the planned admin preflight/coverage command against `/opt/docker/mcp-strava/data/strava.db` without mutating the DB. |
| Live migration smoke | GPS-02, D-23 | Mutates runtime copy or live DB only under operator control | Execute only after backup confirmation; verify backup path, integrity, row counts, GPS counts, and analytics parity in command output. |
| Backfill dry-run estimate | BACKFILL-01, D-20 | Depends on current live mirror coverage | Run planned `admin backfill-streams --dry-run --json` and confirm it reports remaining activities/channels/API-call estimate without Strava mutation. |

## Validation Sign-Off

- [x] All tasks have automated verification or explicit manual-only justification.
- [x] Sampling continuity: no 3 consecutive tasks without automated verification.
- [x] Wave 0 covers all missing Phase 6 test files.
- [x] No watch-mode flags.
- [x] Feedback latency under one task for unit/source checks.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending execution

