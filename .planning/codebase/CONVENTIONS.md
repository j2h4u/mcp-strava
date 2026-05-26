---
analysis_date: 2026-05-26
last_mapped_commit: ab203ab
---
# Coding Conventions

**Analysis Date:** 2026-05-26

## Scope

- This incremental map is scoped to `README.md`, `mcp-content/`, and `tests/`, with minimal command/config context from `pyproject.toml` and `Justfile`.
- Use these conventions for work that touches scoped artifacts: product documentation in `README.md`, prompt content in `mcp-content/prompts/`, and pytest coverage in `tests/`.
- Source-code conventions below are included only where the scoped tests enforce them by importing, monkeypatching, or AST-reading `src/mcp_strava/...` files from `tests/`.

## Naming Patterns

**Files:**
- Use lower-case Python test modules with underscores under `tests/`, for example `tests/test_mcp_surface.py`, `tests/test_read_model_queries.py`, and `tests/test_refresh_runtime.py`.
- Keep reusable test-only protocol fixtures under `tests/fixtures/`, for example `tests/fixtures/fake_mcp_server.py`.
- Keep MCP prompt content as lower-case, underscore-separated markdown files under `mcp-content/prompts/`, for example `mcp-content/prompts/strava_daily_training_brief.md`.
- Do not place source tests or prompt content under generated cache directories such as `tests/__pycache__/`.

**Functions:**
- Use `snake_case` for test helpers and test functions in `tests/`, for example `_create_fixture_db()`, `_repo_with_facts()`, `_install_product_service_spies()`, and `test_mcp_tool_allowlist_is_exact()`.
- Prefix private test helpers with `_` and keep them local to the module that owns the fixture shape, as in `tests/test_application_services.py` and `tests/test_training_aggregates.py`.
- Name behavior tests after the contract they lock, not just the implementation method, as in `tests/test_security_guards.py::test_product_service_registry_excludes_admin_debug_commands`.
- Phase/UAT identifiers may appear in test names when they preserve planning traceability, as in `tests/test_refresh_runtime.py::test_run_once_completes_daily_refresh_per_REFRESH_01_STRAVA_03`.

**Variables:**
- Use explicit `snake_case` names for fixture resources and collaborators, for example `db_path`, `tmp_path`, `repo`, `transport`, `policy`, `clock`, `sleeper`, and `connection` in `tests/test_refresh_runtime.py`.
- Use all-caps constants for expected contracts and forbidden surface terms, for example `EXPECTED_TOOL_NAMES` in `tests/test_mcp_surface.py`, `FORBIDDEN_KEYS` in `tests/test_metric_services.py`, and `REQUIRED_LOCAL_STATE_PATTERNS` in `tests/test_repo_hygiene.py`.
- Prefer descriptive fixture filenames under `tmp_path`, for example `application-services.db` in `tests/test_application_services.py`, `read-model.db` in `tests/test_read_model_materialization.py`, and `strava.duckdb` in `tests/test_duckdb_repository.py`.

**Types:**
- Use `PascalCase` for fake collaborator classes in tests, for example `FakeClock`, `FakeSleeper`, `FakeStravaTransport`, `FakeWarmScriptClient`, and `FakeLiveSmokeClient` in `tests/test_refresh_runtime.py`, `tests/test_strava_adapter.py`, and `tests/test_mcp_test_client.py`.
- Annotate test parameters and return values where the module already opts into typed tests, for example `tmp_path: Path`, `monkeypatch: pytest.MonkeyPatch`, and `capsys: pytest.CaptureFixture[str]` in `tests/test_cli_surface.py` and `tests/test_docker_runtime.py`.
- Use `ServiceEnvelope`, `FreshnessMetadata`, `CompletenessMetadata`, `ServiceWarning`, and `ServiceRationale` in tests when constructing product-service outputs, as shown in `tests/test_cli_surface.py` and `tests/test_mcp_surface.py`.

## Code Style

**Formatting:**
- No formatter configuration is detected in scoped metadata; `pyproject.toml` contains pytest settings but no `black`, `ruff`, or formatter section.
- Keep Python formatting conventional and readable in `tests/`: standard imports first, third-party imports next, local `mcp_strava` imports last, as in `tests/test_docker_runtime.py` and `tests/test_product_fact_bundles.py`.
- Use `from __future__ import annotations` in new typed test modules when forward references or modern type syntax are used, matching `tests/test_mcp_test_client.py`, `tests/test_cli_surface.py`, and `tests/test_training_aggregates.py`.
- Prefer double-quoted strings in new tests where surrounding files use them, such as `tests/test_refresh_runtime.py` and `tests/test_mcp_surface.py`; keep local quote style consistent when editing files that already use single quotes, such as `tests/test_settings.py`.

**Linting:**
- No linter configuration is detected in `pyproject.toml` or `Justfile`.
- Existing static guard tests use `ast` directly for repository, CLI, product-boundary, and security rules in `tests/test_repository_boundary.py`, `tests/test_cli_surface.py`, and `tests/test_security_guards.py`.

**Prompt Content:**
- Keep prompt files in `mcp-content/prompts/` user-facing, concise, and scenario-specific.
- Prompt content in `mcp-content/prompts/strava_daily_training_brief.md`, `mcp-content/prompts/strava_weekly_training_digest.md`, and `mcp-content/prompts/strava_shoe_mileage_watchdog.md` is Russian-language guidance for agent responses.
- MCP prompts must list allowed Strava MCP tools explicitly and must not ask the user to run sync/admin/debug/raw SQL operations; `tests/test_mcp_surface.py` checks prompt names and content-backed exposure.
- Prompt format guidance uses Telegram Markdown in `mcp-content/prompts/strava_daily_training_brief.md` and `mcp-content/prompts/strava_weekly_training_digest.md`.

## Import Organization

**Order:**
1. Standard library imports, for example `json`, `sqlite3`, `urllib.request`, `datetime`, `pathlib.Path`, and `types.SimpleNamespace` in `tests/test_refresh_runtime.py`.
2. Third-party imports, mainly `pytest` and `duckdb`, as in `tests/test_docker_runtime.py` and `tests/test_metric_registry.py`.
3. Local package imports from `mcp_strava...` and cross-test fixture imports from `tests...`, as in `tests/test_product_fact_bundles.py` and `tests/test_read_model_materialization.py`.

**Path Aliases:**
- `pyproject.toml` sets `pythonpath = ["src"]`, so tests import application code as `mcp_strava...` rather than modifying `sys.path`.
- Subprocess tests that run module entrypoints set `PYTHONPATH=src` explicitly, as in `tests/test_security_guards.py::test_module_entrypoint_runs_from_source_tree_with_pythonpath`.

## Error Handling

**Patterns:**
- Use `pytest.raises(..., match=...)` when testing fail-closed behavior and user-facing error text, as in `tests/test_mcp_surface.py`, `tests/test_docker_runtime.py`, `tests/test_strava_adapter.py`, and `tests/test_duckdb_migration.py`.
- Use strict negative assertions for secret redaction and product-surface safety, for example `tests/test_strava_adapter.py::test_tokens_never_appear_in_errors_or_output_per_D10_D18` and `tests/test_cli_surface.py::test_admin_mirror_coverage_json_output`.
- Preserve fail-closed behavior for missing/corrupt runtime data by asserting no file creation or non-zero return codes, as in `tests/test_docker_runtime.py::test_duckdb_preflight_missing_or_corrupt_file_fails_closed`.
- For product and MCP boundaries, assert forbidden command names, fields, and advice phrases are absent rather than relying only on positive examples, as in `tests/test_mcp_surface.py`, `tests/test_metric_services.py`, and `tests/test_training_aggregates.py`.

## Logging

**Framework:** `console`

**Patterns:**
- Tests capture CLI and worker output with `capsys` instead of a logging framework, as in `tests/test_cli_surface.py`, `tests/test_mcp_test_client.py`, and `tests/test_refresh_runtime.py`.
- JSON command output should be asserted by parsing stdout with `json.loads()`, as in `tests/test_cli_surface.py` and `tests/test_phase4_e2e.py`.
- Error and traceback visibility is tested through stderr when the behavior requires it, for example `tests/test_refresh_runtime.py::test_worker_logs_exception_message_and_traceback`.
- Do not print secret-bearing env file contents; `tests/test_docker_runtime.py::test_prepare_runtime_never_prints_env_contents` and `tests/test_strava_adapter.py::test_tokens_never_appear_in_errors_or_output_per_D10_D18` lock that rule.

## Comments

**When to Comment:**
- Use comments sparingly in tests; prefer descriptive helper names and assertion names in `tests/`.
- Add comments only for domain-specific guard intent or fixture setup that would be unclear from the helper name, following the explicit contract style in `tests/test_security_guards.py`.
- In `mcp-content/prompts/`, use bullets and short sections instead of inline implementation commentary.

**JSDoc/TSDoc:**
- Not applicable; scoped code is Python and Markdown in `tests/`, `mcp-content/`, and `README.md`.
- Python tests under `tests/` generally do not use docstrings; test names and helper names carry the contract.

## Function Design

**Size:** Keep new tests focused on one contract per test function in `tests/`; if setup grows, extract private helpers such as `_create_fixture_db()` in `tests/test_repository_boundary.py` or `_aggregate_fixture()` in `tests/test_training_aggregates.py`.

**Parameters:** Prefer explicit pytest fixtures (`tmp_path`, `monkeypatch`, `capsys`) and explicit service collaborators (`repo`, `transport`, `policy`, `clock`, `sleeper`) over implicit global state, matching `tests/test_refresh_runtime.py` and `tests/test_strava_adapter.py`.

**Return Values:** Test helpers may return concrete resources such as `SQLiteRepository`, `Path`, `sqlite3.Connection`, `dict[str, object]`, or `ServiceEnvelope`; examples live in `tests/test_read_model_queries.py`, `tests/test_training_aggregates.py`, and `tests/test_cli_surface.py`.

## Module Design

**Exports:** Test modules in `tests/` are not public API; keep helpers private unless deliberately shared, as with `_aggregate_fixture()` in `tests/test_training_aggregates.py` and `_repo_with_facts()` in `tests/test_read_model_queries.py`.

**Barrel Files:** `tests/__init__.py` is effectively empty; do not add shared test exports there unless a repeated cross-test helper becomes a deliberate package-level fixture.

**Boundary Guards:**
- Keep architectural and safety guard tests in purpose-named modules: repository access in `tests/test_repository_boundary.py`, CLI/product split in `tests/test_cli_surface.py`, security imports/surfaces in `tests/test_security_guards.py`, and repo state policy in `tests/test_repo_hygiene.py`.
- Keep product prompt exposure checks with MCP surface tests in `tests/test_mcp_surface.py`, because prompt names and MCP tool names are part of the same user-facing surface.

---

*Convention analysis: 2026-05-26*
