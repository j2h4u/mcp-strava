---
phase: 14-metric-platform-registry-owned-fact-schema
verified: 2026-05-31T12:30:38Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
---

# Phase 14: Metric Platform registry-owned fact schema Verification Report

**Phase Goal:** Metric Platform registry-owned fact schema. Verify the first incremental slice: registry-owned SQL metadata/helpers for `activity_metric_facts`, `schema.py` uses generated activity fact DDL and generated late-column ADD COLUMN SQL, explicit migration safety, and no expansion into later metric-platform slices.
**Verified:** 2026-05-31T12:30:38Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1 | Registry owns SQL metadata for materialized fact columns (including `activity_metric_facts`) | ✓ VERIFIED | `FactColumnDefinition` includes `sql_type`, `nullable`, `default_sql` and metadata is populated in `_MATERIALIZED_FACT_COLUMN_SQL_METADATA` ([metric_registry.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/metric_registry.py:1552), [metric_registry.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/metric_registry.py:1574)). |
| 2 | Registry can generate `activity_metric_facts` DDL with current PK semantics | ✓ VERIFIED | `activity_metric_facts_table_sql()` renders column definitions from registry + `PRIMARY KEY (activity_id, metric_version)` ([metric_registry.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/metric_registry.py:2262)). Spot-check confirmed PK present. |
| 3 | `schema.py` uses generated `activity_metric_facts` DDL instead of duplicated inline table definition | ✓ VERIFIED | `DUCKDB_SCHEMA_SQL` includes `{activity_metric_facts_table_sql()}` and imports helper from registry ([schema.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/adapters/duckdb/schema.py:3), [schema.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/adapters/duckdb/schema.py:156)). |
| 4 | Late-column additive migration SQL is generated from registry metadata | ✓ VERIFIED | `ensure_provenance_columns()` calls `activity_metric_fact_add_column_sql(column_name)` for explicit allowlist columns ([schema.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/adapters/duckdb/schema.py:281), [schema.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/adapters/duckdb/schema.py:522)). |
| 5 | Additive migration safety is explicit (no unsafe NOT NULL-without-default additive columns) | ✓ VERIFIED | Guard raises `RuntimeError` if late column is `NOT NULL` and lacks default before executing ALTER ([schema.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/adapters/duckdb/schema.py:523)). Test enforces invariant across allowlist ([test_duckdb_repository.py](/home/j2h4u/repos/j2h4u/mcp-strava/tests/test_duckdb_repository.py:393)). |
| 6 | Temp-DB parity tests verify names/types/nullability/defaults/PK for `activity_metric_facts` | ✓ VERIFIED | `test_activity_metric_fact_schema_matches_registry_metadata` checks representative columns + PK; smoke test checks expected tables/views/index persist ([test_metric_registry.py](/home/j2h4u/repos/j2h4u/mcp-strava/tests/test_metric_registry.py:290), [test_metric_registry.py](/home/j2h4u/repos/j2h4u/mcp-strava/tests/test_metric_registry.py:345)). |
| 7 | Phase 14 remained slice-1 scoped (no expansion into source grammar/computed DAG/rematerialize work) | ✓ VERIFIED | Scope-fence scan found only pre-existing `ACTIVITY_SCALAR_FACTS` references in `application/metric_services.py`; no Phase 14 file in those results. No phase files introduce rematerialize/source-grammar additions. |
| 8 | Verification does not require live DB mutation or Strava API calls | ✓ VERIFIED | Phase tests use `duckdb.connect(':memory:')`/fixtures and schema helpers only ([test_metric_registry.py](/home/j2h4u/repos/j2h4u/mcp-strava/tests/test_metric_registry.py:274), [test_duckdb_repository.py](/home/j2h4u/repos/j2h4u/mcp-strava/tests/test_duckdb_repository.py:348)). No Strava adapter calls in verified slice code paths. |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected    | Status | Details |
| -------- | ----------- | ------ | ------- |
| `src/mcp_strava/metric_registry.py` | Registry-owned fact-column SQL metadata + DDL/ADD COLUMN helpers | ✓ VERIFIED | Exists; substantive (2k+ lines, helper + validation logic); wired into runtime via `schema.py` imports and tests. |
| `src/mcp_strava/adapters/duckdb/schema.py` | Runtime uses registry-generated activity fact table DDL and ADD COLUMN SQL | ✓ VERIFIED | Exists; substantive schema module; wired via `create_schema()` + `ensure_provenance_columns()` using registry helpers. |
| `tests/test_metric_registry.py` | Registry/schema parity + DDL helper contract tests | ✓ VERIFIED | Exists; substantive coverage for metadata, generated DDL, schema parity, smoke checks. |
| `tests/test_duckdb_repository.py` | Additive migration compatibility + safety invariant tests | ✓ VERIFIED | Exists; includes old-table fixture migration verification and late-column safety invariant test. |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `MATERIALIZED_FACT_COLUMN_REGISTRY` | `activity_metric_facts` generated DDL | `materialized_fact_column_definition_sql()` uses `sql_type`/`nullable`/`default_sql` | ✓ WIRED | Registry entry -> definition getter -> SQL renderer -> table SQL builder ([metric_registry.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/metric_registry.py:2244), [metric_registry.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/metric_registry.py:2252), [metric_registry.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/metric_registry.py:2262)). |
| `metric_registry.activity_metric_facts_table_sql` | `schema.create_schema` | Imported helper injected into `DUCKDB_SCHEMA_SQL` | ✓ WIRED | Import in schema module and interpolated into schema SQL executed by `create_schema()` ([schema.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/adapters/duckdb/schema.py:3), [schema.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/adapters/duckdb/schema.py:156), [schema.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/adapters/duckdb/schema.py:536)). |
| Phase 14 scope fence | Slice-1-only implementation | Scan for forbidden expansion patterns | ✓ WIRED | `rg -n "source=.*detail_json|rematerialize|computed:|ACTIVITY_SCALAR_FACTS" src/mcp_strava tests` returned only pre-existing `application/metric_services.py` references. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `metric_registry.py` | `columns` in `activity_metric_facts_table_sql()` | `MATERIALIZED_FACT_COLUMN_REGISTRY["activity_metric_facts"]` -> `materialized_fact_column_definition_sql()` | Yes (full CREATE TABLE statement generated from registry metadata) | ✓ FLOWING |
| `schema.py` | `DUCKDB_SCHEMA_SQL` activity section + late ALTER SQL | `activity_metric_facts_table_sql()` and `activity_metric_fact_add_column_sql()` | Yes (executed SQL creates 44-column table and adds late columns on old fixture) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Generated table SQL contains expected prefix + PK | `uv run python - <<'PY' ... activity_metric_facts_table_sql ... PY` | `table_sql_prefix CREATE TABLE activity_metric_facts (` and `has_pk True` | ✓ PASS |
| Generated ADD COLUMN SQL and late-column safety invariant | `uv run python - <<'PY' ... activity_metric_fact_add_column_sql ... materialized_fact_column_definition ... PY` | `add_col ALTER TABLE ... calories_kcal DOUBLE`; `unsafe_late_cols []` | ✓ PASS |
| Runtime schema creation yields expected activity fact column count | `uv run python - <<'PY' ... create_schema(:memory:) ... PY` | `activity_metric_facts_columns 44` | ✓ PASS |
| Additive migration on old fixture adds all allowlisted late columns | `uv run python - <<'PY' ... ensure_provenance_columns ... PY` | `added_late_cols ['observed_min_hr','observed_max_hr','hr_zone_model','hr_max_used','hr_rest_used','calories_kcal']` | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| None declared/discovered for Phase 14 | `find scripts -path '*/tests/probe-*.sh' ...` + phase grep | No probe files referenced for this phase | ? SKIP |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| Metric platform maintainability / registry source-of-truth | 14-01, 14-02, 14-03 | Registry is the single SQL schema source for `activity_metric_facts` creation and late additive ALTER SQL | ✓ SATISFIED | Registry metadata + helper rendering in [metric_registry.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/metric_registry.py:1574), runtime wiring in [schema.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/adapters/duckdb/schema.py:156) and [schema.py](/home/j2h4u/repos/j2h4u/mcp-strava/src/mcp_strava/adapters/duckdb/schema.py:522), tests in [test_metric_registry.py](/home/j2h4u/repos/j2h4u/mcp-strava/tests/test_metric_registry.py:377) and [test_duckdb_repository.py](/home/j2h4u/repos/j2h4u/mcp-strava/tests/test_duckdb_repository.py:332). |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| None | - | No `TBD`/`FIXME`/`XXX` debt markers; no verified stub patterns in Phase 14 files | ℹ️ Info | No blocker anti-patterns detected |

### Human Verification Required

None.

### Gaps Summary

No gaps found. Phase 14 goal and slice-1 constraints are achieved in code: registry-owned SQL metadata exists, runtime schema uses generated `activity_metric_facts` DDL and generated additive ALTER SQL with explicit safety checks, and scope remains fenced from later metric-platform slices.

---

_Verified: 2026-05-31T12:30:38Z_
_Verifier: the agent (gsd-verifier)_
