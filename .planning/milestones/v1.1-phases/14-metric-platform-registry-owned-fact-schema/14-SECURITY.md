---
phase: 14
slug: metric-platform-registry-owned-fact-schema
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-31
register_authored_at_plan_time: true
---

# Phase 14 - Security

Per-phase security contract: threat register, accepted risks, and audit trail for
Metric Platform registry-owned fact schema.

## Security Scope

Phase 14 moved `activity_metric_facts` SQL definition ownership into the metric
registry and cut DuckDB schema creation and late-column migration SQL over to
registry-generated helpers. The audit covers only that slice: registry metadata,
generated DDL, additive late-column migration policy, and verification gates.

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| registry metadata | Import-time registry data is rendered into DuckDB SQL for materialized fact columns | SQL type, nullability, default, table and column identifiers |
| schema metadata -> DuckDB DDL | Registry-rendered strings become runtime DuckDB DDL for `activity_metric_facts` | Generated `CREATE TABLE` and `ALTER TABLE ADD COLUMN` SQL |
| existing DuckDB files -> additive migration | Repository initialization may call generated late-column migration SQL on existing local DB files | Existing local mirror schema plus allowlisted late columns |
| verification only | Phase verification runs local checks and tests without live admin migration commands | Local test process, temp DuckDB databases, Docker smoke |
| dependency supply chain | Phase plans accepted unchanged dependency risk by installing no new packages | Existing dependency set only |

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-14-01-SCHEMA-DRIFT | Tampering | fact-column SQL metadata | mitigate | `FactColumnDefinition` now carries `sql_type`, `nullable`, and `default_sql`; registry validation rejects unsafe identifiers, unsupported type tokens, and unsafe defaults; tests assert generated DDL fragments match the current contract. Evidence: `src/mcp_strava/metric_registry.py:1552`, `src/mcp_strava/metric_registry.py:2069`, `tests/test_metric_registry.py:386`, `tests/test_metric_registry.py:392`. | closed |
| T-14-SC | Tampering | dependency supply chain | accept | No packages were installed and no dependency files were changed by Phase 14; the residual dependency risk is unchanged from project baseline and recorded in the accepted risks log. Evidence: plan summaries record `tech_stack.added: []`; Phase 14 commit history contains no `pyproject.toml` or `uv.lock` changes. | closed |
| T-14-02-DRIFT | Tampering | generated `activity_metric_facts` DDL | mitigate | `schema.py` injects `activity_metric_facts_table_sql()` into `DUCKDB_SCHEMA_SQL`; temp-DuckDB tests compare registry order, representative types, nullability, defaults, and primary key; smoke tests preserve expected tables, views, and index. Evidence: `src/mcp_strava/adapters/duckdb/schema.py:156`, `src/mcp_strava/metric_registry.py:2262`, `tests/test_metric_registry.py:290`, `tests/test_metric_registry.py:345`, `tests/test_metric_registry.py:377`. | closed |
| T-14-02-MIGRATION | Tampering | existing local DuckDB files | mitigate | Additive migration scope remains an explicit late-column allowlist; `ensure_provenance_columns()` fails fast for `NOT NULL` columns without defaults before executing generated `ALTER TABLE`; old-fixture tests prove allowlisted columns are added with registry-owned type/null/default metadata. Evidence: `src/mcp_strava/adapters/duckdb/schema.py:281`, `src/mcp_strava/adapters/duckdb/schema.py:518`, `tests/test_duckdb_repository.py:332`, `tests/test_duckdb_repository.py:393`. | closed |
| T-14-02-DATA | Information Disclosure | live Strava mirror | mitigate | Tests and verification use `duckdb.connect(':memory:')` or test fixtures only; Phase 14 verification explicitly confirms no live DuckDB mutation or Strava API calls were required. Evidence: `tests/test_metric_registry.py:273`, `tests/test_metric_registry.py:290`, `tests/test_duckdb_repository.py:348`, `.planning/phases/14-metric-platform-registry-owned-fact-schema/14-VERIFICATION.md`. | closed |
| T-14-03-LIVE | Tampering | live DuckDB mirror | mitigate | Final gates ran `just check`, `just test`, Docker health, MCP smoke, and the scope-fence scan; no live admin migration/cutover command or Strava API operation was required. Evidence: `.planning/phases/14-metric-platform-registry-owned-fact-schema/14-03-SUMMARY.md`, `.planning/phases/14-metric-platform-registry-owned-fact-schema/14-VERIFICATION.md`. | closed |

## Summary Threat Flags

No additional `## Threat Flags` sections were present in the Phase 14 summary
artifacts. The security register is built from the authored plan-time
`<threat_model>` blocks in `14-01-PLAN.md`, `14-02-PLAN.md`, and
`14-03-PLAN.md`.

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-14-SC | T-14-SC | Phase 14 installed no packages and did not modify dependency metadata, so dependency supply-chain exposure remains unchanged from the already accepted project baseline. | GSD plan-time disposition | 2026-05-31 |

Accepted risks do not resurface in future audit runs.

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-31 | 6 | 6 | 0 | Codex |

## Verification Evidence

| Command or Artifact | Result |
|---------------------|--------|
| `uv run pytest tests/test_metric_registry.py -q -x` | `25 passed` after 14-01 registry metadata setup |
| `uv run pytest tests/test_metric_registry.py tests/test_duckdb_repository.py -q -x` | `36 passed` after 14-02 schema cutover and additive migration tests |
| `uv run pytest tests/test_read_model_materialization.py tests/test_training_aggregates.py -q -x` | `27 passed` after 14-02 compatibility checks |
| `just check` | `ruff`, `ruff format --check`, and `pyright` passed in 14-03 |
| `just test` | Full pytest, Docker build, container health, and MCP smoke passed in 14-03 |
| Scope fence scan | Only pre-existing `ACTIVITY_SCALAR_FACTS` references in `application/metric_services.py`; Phase 14 did not add later-slice source grammar, computed DAG, rematerialization, or payload-generation work |
| Phase verification report | `status: passed`, `score: 8/8 must-haves verified`, including no live DB mutation or Strava API calls |

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-31
