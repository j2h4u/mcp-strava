---
phase: 6
security_status: SECURED
threats_reviewed: 12
threats_open: 0
threats_deferred: 0
verified_at: 2026-05-24T00:00:00Z
---

# Phase 06 Security Verification

## Verdict
`SECURED`.

## Threat Verification

| Threat | Category | Disposition | Verdict | Mitigation Evidence | Residual Risk |
|---|---|---|---|---|---|
| 06-01 T-06-01 | Tampering (SQLite migration) | mitigate | CLOSED | Migration enforces row parity and inventory checks: `run_migrations` parity loop and inventory/integrity gates in `src/mcp_strava/adapters/sqlite/migrations.py:400-425`; versioned required inventory in `src/mcp_strava/adapters/sqlite/schema.py:11-17`, `src/mcp_strava/adapters/sqlite/schema.py:79-125`, `src/mcp_strava/adapters/sqlite/schema.py:225-255`; tests assert v3/v4 inventory contracts in `tests/test_full_fidelity_mirror.py:148-159`. | Low once migration gates remain mandatory. |
| 06-01 T-06-02 | Information Disclosure (Coverage CLI) | mitigate | CLOSED | Coverage command returns aggregate-only payload in `src/mcp_strava/application/mirror_coverage.py:88-100`, and regression test now seeds token-like values in `summary_json`/`detail_json` then asserts coverage output excludes `summary_json`, `detail_json`, `summary-secret`, `detail-secret`, `access_token`, and `refresh_token` in `tests/test_cli_surface.py:231-254`. | Low. |
| 06-01 T-06-03 | Information Integrity (Stream metadata) | mitigate | CLOSED | Unknown/future channels retained into `values_json` and metadata in `_stream_payload` (`src/mcp_strava/refresh/_sync_ops.py:152-163`, `src/mcp_strava/refresh/_sync_ops.py:115-129`); repository metadata upsert/merge path in `src/mcp_strava/adapters/sqlite/repository.py:748-947`; tests assert unknown key retention and metadata availability in `tests/test_refresh_runtime.py:500-577`. | Low. |
| 06-02 T-06-03 | Information Integrity (Stream parser) | mitigate | CLOSED | Fake transport test verifies unknown key flows to `values_json` and `latlng` excluded: `tests/test_refresh_runtime.py:522`, `tests/test_refresh_runtime.py:564-570`. | Low. |
| 06-02 T-06-04 | Tampering (Stream replacement) | mitigate | CLOSED | Replacement transaction remains activity-scoped in `src/mcp_strava/adapters/sqlite/repository.py:801-805`, and regression test now creates neighboring activity stream rows + metadata, replaces activity `10`, then asserts activity `20` rows/metadata remain unchanged in `tests/test_full_fidelity_mirror.py:234-330`. | Low. |
| 06-02 T-06-05 | Denial of Service (Uneven channel lengths) | mitigate | CLOSED | Parser tolerates missing/out-of-range values via `_channel_value` bounds check and per-index guards in `src/mcp_strava/refresh/_sync_ops.py:69-73`, `src/mcp_strava/refresh/_sync_ops.py:152-154`; missing channels recorded as unavailable metadata in `src/mcp_strava/refresh/_sync_ops.py:86-101`; test asserts unavailable rows without failing sync in `tests/test_refresh_runtime.py:580-617`. | Low. |
| 06-03 T-06-04 | Tampering (GPS migration) | mitigate | CLOSED | Backup + integrity + row-count + gps-count checks block completion in `src/mcp_strava/adapters/sqlite/migrations.py:381-425`; canonicalization path in `src/mcp_strava/adapters/sqlite/migrations.py:298-367`; tests cover idempotence and parity signals in `tests/test_full_fidelity_mirror.py:411-456`. | Low. |
| 06-03 T-06-05 | Repudiation (Migration output) | mitigate | CLOSED | Failure messages include parity dimension/table and backup path in `src/mcp_strava/adapters/sqlite/migrations.py:403-404`, `src/mcp_strava/adapters/sqlite/migrations.py:419-424`. | Low. |
| 06-03 T-06-06 | Denial of Service (Malformed local `latlng`) | mitigate | CLOSED | Malformed JSON is tolerated (`_json_latlng_pair` returns `None`) in `src/mcp_strava/adapters/sqlite/migrations.py:191-205`; malformed/conflict tracking in `src/mcp_strava/adapters/sqlite/migrations.py:232-253`; tests cover malformed row handling without aborting migration in `tests/test_full_fidelity_mirror.py:397`, `tests/test_full_fidelity_mirror.py:440-456`. | Low. |
| 06-04 T-06-05 | Denial of Service (Backfill runtime) | mitigate | CLOSED | Backoff/checkpoint logic in runtime `run_backfill_stream_channels` and failure handling: `src/mcp_strava/refresh/runtime.py:171-224`, `src/mcp_strava/refresh/runtime.py:229-240`; checkpoint stage definitions in `src/mcp_strava/refresh/checkpoints.py:8-20`; tests cover dry-run estimation, resumability/checkpoints, and rate-limit behavior in `tests/test_refresh_runtime.py:619-673`, `tests/test_refresh_runtime.py:758-805`. | Low. |
| 06-04 T-06-06 | Information Disclosure (MCP surface) | mitigate | CLOSED | MCP allowlist and forbidden tool names in `src/mcp_strava/interfaces/mcp_http.py:21-54`; test enforces exact allowlist and forbidden disjointness in `tests/test_mcp_surface.py:15-48`, `tests/test_mcp_surface.py:76-81`. | Low. |
| 06-04 T-06-07 | Tampering (Live runtime DB) | mitigate | CLOSED | Tests use temp/copy DBs (`tmp_path`) across phase suites, for example `tests/test_full_fidelity_mirror.py:118`, `tests/test_repository_boundary.py:368-373`, `tests/test_docker_runtime.py:60-116`; runtime preflight fails closed for missing/invalid DB in `src/mcp_strava/deploy/preflight.py:45-72`; operator-only live smoke steps documented in verification artifact with explicit admin commands on copied DB (`.planning/phases/06-full-fidelity-strava-mirror/06-VERIFICATION.md:74-75`). | Low if operators keep using copied DB + preflight flow. |

## Threat Flags Review

| Threat Flag | Mapping | Result |
|---|---|---|
| `threat_flag: migration-surface` (`06-03-SUMMARY`) | Maps to planned GPS migration threat family (`T-06-04` / `T-06-05` / `T-06-06`) | Informational only; no unregistered flag. |

## Test Run Note

This re-audit validated the two prior blocker threats directly in code/tests and incorporated orchestrator verification results:
- `uv run pytest tests/test_cli_surface.py::test_admin_mirror_coverage_json_output tests/test_full_fidelity_mirror.py::test_replace_stream_rows_and_channel_metadata_preserves_other_activities` -> `2 passed`
- `uv run pytest` -> `212 passed, 1 skipped`
- `just test` -> passed (Docker + MCP smoke complete)
