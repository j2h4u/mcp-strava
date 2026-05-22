---
analysis_date: 2026-05-22
last_mapped_commit: b207e64f8293ddb0b3432562705b96a0a0264082
---
# Coding Conventions

**Analysis Date:** 2026-05-22

## Naming Patterns

**Files:**
- Use lower-case module names with underscores under `src/mcp_strava/`, for example `src/mcp_strava/application/metric_services.py`, `src/mcp_strava/adapters/sqlite/repository.py`, and `src/mcp_strava/interfaces/mcp_http.py`.
- Keep package boundaries explicit: `application`, `adapters`, `refresh`, `interfaces`, and `deploy` are separate directories, not mixed utility buckets.

**Functions:**
- Use `snake_case` for functions and helpers, including private helpers such as `_compact_activity()` in `src/mcp_strava/application/workouts.py`, `_validate_ranges()` in `src/mcp_strava/settings.py`, and `_apply_connection_pragmas()` in `src/mcp_strava/adapters/sqlite/connection.py`.
- Keep command and entrypoint functions descriptive and action-oriented, such as `main()`, `build_mcp_server()`, `run_once()`, and `validate_runtime_db()`.

**Variables:**
- Use `snake_case` for local variables and parameters.
- Use explicit names for runtime collaborators and data handles, such as `repo`, `transport`, `policy`, `clock`, `sleeper`, and `connection`.

**Types:**
- Use `PascalCase` for dataclasses, classes, protocols, and enums, such as `Settings`, `SQLiteRepository`, `ServiceEnvelope`, `StravaTransport`, `RefreshPolicy`, and `Stage`.
- Keep dataclasses in `src/mcp_strava/types.py` and adapter-specific contracts in `src/mcp_strava/adapters/strava/types.py`.

**Constants:**
- Use `UPPER_CASE` for module constants, including `MCP_TOOL_NAMES`, `FORBIDDEN_TOOL_NAMES`, `REQUIRED_RUNTIME_TABLES`, `MCP_TOOL_IDS`, and `BACKUP_RETENTION_DEFAULT`.
- Keep tunable values centralized in `src/mcp_strava/constants.py` and runtime settings in `src/mcp_strava/settings.py`.

## Code Style

**Formatting:**
- No repo-local formatter config is detected in `pyproject.toml`; the code follows conventional Python formatting and readability rules.
- Docstrings are the main documentation style. Modules are usually documented with a short purpose string at the top.

**Import Style:**
- Prefer standard-library imports first, third-party imports next, and local `mcp_strava` imports last.
- `from __future__ import annotations` is used where forward references and lighter typing syntax are helpful.
- Import aliases are used intentionally for clarity, for example `import mcp_strava.refresh.runtime as refresh_runtime` in `src/mcp_strava/cli.py`.

**Layout:**
- Prefer thin edge modules and move business logic into `src/mcp_strava/application/` or `src/mcp_strava/adapters/`.
- Keep each module focused on one boundary: CLI dispatch in `src/mcp_strava/cli.py`, HTTP MCP registration in `src/mcp_strava/interfaces/mcp_http.py`, SQLite access in `src/mcp_strava/adapters/sqlite/`, and Strava HTTP behavior in `src/mcp_strava/adapters/strava/`.

## Error Handling

**Patterns:**
- Raise `RuntimeError` for hard fail-closed conditions that should stop the workflow, such as missing runtime DB invariants in `src/mcp_strava/deploy/preflight.py`, schema parity failures in `src/mcp_strava/adapters/sqlite/migrations.py`, and missing auth material in `src/mcp_strava/db.py` and `src/mcp_strava/sync.py`.
- Raise `ValueError` for invalid configuration or unsafe transport settings, such as the host/origin validation in `src/mcp_strava/interfaces/mcp_http.py` and integer range checks in `src/mcp_strava/settings.py`.
- Use `StravaUnavailable` reason codes in `src/mcp_strava/adapters/strava/types.py` to keep adapter failures product-safe and machine-readable.
- Return `None` or incomplete envelope metadata when the data is missing or insufficient instead of inventing defaults, especially in `src/mcp_strava/application/workouts.py`, `src/mcp_strava/application/reports.py`, and `src/mcp_strava/refresh/freshness.py`.
- CLI and runtime entrypoints print human-readable failures to `stderr` and exit non-zero instead of leaking raw tracebacks to callers, unless the command is explicitly a debugging path.

## Logging

**Framework:**
- No logging framework is detected in the scoped files.

**Patterns:**
- Machine-readable command output is usually JSON on `stdout`, as in `src/mcp_strava/cli.py`.
- Validation and smoke failures print concise diagnostics to `stderr`, as in `src/mcp_strava/deploy/preflight.py` and `src/mcp_strava/deploy/smoke.py`.
- Progress and failure handling stay close to the command boundary; there is little evidence of cross-cutting logging helpers.

## Comments

**When to Comment:**
- Comment domain rules, thresholds, and safety rationale.
- Avoid comments that restate trivial syntax or obvious control flow.

**Observed Style:**
- Comments are used to justify thresholds, explain phase-specific behavior, or preserve migration/history notes, for example in `src/mcp_strava/constants.py`, `src/mcp_strava/report.py`, `src/mcp_strava/db.py`, and `src/mcp_strava/deploy/preflight.py`.
- Docstrings are preferred over inline prose for module and function intent.

## Function Design

**Size:**
- Keep functions small and single-purpose.
- Edge handlers should stay thin; the computation belongs in `src/mcp_strava/application/`, `src/mcp_strava/refresh/`, or `src/mcp_strava/adapters/`.

**Parameters:**
- Prefer explicit parameters and keyword-only arguments when a function orchestrates multiple collaborators or optional behaviors.
- Use injectable collaborators instead of hidden globals where possible, especially for `connection`, `clock`, `sleeper`, `transport`, and `policy`.

**Return Values:**
- Return typed dataclasses or structured dicts instead of raw nested dicts once data crosses a module boundary.
- Use envelope objects such as `ServiceEnvelope`, `FreshnessMetadata`, and `CompletenessMetadata` to carry both data and quality metadata.

## Module Design

**Exports:**
- Modules generally export functions and dataclasses directly.
- `src/mcp_strava/__init__.py` is empty, so the package does not act as a barrel file.

**Shared Boundaries:**
- Shared contracts live in `src/mcp_strava/types.py`.
- Shared config lives in `src/mcp_strava/settings.py`.
- Shared algorithm constants live in `src/mcp_strava/constants.py`.
- Repository and adapter boundaries stay explicit in `src/mcp_strava/adapters/sqlite/` and `src/mcp_strava/adapters/strava/`.
- Read-only product exposure is concentrated in `src/mcp_strava/interfaces/mcp_http.py`.

---

*Convention analysis: 2026-05-22*
