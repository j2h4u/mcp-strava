---
phase: 14
slug: metric-platform-registry-owned-fact-schema
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-31
---

# Phase 14 - Validation Strategy

Per-phase validation contract for feedback sampling during execution and
retroactive Nyquist audit.

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest 9 via `uv` |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`, `pythonpath = ["src"]`) |
| Quick run command | `uv run pytest tests/test_metric_registry.py -q` |
| Focused phase command | `uv run pytest tests/test_metric_registry.py tests/test_duckdb_repository.py tests/test_read_model_materialization.py tests/test_training_aggregates.py -q` |
| Full suite command | `just test` |
| Static gate command | `just check` |
| Estimated runtime | quick: ~1s; focused: ~25s; full: ~3m plus Docker startup |

## Sampling Rate

- After every Task 14-01 commit: run `uv run pytest tests/test_metric_registry.py -q`.
- After every Task 14-02 commit: run `uv run pytest tests/test_metric_registry.py tests/test_duckdb_repository.py -q`.
- After Plan 14-02: run `uv run pytest tests/test_read_model_materialization.py tests/test_training_aggregates.py -q`.
- Before `$gsd-verify-work`: run `just check` and `just test`.
- Max focused feedback latency: 30 seconds for the Phase 14 focused test set.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | Registry-owned SQL metadata contract is specified before implementation | T-14-01-SCHEMA-DRIFT | Unsafe registry SQL fragments are rejected before DDL rendering | contract/unit | `uv run pytest tests/test_metric_registry.py -q` | yes | green |
| 14-01-02 | 01 | 1 | `FactColumnDefinition` carries SQL type, nullability, and default metadata for all materialized fact columns | T-14-01-SCHEMA-DRIFT | Missing SQL metadata, unsafe identifiers, unsupported type tokens, and unsafe defaults fail validation | contract/unit | `uv run pytest tests/test_metric_registry.py -q` | yes | green |
| 14-01-03 | 01 | 1 | `activity_metric_facts_table_sql()` and `activity_metric_fact_add_column_sql()` render the current schema contract | T-14-01-SCHEMA-DRIFT | Generated SQL preserves current constraints and primary key semantics | contract/unit | `uv run pytest tests/test_metric_registry.py -q` | yes | green |
| 14-02-01 | 02 | 2 | Temp DuckDB schema parity verifies registry order, representative type/null/default values, and primary key | T-14-02-DRIFT | Generated DDL cannot drift from registry metadata without failing tests | integration/temp-db | `uv run pytest tests/test_metric_registry.py tests/test_duckdb_repository.py -q` | yes | green |
| 14-02-02 | 02 | 2 | `schema.py` uses registry-generated `activity_metric_facts` table DDL | T-14-02-DRIFT | Runtime schema contains one registry-generated activity fact table definition and keeps tables/views/indexes | integration/temp-db | `uv run pytest tests/test_metric_registry.py -q` | yes | green |
| 14-02-03 | 02 | 2 | Additive late-column migration SQL is registry-generated but policy remains allowlisted | T-14-02-MIGRATION | Old temp fixture receives only the allowed late columns with safe null/default metadata | integration/temp-db | `uv run pytest tests/test_duckdb_repository.py -q` | yes | green |
| 14-02-04 | 02 | 2 | Phase 14 tests do not mutate the live DuckDB mirror | T-14-02-DATA | Tests use `duckdb.connect(":memory:")` or local fixtures only | integration/temp-db | `uv run pytest tests/test_metric_registry.py tests/test_duckdb_repository.py -q` | yes | green |
| 14-03-01 | 03 | 3 | Full quality gates pass after schema cutover | T-14-03-LIVE | No live admin migration/cutover or Strava API call is needed for verification | full-gate | `just check && just test` | yes | green |
| 14-03-02 | 03 | 3 | Phase remains limited to registry-owned `activity_metric_facts` schema generation | T-14-03-LIVE | Scope scan excludes source grammar, computed DAG, rematerialization, and payload-generation expansion | static scan | `rg -n "source=.*detail_json|rematerialize|computed:|ACTIVITY_SCALAR_FACTS" src/mcp_strava tests` | yes | green |

## Gap Analysis

| Gap ID | Requirement | Original Status | Resolution | Status |
|--------|-------------|-----------------|------------|--------|
| G-14-01-SAFE-METADATA | Registry validation rejects malformed identifiers, unsupported `sql_type` tokens, and unsafe `default_sql` values before helper rendering | missing direct test | Added `test_fact_column_sql_metadata_rejects_unsafe_fragments_before_rendering` in `tests/test_metric_registry.py` | resolved |

## Wave 0 Requirements

Existing infrastructure covers all phase requirements:

- `pytest` is already installed in the dev dependency group.
- `pyproject.toml` already configures `testpaths` and `pythonpath`.
- Phase 14 test files already exist under `tests/`.
- No new fixture framework or test harness is required.

## Manual-Only Verifications

All Phase 14 behaviors have automated verification. No manual-only validation
items remain.

## Validation Audit 2026-05-31

| Metric | Count |
|--------|-------|
| Gaps found | 1 |
| Resolved | 1 |
| Escalated | 0 |
| Manual-only | 0 |

## Current Verification Evidence

| Command | Result |
|---------|--------|
| `uv run pytest tests/test_metric_registry.py -q` | `29 passed in 0.81s` |
| `uv run pytest tests/test_metric_registry.py tests/test_duckdb_repository.py tests/test_read_model_materialization.py tests/test_training_aggregates.py -q` | `65 passed in 25.39s` |
| `uv run ruff check tests/test_metric_registry.py && uv run ruff format --check tests/test_metric_registry.py` | `All checks passed!`; `1 file already formatted` |

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Focused feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-31
