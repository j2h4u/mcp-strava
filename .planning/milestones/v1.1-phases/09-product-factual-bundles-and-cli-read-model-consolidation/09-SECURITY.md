---
phase: 09-product-factual-bundles-and-cli-read-model-consolidation
phase_number: 09
slug: product-factual-bundles-and-cli-read-model-consolidation
status: verified
threats_open: 0
threats_total: 28
threats_closed: 28
asvs_level: 1
security_block_on: high
created: 2026-05-26
auditor: codex
---

# Phase 09 - Security

## Security Result

SECURED. All plan-authored threat mitigations from plans 09-01 through 09-04 were verified against implemented code, tests, or deployment docs. Implementation and tests were not modified.

## Trust Boundaries

| Boundary | Description |
|---|---|
| MCP/CLI request -> aggregate query builder | Product request parameters select bundle, metric, date, scope, sport, and window behavior. |
| Registry metadata -> DuckDB SQL templates | Registered metric metadata selects whitelisted sources, columns, aggregate modes, and windows. |
| Read model -> product payload | Local activity, status, kudos, gear, freshness, and read-model facts become CLI/MCP-visible payloads. |
| Admin namespace -> local storage/runtime operations | Mutating refresh, backfill, raw, SQL, token, migration, and cutover controls remain local admin commands. |
| Documentation -> operator commands | Deployment commands can be copied into runtime verification and must not promote product/admin boundary breaks. |

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|---|---|---|---|---|
| 09-01/T-09-01-S | Spoofing | mitigate | closed | `AggregateRequest` exposes no gear/equipment filter (`src/mcp_strava/adapters/duckdb/aggregate_queries.py:24`); `sport_filter` is rejected unless present in `ALL_SPORTS` (`aggregate_queries.py:102`); invalid gear/sport requests are tested (`tests/test_training_aggregates.py:1121`). |
| 09-01/T-09-01-T | Tampering | mitigate | closed | SQL value/sample/denominator columns are checked against registry-derived `_ALLOWED_COLUMNS` (`aggregate_queries.py:92`, `aggregate_queries.py:982`); date/window/sport predicates use bound parameters (`aggregate_queries.py:918`); allowed columns are built from registry metadata (`src/mcp_strava/application/metric_registry.py:1257`). |
| 09-01/T-09-01-R | Repudiation | mitigate | closed | `StatusFactDefinition` and `StatusFact` include code, metric id, threshold, window, evidence, completeness, calculation, and materialized source (`src/mcp_strava/types.py:927`); status facts copy those fields from registry definitions (`aggregate_queries.py:447`). |
| 09-01/T-09-01-I | Information Disclosure | mitigate | closed | `kudos_names` is added only in workout detail (`src/mcp_strava/application/metric_services.py:479`); aggregate bundles exclude `kudos_names` and gear metrics (`tests/test_metric_registry.py:475`, `tests/test_metric_registry.py:499`); gear output is shaped mirrored fields only (`metric_services.py:255`). |
| 09-01/T-09-01-D | Denial of Service | mitigate | closed | Supported aggregate buckets/scopes/windows are finite registry constants (`metric_registry.py:32`); request windows are validated (`aggregate_queries.py:109`); mixed `both` requests split by metric-supported scope only (`aggregate_queries.py:554`). |
| 09-01/T-09-01-E | Elevation of Privilege | mitigate | closed | MCP tool ids remain the six product tools (`src/mcp_strava/interfaces/mcp_http.py:30`); aggregate tool schema excludes raw/admin/sync/debug parameters (`tests/test_mcp_surface.py:193`); product service registry excludes admin/debug names (`tests/test_security_guards.py:208`). |
| 09-01/T-09-SC | Tampering | accept | closed | Accepted risk AR-09-SC. Phase plans contain no package-manager install task, package files are unchanged, and `rg` found no `pip/npm/cargo` install command in Phase 09 artifacts beyond the threat text itself. |
| 09-02/T-09-02-S | Spoofing | mitigate | closed | Product bundle ids resolve only through `AGGREGATE_METRIC_BUNDLES` (`metric_registry.py:38`, `metric_registry.py:1315`); request resolution calls `metrics_for_aggregate_bundle` before query work (`aggregate_queries.py:507`); unknown bundle rejection is tested (`tests/test_metric_registry.py:439`). |
| 09-02/T-09-02-T | Tampering | mitigate | closed | Aggregate rows emit registry metric ids and calculations (`aggregate_queries.py:1016`); product bundle completeness filters requested metrics to registered ids (`src/mcp_strava/application/product_facts.py:586`); tests assert returned metric ids are registered and accounted for (`tests/test_product_fact_bundles.py:77`, `tests/test_product_fact_bundles.py:112`). |
| 09-02/T-09-02-R | Repudiation | mitigate | closed | Status facts are registry-backed (`metric_registry.py:1157`) and daily bundle status sections include the registry status fact items (`product_facts.py:156`); tests require threshold/window/evidence/completeness/metric_id fields (`tests/test_product_fact_bundles.py:283`). |
| 09-02/T-09-02-I | Information Disclosure | mitigate | closed | Detail-only kudos and mirrored gear shaping are implemented in `metric_services.py:255` and `metric_services.py:479`; product bundle gear facts use detail service output only (`product_facts.py:460`); mirrored and missing-gear behavior is tested (`tests/test_product_fact_bundles.py:322`). |
| 09-02/T-09-02-D | Denial of Service | mitigate | closed | Product bundle service calls use fixed bundle ids and bounded local date windows (`product_facts.py:48`, `product_facts.py:180`, `product_facts.py:273`); aggregate validation rejects unsupported dates/windows/scopes before execution (`aggregate_queries.py:102`, `tests/test_training_aggregates.py:1121`). |
| 09-02/T-09-02-E | Elevation of Privilege | mitigate | closed | Bundle shaping is added to existing `get_training_aggregates_service` while preserving rows (`src/mcp_strava/application/aggregate_services.py:55`, `aggregate_services.py:96`); MCP exposes this through the existing `get_training_aggregates` tool only (`mcp_http.py:316`). |
| 09-02/T-09-SC | Tampering | accept | closed | Accepted risk AR-09-SC. No package-manager install task exists in plan 09-02 or its implementation evidence. |
| 09-03/T-09-03-S | Spoofing | mitigate | closed | Root `COMMANDS` contains product commands plus `admin`; mutating operations are in `ADMIN_COMMANDS` (`src/mcp_strava/cli.py:757`, `src/mcp_strava/cli.py:772`); tests assert no admin names at root (`tests/test_security_guards.py:107`). |
| 09-03/T-09-03-T | Tampering | mitigate | closed | Admin dispatch is namespaced (`cli.py:732`); storage cutover refuses live-looking targets without `--apply --confirm-live-cutover` (`cli.py:326`, `cli.py:345`); confirmation behavior is tested (`tests/test_cli_surface.py:377`). |
| 09-03/T-09-03-R | Repudiation | mitigate | closed | CLI product commands print full `ServiceEnvelope` JSON when requested (`cli.py:539`) and render freshness/completeness/status/rationale metadata in text mode (`cli.py:551`); JSON envelope fields are tested (`tests/test_cli_surface.py:254`). |
| 09-03/T-09-03-I | Information Disclosure | mitigate | closed | Product CLI handlers delegate to product/read-model services (`cli.py:149`); guard tests forbid raw SQL, token, sync, backfill, and recompute calls from product handlers (`tests/test_cli_surface.py:605`, `tests/test_security_guards.py:450`). |
| 09-03/T-09-03-D | Denial of Service | mitigate | closed | Product commands call prepared service functions only (`cli.py:149`, `cli.py:167`); product bundle services are guarded against request-time recompute/admin handlers (`tests/test_security_guards.py:377`, `tests/test_security_guards.py:410`); aggregate requests validate bounded scopes/windows (`aggregate_queries.py:102`). |
| 09-03/T-09-03-E | Elevation of Privilege | mitigate | closed | Product service registry lists only product services (`src/mcp_strava/application/registry.py:20`); MCP tool allowlist is product-only (`mcp_http.py:30`); tests prove admin commands are absent from product registry and MCP surface (`tests/test_security_guards.py:208`, `tests/test_security_guards.py:691`). |
| 09-03/T-09-SC | Tampering | accept | closed | Accepted risk AR-09-SC. No package-manager install task exists in plan 09-03 or its implementation evidence. |
| 09-04/T-09-04-S | Spoofing | mitigate | closed | Runtime and dev client both define the same six MCP tool ids (`mcp_http.py:30`, `src/mcp_strava/devtools/mcp_client/client.py:19`); exact allowlist tests enforce no new/renamed tools (`tests/test_mcp_surface.py:183`). |
| 09-04/T-09-04-T | Tampering | mitigate | closed | MCP smoke bundle calls use bounded product parameters only (`client.py:313`); tests assert bundle smoke calls use registered bundles, start/end dates, and no raw/window overrides in default smoke (`tests/test_mcp_test_client.py:170`); aggregate schema forbids SQL/table/query/raw/admin fields (`tests/test_mcp_surface.py:193`). |
| 09-04/T-09-04-R | Repudiation | mitigate | closed | Deployment docs list targeted MCP/client tests, CLI/security tests, `just phase9-bundle-smoke`, `just test`, and optional p95 gate (`docs/deployment.md:190`); `Justfile` defines the smoke recipe (`Justfile:23`). |
| 09-04/T-09-04-I | Information Disclosure | mitigate | closed | MCP payload guard rejects raw/admin/token/log/debug fields and advice phrases (`tests/test_mcp_surface.py:149`); product bundle guards block raw/admin/sync/token/legacy helpers (`tests/test_security_guards.py:377`, `tests/test_security_guards.py:668`). |
| 09-04/T-09-04-D | Denial of Service | mitigate | closed | Smoke requests use finite bundle/date ranges (`client.py:313`); expensive aggregate/compare tools use a bounded short-lived cache (`mcp_http.py:48`, `mcp_http.py:124`); cache and full request identity are tested (`tests/test_mcp_surface.py:420`, `tests/test_mcp_surface.py:524`). |
| 09-04/T-09-04-E | Elevation of Privilege | mitigate | closed | Deployment docs state sync/backfill/raw/sql/token/log/recompute stay below MCP/product (`docs/deployment.md:178`, `docs/deployment.md:273`); product registry and CLI/MCP guard tests exclude those controls (`tests/test_security_guards.py:208`, `tests/test_security_guards.py:450`). |
| 09-04/T-09-SC | Tampering | accept | closed | Accepted risk AR-09-SC. No package-manager install task exists in plan 09-04 or its implementation evidence. |

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---|---|---|---|---|
| AR-09-SC | 09-01/T-09-SC, 09-02/T-09-SC, 09-03/T-09-SC, 09-04/T-09-SC | The plan set accepts package-manager tampering risk because no npm/pip/cargo install task exists. Current evidence: no install command in Phase 09 plan/tasks, tracked package files are unchanged, and implementation work did not add dependencies. | Phase 09 plan threat model | 2026-05-26 |

## Threat Flags

No unregistered flags. All four `## Threat Flags` sections in `09-01-SUMMARY.md` through `09-04-SUMMARY.md` are `None`.

## Verification Commands

| Command | Result |
|---|---|
| `uv run pytest -q tests/test_metric_registry.py tests/test_training_aggregates.py tests/test_product_fact_bundles.py tests/test_cli_surface.py tests/test_mcp_surface.py tests/test_mcp_test_client.py tests/test_security_guards.py tests/test_mcp_latency_gate.py` | Passed: 126 tests in 11.17s. |
| `rg -n "pip install\|uv add\|poetry add\|npm install\|pnpm add\|yarn add\|cargo add\|cargo install" .planning/phases/09-product-factual-bundles-and-cli-read-model-consolidation Justfile pyproject.toml requirements.txt package.json package-lock.json Cargo.toml` | Matches are limited to the accepted-risk threat/report text; no install command appears in tasks, Justfile, or package files. |
| `git status --short --untracked-files=all` | Existing unrelated untracked `references/linkedin-post-notes.md`; no implementation/test file edits from this audit. |

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|---|---:|---:|---:|---|
| 2026-05-26 | 28 | 28 | 0 | codex |

## Sign-Off

- [x] All threats have a disposition: mitigate or accept.
- [x] Accepted risks documented in Accepted Risks Log.
- [x] `threats_open: 0` confirmed.
- [x] `status: verified` set in frontmatter.

Approval: verified 2026-05-26
