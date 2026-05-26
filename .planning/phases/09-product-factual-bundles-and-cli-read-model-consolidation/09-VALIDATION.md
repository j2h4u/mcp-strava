---
phase: 09
slug: product-factual-bundles-and-cli-read-model-consolidation
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-26
state: B-reconstructed-from-artifacts
auditor: codex
---

# Phase 09 - Validation Strategy

State B reconstruction from Phase 09 plans, summaries, security, verification artifacts, current tests, and current command output.

Result: no Nyquist validation gaps found. Existing behavioral tests cover every Phase 09 requirement, and the targeted phase commands, full pytest suite, direct MCP smoke, Docker smoke, and warm p95 gate are green.

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest via `uv run pytest` |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py` |
| Phase targeted commands | Plan-specific commands in the Per-Task Verification Map |
| Full suite command | `uv run pytest -q` |
| Direct server smoke | `just phase9-bundle-smoke` |
| Docker smoke | `just test` |
| Warm p95 gate | `just mcp-read-model-perf 20 2 500` |
| Estimated feedback latency | pytest target 1-14s; full pytest ~22s; Docker/direct smoke depends on image/cache state |

## Sampling Rate

- After every Phase 09 task commit: run that task's targeted pytest command.
- After every plan wave: run `uv run pytest -q`.
- Before verification closeout: run `just phase9-bundle-smoke`, `just test`, and `just mcp-read-model-perf 20 2 500`.
- Gateway smoke is intentionally out of scope for Phase 09 validation.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01 | 01 | 1 | APP-01 | T-09-01-R | Daily factual bundle rows and status metadata are registry-backed. | integration | `uv run pytest -q tests/test_metric_registry.py tests/test_training_aggregates.py` | yes | green |
| 09-01 | 01 | 1 | APP-02 | T-09-01-D | Weekly/historical aggregate bundles handle mixed scopes and bounded windows. | integration | `uv run pytest -q tests/test_metric_registry.py tests/test_training_aggregates.py` | yes | green |
| 09-01 | 01 | 1 | MCP-01 | T-09-01-E | Aggregate facts do not add MCP tools or admin capabilities. | unit/integration | `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py tests/test_security_guards.py` | yes | green |
| 09-01 | 01 | 1 | MCP-03 | T-09-01-R | Aggregate service envelopes expose freshness, completeness, calculation, and read-model metadata. | integration | `uv run pytest -q tests/test_metric_registry.py tests/test_training_aggregates.py` | yes | green |
| 09-01 | 01 | 1 | READMODEL-01 | T-09-01-T | Materialized fact columns and query columns are registry-derived with version/provenance fields. | unit/integration | `uv run pytest -q tests/test_metric_registry.py tests/test_training_aggregates.py` | yes | green |
| 09-01 | 01 | 1 | READMODEL-04 | T-09-01-T | Historical/status facts query prepared DuckDB/read-model views, not absent columns or raw stream recompute. | integration | `uv run pytest -q tests/test_metric_registry.py tests/test_training_aggregates.py` | yes | green |
| 09-01 | 01 | 1 | TEST-03 | T-09-01-E | Boundary tests enforce no forbidden MCP/admin expansion. | unit | `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py tests/test_security_guards.py` | yes | green |
| 09-01 | 01 | 1 | TEST-06 | T-09-01-D | Query-shape and read-model smoke coverage exists for Phase 09 bundles. | integration/smoke | `uv run pytest -q tests/test_metric_registry.py tests/test_training_aggregates.py` | yes | green |
| 09-02 | 02 | 2 | APP-01 | T-09-02-R | Daily brief service returns factual sections and explicit bundle completeness. | integration | `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py tests/test_metric_services.py` | yes | green |
| 09-02 | 02 | 2 | APP-02 | T-09-02-D | Weekly digest service returns load, volume, efficiency, sport, and trend facts. | integration | `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py tests/test_metric_services.py` | yes | green |
| 09-02 | 02 | 2 | APP-03 | T-09-02-I | Recent workouts and workout detail facts come from local read-model services with kudos/gear shaping. | integration | `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py tests/test_metric_services.py` | yes | green |
| 09-02 | 02 | 2 | APP-04 | T-09-02-R | Freshness/read-model status is included in product service envelopes. | integration | `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py tests/test_metric_services.py` | yes | green |
| 09-02 | 02 | 2 | MCP-01 | T-09-02-E | Product bundles are exposed through existing aggregate service paths only. | integration | `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py tests/test_security_guards.py` | yes | green |
| 09-02 | 02 | 2 | MCP-03 | T-09-02-R | Bundle payloads contain freshness, completeness, read-model, and reason-code metadata. | integration | `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py tests/test_metric_services.py` | yes | green |
| 09-02 | 02 | 2 | READMODEL-04 | T-09-02-T | Bundle services do not call Strava, sync, raw SQL, token refresh, or legacy recompute paths. | unit | `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | yes | green |
| 09-02 | 02 | 2 | TEST-04 | T-09-02-I | Product tests cover freshness, missing-data completeness, no-advice text, daily/weekly/historical parity, kudos, and gear facts. | integration | `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py tests/test_metric_services.py` | yes | green |
| 09-02 | 02 | 2 | TEST-06 | T-09-02-D | Aggregate service keeps rows and adds bundle sections only for scenario bundles. | integration | `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py tests/test_metric_services.py` | yes | green |
| 09-03 | 03 | 3 | CLI-01 | T-09-03-S | Root CLI exposes product commands plus namespaced local admin commands. | smoke/unit | `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | yes | green |
| 09-03 | 03 | 3 | CLI-02 | T-09-03-D | CLI product handlers delegate to application/read-model services. | unit | `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | yes | green |
| 09-03 | 03 | 3 | CLI-03 | T-09-03-R | Removed legacy commands have documented and tested replacement paths. | unit | `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | yes | green |
| 09-03 | 03 | 3 | APP-01 | T-09-03-R | `report daily --json` uses the daily product fact service. | smoke/unit | `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | yes | green |
| 09-03 | 03 | 3 | APP-02 | T-09-03-R | `weekly --json` uses the weekly product fact service. | smoke/unit | `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | yes | green |
| 09-03 | 03 | 3 | APP-03 | T-09-03-I | `workouts recent` and `workout analyze` use metric services and expose kudos/gear detail facts. | smoke/unit | `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | yes | green |
| 09-03 | 03 | 3 | APP-04 | T-09-03-I | `freshness` remains a product read command while mutating refresh paths remain admin-only. | smoke/unit | `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | yes | green |
| 09-03 | 03 | 3 | MCP-02 | T-09-03-E | Sync/backfill/raw/API/SQL/token/admin/log controls are absent from MCP/product registries. | unit | `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | yes | green |
| 09-03 | 03 | 3 | TEST-03 | T-09-03-E | AST guards prove dead handlers/imports and admin names are absent from product/MCP paths. | unit | `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | yes | green |
| 09-03 | 03 | 3 | TEST-04 | T-09-03-I | CLI JSON envelopes and replacement paths preserve current product behavior. | smoke/unit | `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | yes | green |
| 09-04 | 04 | 4 | MCP-01 | T-09-04-S | MCP tool allowlist remains exactly the six product tools. | unit/smoke | `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py tests/test_security_guards.py` | yes | green |
| 09-04 | 04 | 4 | MCP-02 | T-09-04-E | MCP schemas and payloads exclude sync/admin/raw/sql/token/log/debug fields. | unit/smoke | `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py tests/test_security_guards.py` | yes | green |
| 09-04 | 04 | 4 | MCP-03 | T-09-04-R | MCP bundle responses include rows, sections, completeness, freshness, calculation, and read-model metadata. | integration/smoke | `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py tests/test_security_guards.py` | yes | green |
| 09-04 | 04 | 4 | PERF-01 | T-09-04-D | Warm product MCP calls stay below 500 ms p95, with startup measured separately. | smoke/perf | `just mcp-read-model-perf 20 2 500` | yes | green |
| 09-04 | 04 | 4 | TEST-03 | T-09-04-S | Tests enforce exact tool allowlist and forbidden tool absence. | unit | `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py tests/test_security_guards.py` | yes | green |
| 09-04 | 04 | 4 | TEST-04 | T-09-04-I | Tests cover no-advice/no-admin payloads, daily brief composition, and completeness reason codes. | integration | `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py tests/test_security_guards.py` | yes | green |
| 09-04 | 04 | 4 | TEST-06 | T-09-04-D | Direct MCP bundle smoke, Docker smoke, and full suite cover query shape and runtime behavior. | smoke | `just phase9-bundle-smoke && just test` | yes | green |

## Wave 0 Requirements

Existing infrastructure covers all Phase 09 requirements.

- No missing test framework setup.
- No missing test file stubs.
- No generated validation-gap tests were required during this audit.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| none | none | All Phase 09 behaviors have automated verification. | none |

## Audit Trail

| Audit Date | Input State | Gaps Found | Resolved By New Tests | Escalated | Result |
|------------|-------------|------------|-----------------------|-----------|--------|
| 2026-05-26 | State B - no existing validation file, plans/summaries/security/verification present | 0 | 0 | 0 | Nyquist compliant |

## Commands Run

| Command | Result |
|---------|--------|
| `uv run pytest -q tests/test_metric_registry.py tests/test_training_aggregates.py` | 44 passed in 7.26s |
| `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py tests/test_metric_services.py` | 36 passed in 13.63s |
| `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` | 52 passed in 2.42s |
| `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py tests/test_security_guards.py` | 49 passed in 2.66s |
| `uv run pytest -q tests/test_mcp_latency_gate.py tests/test_application_reports.py tests/test_application_workouts.py tests/test_smoke.py` | 22 passed, 1 skipped in 0.79s |
| `uv run pytest -q` | 353 passed, 1 skipped in 21.85s |
| `just phase9-bundle-smoke` | Passed: 19 pytest tests, direct smoke status `ok`, six MCP tools, and bundle calls for `daily_brief`, `weekly_digest`, and `historical_facts` |
| `just mcp-read-model-perf 20 2 500` | Passed: status `ok`; worst warm p95 was `list_workouts` at 100.721 ms, below 500 ms |
| `just test` | Passed: Docker build/recreate healthy; smoke-basic status `ok` and six MCP tools |

## Post-UAT Validation Update

| Date | Change | Command | Result |
|------|--------|---------|--------|
| 2026-05-26 | Added a regression test proving `get_freshness_service()` routes primary connections through `repository_from_connection()` instead of forcing SQLite. | `uv run pytest -q tests/test_application_services.py tests/test_phase4_e2e.py::test_phase4_cli_freshness_json_uses_fixture_sqlite_without_strava` | 7 passed |
| 2026-05-26 | Re-ran the full suite after the UAT freshness fix. | `uv run pytest -q` | 354 passed, 1 skipped |

## Gap Analysis Notes

- No `no_test_file` gaps found. The relevant Phase 09 test files already exist and target behavior rather than only structure.
- No `test_fails` gaps found. Every targeted command and the full suite passed.
- No `no_automated_command` gaps found. Each requirement maps to pytest, direct MCP smoke, Docker smoke, or the warm p95 command.
- No gateway validation was run or required; Phase 09 product validation is direct-server and test-suite scoped.

## Validation Sign-Off

- [x] All tasks have automated verification.
- [x] Sampling continuity: no three consecutive tasks without automated verification.
- [x] Wave 0 dependencies are complete; no missing stubs or framework setup.
- [x] No watch-mode flags are used in validation commands.
- [x] Manual-only verification list is none.
- [x] `nyquist_compliant: true` is set in frontmatter.

Approval: verified 2026-05-26
