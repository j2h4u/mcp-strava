---
analysis_date: 2026-05-26
last_mapped_commit: ab203ab
scope:
  - README.md
  - mcp-content
  - tests
---

# Codebase Concerns

**Analysis Date:** 2026-05-26

## Tech Debt

**Duplicated database fixtures across tests:**
- Issue: SQLite and DuckDB schemas are embedded in many test helpers instead of coming from one shared fixture builder.
- Files: `tests/test_sqlite_safety.py:12`, `tests/test_repository_boundary.py:11`, `tests/test_refresh_runtime.py:96`, `tests/test_read_model_queries.py:22`, `tests/test_metric_services.py:67`, `tests/test_application_services.py:21`, `tests/test_full_fidelity_mirror.py:16`, `tests/test_phase4_e2e.py:13`, `tests/test_duckdb_migration.py:32`
- Impact: schema changes require many coordinated edits; stale fixture DDL can make tests pass against shapes that production migrations no longer create.
- Fix approach: use one fixture factory under `tests/` for base mirror schemas, migrated read-model schemas, and DuckDB cutover fixtures; keep per-test data rows local.

**Source-shape guards are spread across the suite:**
- Issue: Several tests parse or read source files directly to enforce boundaries through string and AST assertions.
- Files: `tests/test_security_guards.py:40`, `tests/test_security_guards.py:69`, `tests/test_security_guards.py:286`, `tests/test_security_guards.py:527`, `tests/test_repository_boundary.py:60`, `tests/test_read_model_queries.py:529`, `tests/test_docker_runtime.py:253`
- Impact: these guards are valuable for security and architecture boundaries, but their duplicated scan logic makes legitimate refactors noisy and expensive to maintain.
- Fix approach: centralize AST/source guard helpers in `tests/` and keep behavior tests as the first line of defense; reserve source-shape assertions for forbidden imports, public exposure, and local-state safety.

**Prompt contracts are partly test-backed and partly manual:**
- Issue: the MCP prompt names are tested, but only the daily prompt body is inspected for content.
- Files: `tests/test_mcp_surface.py:239`, `mcp-content/prompts/strava_daily_training_brief.md:5`, `mcp-content/prompts/strava_weekly_training_digest.md:5`, `mcp-content/prompts/strava_shoe_mileage_watchdog.md:5`
- Impact: the weekly digest and shoe mileage prompts can drift into unsupported tools, admin operations, or unsafe interpretation language without a direct prompt-body regression.
- Fix approach: parameterize prompt-content tests across all files under `mcp-content/prompts/` and assert allowed tools, forbidden admin/sync/raw-SQL language, medical-safety wording, and no internal file paths.

## Known Bugs

**README storage contract conflicts with Docker/DuckDB expectations:**
- Symptoms: `README.md` describes the mirror as local SQLite and documents `/opt/docker/mcp-strava/data/strava.db` as the runtime facts path, while scoped tests assert DuckDB-primary container paths.
- Files: `README.md:5`, `README.md:122`, `tests/test_docker_runtime.py:47`, `tests/test_docker_runtime.py:62`, `tests/test_settings.py:11`, `tests/test_settings.py:47`
- Trigger: a new operator following `README.md` prepares or inspects `strava.db` while the Docker-facing tests expect `/runtime/data/strava.duckdb`.
- Workaround: use the Docker and deployment commands tested in `tests/test_docker_runtime.py` rather than the README path table.

**README MCP tool list omits the aggregate tool:**
- Symptoms: `README.md` lists workouts, workout detail, period comparison, fitness state, and projection, but the scoped MCP surface tests require `get_training_aggregates`.
- Files: `README.md:11`, `tests/test_mcp_surface.py:16`, `tests/test_mcp_surface.py:183`, `tests/test_mcp_latency_gate.py:124`, `tests/test_mcp_test_client.py:170`
- Trigger: users relying on the README do not see the training aggregate surface that tests treat as part of the product contract.
- Workaround: use `just mcp-list-tools` from `README.md:109` to inspect the live surface.

## Security Considerations

**Strava credential setup can leak through shell history or process listing:**
- Risk: the token exchange example passes `client_secret` and authorization code on the command line, and the `.env` heredoc writes secrets before `chmod 600` is applied.
- Files: `README.md:51`, `README.md:63`
- Current mitigation: `README.md:24` tells operators to treat `.env` as secret material, and `README.md:73` applies `chmod 600`.
- Recommendations: document a `umask 077` or `install -m 600 /dev/null .env` flow before writing secrets, and prefer reading the Strava secret from a protected file or environment variable instead of placing it directly in a shell command.

**Runtime overlay permissions are allowed to be world-readable:**
- Risk: `live.env` is documented as an operator env overlay and its test accepts `0644`; this is safe only if it never contains credentials or sensitive host policy.
- Files: `README.md:123`, `README.md:124`, `tests/test_docker_runtime.py:546`, `tests/test_docker_runtime.py:551`
- Current mitigation: OAuth credentials are documented separately in `/opt/docker/mcp-strava/.env`.
- Recommendations: keep `live.env` explicitly non-secret in documentation and tighten the accepted mode to `0600` or `0640` if operators can place sensitive overrides there.

**Public HTTP exposure is protected by tests but remains high-risk configuration:**
- Risk: local mode must reject wildcard binds, and container mode may bind `0.0.0.0` only behind constrained host/origin policy.
- Files: `README.md:95`, `tests/test_mcp_surface.py:258`, `tests/test_security_guards.py:801`, `tests/test_docker_runtime.py:52`
- Current mitigation: tests assert no public compose port binding, explicit allowed hosts/origins, and local fail-closed behavior.
- Recommendations: keep the compose surface un-published by default, require explicit operator intent for container binds, and include real `just smoke` or `just mcp-smoke-full` checks after deployment changes.

## Performance Bottlenecks

**Repeated source-tree parsing in tests:**
- Problem: multiple tests walk `src/mcp_strava` with `rglob("*.py")` and parse modules independently.
- Files: `tests/test_security_guards.py:69`, `tests/test_security_guards.py:286`, `tests/test_security_guards.py:527`, `tests/test_security_guards.py:547`, `tests/test_security_guards.py:579`, `tests/test_repository_boundary.py:65`, `tests/test_refresh_runtime.py:838`
- Cause: each boundary guard owns its own scan logic.
- Improvement path: build a cached source inventory fixture for tests that need AST import/call checks, and keep per-test assertions focused on their rule.

**Latency gate unit tests do not measure the product runtime:**
- Problem: the latency tests validate threshold logic with fake clients and artificial sleeps, not the Docker HTTP MCP server.
- Files: `tests/test_mcp_latency_gate.py:18`, `tests/test_mcp_latency_gate.py:36`, `tests/test_mcp_latency_gate.py:81`, `tests/test_mcp_test_client.py:141`, `README.md:106`
- Cause: pytest-level tests cover client math and call selection, while runtime performance is delegated to `just mcp-read-model-perf`.
- Improvement path: keep `just mcp-read-model-perf` as a required verification gate for read-model changes and record the command in phase acceptance checks, not only in README.

**Large fixture-heavy tests create scaling pressure:**
- Problem: the scoped test suite is fixture-dense, with `tests/test_training_aggregates.py`, `tests/test_refresh_runtime.py`, `tests/test_metric_services.py`, and `tests/test_read_model_materialization.py` carrying many rows, schemas, and date windows.
- Files: `tests/test_training_aggregates.py:264`, `tests/test_refresh_runtime.py:96`, `tests/test_metric_services.py:67`, `tests/test_read_model_materialization.py:317`
- Cause: rich coverage is built through repeated local database construction.
- Improvement path: use reusable seeded fixture builders and keep expensive scenario matrices explicit, so new metrics do not multiply setup cost across unrelated tests.

## Fragile Areas

**Hard-coded product surface names require coordinated edits:**
- Files: `tests/test_mcp_surface.py:16`, `tests/test_mcp_surface.py:25`, `tests/test_mcp_latency_gate.py:124`, `tests/test_mcp_test_client.py:170`
- Why fragile: adding, renaming, or retiring an MCP tool or prompt requires edits in several independent allowlists.
- Safe modification: update the product registry first, then update a single exported expected-surface contract used by MCP surface, latency, and smoke-client tests.
- Test coverage: surface drift is well guarded, but the guard data is duplicated.

**README is not included in the docs drift tests:**
- Files: `README.md:5`, `README.md:11`, `tests/test_metric_registry.py:249`, `tests/test_cli_surface.py:585`, `tests/test_docker_runtime.py:103`
- Why fragile: the suite checks `docs/metrics.md`, `docs/cli.md`, and `docs/deployment.md`, while README storage and tool-surface text can diverge from tested behavior.
- Safe modification: add a lightweight README contract test for runtime storage path, product tool names, and the admin/MCP boundary.
- Test coverage: README drift is visible only through manual review in the scoped files.

**Shoe mileage prompt is ahead of a dedicated shoe-mileage surface:**
- Files: `mcp-content/prompts/strava_shoe_mileage_watchdog.md:7`, `mcp-content/prompts/strava_shoe_mileage_watchdog.md:12`, `tests/test_product_fact_bundles.py:322`, `tests/test_metric_registry.py:499`, `tests/test_training_aggregates.py:894`
- Why fragile: the prompt encodes 500 km and 800 km thresholds, while gear facts are tested as context/detail facts rather than aggregate filters or a dedicated mileage endpoint.
- Safe modification: keep the prompt conservative until the MCP surface exposes complete shoe mileage facts, then move thresholds into a typed service contract or registry entry.
- Test coverage: gear facts are covered as supported detail facts, but the watchdog prompt behavior is not tested end to end.

## Scaling Limits

**Prompt and surface contracts scale by duplicated constants:**
- Current capacity: three prompts and six product tools are covered by hard-coded tuples in scoped tests.
- Limit: each new prompt/tool increases the number of allowlists and latency-call fixtures that must stay in sync.
- Scaling path: expose the canonical product surface from one runtime module and have tests compare against that registry instead of repeating names.

**Source-guard scans scale with repository size:**
- Current capacity: the suite scans a modest `src/mcp_strava` tree several times per run.
- Limit: repeated `rglob` plus AST parse checks add test latency as modules grow.
- Scaling path: cache parsed ASTs or consolidate guard rules into one source-boundary test module.

## Dependencies at Risk

**Python minor version check conflicts with plus-version documentation:**
- Risk: README says Python 3.14+, but the Docker runtime test requires exactly Python 3.14.
- Impact: a future Python 3.15-compatible environment can fail `tests/test_docker_runtime.py` even if package metadata remains valid.
- Migration plan: either document the runtime as exactly Python 3.14 or relax `tests/test_docker_runtime.py:22` to match the `>=3.14` contract.

**DuckDB dependency is tightly pinned by test and metadata:**
- Risk: `tests/test_docker_runtime.py` asserts the loaded DuckDB version starts with `1.5.` and metadata pins `<1.6`.
- Impact: security or correctness fixes that require DuckDB 1.6+ need coordinated code, test, and deployment changes.
- Migration plan: introduce an explicit DuckDB upgrade phase with migration parity tests and runtime smoke before widening the dependency range.

## Missing Critical Features

**Dedicated shoe mileage query surface:**
- Problem: the shoe mileage prompt exists, but scoped tests keep gear facts out of aggregates and only verify gear facts as detail/context data.
- Blocks: a reliable watchdog answer for per-shoe lifetime mileage without asking the agent to infer across arbitrary workout detail calls.

**README contract verification:**
- Problem: README carries setup, runtime-state, and tool-surface claims that are not directly checked by the docs regression tests.
- Blocks: confidence that the first-run operator path matches the tested Docker/DuckDB product surface.

## Test Coverage Gaps

**Weekly and shoe prompt body checks:**
- What's not tested: allowed tools, forbidden admin/sync/raw operations, medical-safety wording, and unsupported-feature behavior for weekly and shoe prompts.
- Files: `mcp-content/prompts/strava_weekly_training_digest.md`, `mcp-content/prompts/strava_shoe_mileage_watchdog.md`, `tests/test_mcp_surface.py:239`
- Risk: prompt drift can violate the MCP boundary while the prompt-name test still passes.
- Priority: High

**README drift checks:**
- What's not tested: README storage backend wording, runtime paths, and full product MCP tool list.
- Files: `README.md`, `tests/test_metric_registry.py:249`, `tests/test_cli_surface.py:585`, `tests/test_docker_runtime.py:103`
- Risk: new setup or operation work follows stale README guidance.
- Priority: Medium

**Real runtime performance gate in pytest:**
- What's not tested: warm read-model latency against the actual Docker HTTP MCP server during `uv run pytest -q`.
- Files: `tests/test_mcp_latency_gate.py`, `tests/test_mcp_test_client.py`, `README.md:106`
- Risk: fake-client latency tests pass while live `get_training_aggregates` or detail calls exceed the product latency budget.
- Priority: Medium

**Environment-dependent daily report smoke:**
- What's not tested: `daily_report()` behavior when `data/strava.db` is absent from the developer checkout.
- Files: `tests/test_smoke.py:63`, `tests/test_smoke.py:67`, `tests/test_smoke.py:73`
- Risk: the local smoke suite can skip an end-to-end report path on machines without a mirror database.
- Priority: Low

---

*Concerns audit: 2026-05-26*
