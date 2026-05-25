---
quick_id: 260525-jpo
status: completed
---

# Clean Core Metric Registry Without Losing Derived Signals

## Goal

Separate the core metric inventory from MCP exposure and remove only true aliases or empty placeholders.

## Deletion Rules

- The metric registry is a core inventory, not an MCP tool list.
- Every metric or fact that we pull from Strava, calculate, or deliberately derive must be registered.
- `exposed_in` is surface metadata only; a metric may be core-only.
- Delete aliases with no distinct formula or user question.
- Do not delete useful derived helpers such as zones, severities, histories, streaks, and adjusted metrics.
- If a useful registered metric is empty or duplicated, fix the formula/materialization instead of deleting it.

## Scope

- Metric registry and generated metric docs.
- MCP metric services and period comparison mappings.
- SQLite read-model schema, migration inventory, and materializer.
- Dataclasses and tests.
- Runtime database migration with backup before changing `/opt/docker/mcp-strava/data/strava.db`.

## Remove As True Aliases Or Redundant Surface Fields

- `atl` and `ctl` as separate metric ids; use `fatigue` and `fitness`.
- `z5_seconds` as a duplicate metric id; zone buckets remain represented by `time_in_hr_zones_min` and stored `zone5_seconds`.

## Preserve And Fix

- `hr_recovery_pauses`
- `hr_recovery_total_rest_sec`
- `cardiac_drift_quality`
- `cardiac_cost_adjusted`
- `form_zone`
- `acwr_zone`
- `cardiac_drift_severity`
- `cardiac_drift_significant`
- daily, by-sport, history, rolling, trend, streak, and progressive derived signals

## Verification

- Add fail-fast tests preventing reserved/null/skipped registry metrics.
- Run `uv run pytest -q`.
- Run `just test`.
- Back up and migrate the Docker runtime DB only after local tests pass.
- Smoke the live MCP server after migration.

## Result

- Metric registry is treated as a core inventory; MCP exposure is only `exposed_in` metadata.
- Removed only true aliases/redundant ids: `atl`, `ctl`, and registry-level `z5_seconds`.
- Preserved and restored derived helper metrics including `form_zone`, `acwr_zone`, drift quality/severity/significance, adjusted cardiac cost, histories, rolling summaries, streaks, and progressive signals.
- Runtime DB migrated to `user_version=6` with backup at `/opt/docker/mcp-strava/data/backups/strava-20260525T100557Z.db`.
- Read-model materialization is automatic in the refresh worker and bounded by `MCP_STRAVA_READ_MODEL_BATCH_SIZE`.
- Verified with `uv run pytest -q`, `just test`, and MCP read-model performance smoke.
