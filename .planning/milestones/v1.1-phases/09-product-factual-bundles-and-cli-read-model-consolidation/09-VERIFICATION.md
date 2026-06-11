---
phase: 09-product-factual-bundles-and-cli-read-model-consolidation
verified: 2026-05-26T15:28:09Z
status: passed
score: "10/10 must-haves verified"
overrides_applied: 0
---

# Phase 9: Product factual bundles and CLI read-model consolidation Verification Report

**Phase Goal:** MCP and CLI product reads expose factual daily, weekly, historical, status, kudos, and supported gear facts from the DuckDB/read-model application layer without adding MCP tools or reviving legacy CLI/recompute paths.
**Verified:** 2026-05-26T15:28:09Z
**Status:** passed
**Re-verification:** No - initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | MCP remains exactly the six product tools; product verification does not rely on gateway smoke. | VERIFIED | `MCP_TOOL_NAMES` is exactly `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, `project_fitness_state`, `get_training_aggregates` in `src/mcp_strava/interfaces/mcp_http.py:30`; `tests/test_mcp_surface.py:183` asserts exact allowlist; `docs/deployment.md:192` and `docs/deployment.md:206` explicitly require direct server smoke, not gateway smoke. Live `just phase9-bundle-smoke` returned these six tools and no gateway path. |
| 2 | Product bundles expose daily, weekly, historical, status, kudos, and supported gear facts from shared application/read-model services. | VERIFIED | `src/mcp_strava/application/product_facts.py:48`, `:180`, and `:273` define daily, weekly, and historical bundle services; `src/mcp_strava/application/aggregate_services.py:55` returns aggregate rows and adds `data.bundle` only through `_product_bundle_payload` at `:101`; `src/mcp_strava/application/metric_services.py:255` builds mirrored gear facts, while kudos are present in list/detail/aggregate contexts. |
| 3 | Product bundles are factual, machine-readable, and not advice/recommendation surfaces. | VERIFIED | `product_facts.py:1` states no coaching advice crosses the boundary; status facts are typed in `src/mcp_strava/types.py:928` and `:940`; `STATUS_FACT_REGISTRY` at `src/mcp_strava/application/metric_registry.py:1157` stores codes, thresholds, windows, evidence keys, completeness reasons, calculations, and materialized sources. Tests reject advice phrases and forbidden fields in `tests/test_product_fact_bundles.py:31` and `tests/test_mcp_surface.py:44`. |
| 4 | Bundle completeness is explicit; metrics are accounted for as included, unavailable, skipped, or scope-incompatible with reason codes. | VERIFIED | `product_facts.py:586` builds `bundle_completeness` with requested/included/unavailable/skipped/scope-incompatible arrays; unaccounted metrics get `data_absent` at `:603`; gear absence emits `gear_data_not_mirrored` at `:484`. MCP payload tests validate reason codes in `tests/test_mcp_surface.py:158` and bundle sections at `:169`. |
| 5 | Historical and status facts are derived from DuckDB/read-model facts, not absent training-model columns or raw stream recompute. | VERIFIED | `v_historical_context_facts` derives activity streak, rest streak, and last-hike facts from `daily_load_facts` and `activity_metric_facts` in `src/mcp_strava/adapters/duckdb/schema.py:415`; registry maps these facts to that view in `metric_registry.py:1081`. Tests assert the query uses the view and not `training_model_daily.activity_streak_days` at `tests/test_training_aggregates.py:821`. |
| 6 | CLI product reads are thin consumers of product/read-model services, with admin operations kept below product and MCP surfaces. | VERIFIED | `src/mcp_strava/cli.py:149` calls `get_daily_brief_facts_service`, `:158` calls `get_weekly_digest_facts_service`, `:167` calls `list_workouts_service`, `:177` calls `get_workout_detail_service`, and `:186` calls freshness service. Root `COMMANDS` only has product commands plus `admin` at `:772`; admin commands are namespaced at `:757`. `uv run python -m mcp_strava` printed only `report, weekly, workouts, workout, freshness, admin`. |
| 7 | Legacy report/workout modules and retired legacy CLI handlers are not retained as compatibility aliases. | VERIFIED | `mcp_strava.application.reports` and `.workouts` import specs are `None`; `tests/test_application_reports.py:9` and `tests/test_application_workouts.py:9` assert retirement; `tests/test_security_guards.py:113` forbids dead handlers/imports. `docs/cli.md:7` documents replacements instead of old aliases. |
| 8 | Review fixes are present: per-sport rolling facts use stored sport rows, and warm latency bundle calls remain distinct entries. | VERIFIED | `aggregate_queries.py:928` filters rolling facts to `scope = 'sport'` and `:902` returns stored `sport_type` for per-sport output; regression test `tests/test_training_aggregates.py:937` proves Run and Hike rows remain distinct. `client.py:643` builds latency result keys with `get_training_aggregates:{metric_bundle}` and `tests/test_mcp_latency_gate.py:96` asserts distinct daily/weekly/historical entries. |
| 9 | MCP product reads use materialized/read-model facts and preserve freshness/completeness metadata, without request-time stream-heavy recompute. | VERIFIED | MCP envelope payload always includes `data`, `freshness`, `completeness`, `warnings`, and `rationale` in `mcp_http.py:63`; `aggregate_services.py:68` reads repository freshness/read-model status before `query_training_aggregates`; security guards at `tests/test_security_guards.py:377` and `:410` block Strava, sync, token refresh, legacy report/workout, and recompute calls from product bundle services. |
| 10 | Current test/smoke/performance evidence is green against code and Docker runtime. | VERIFIED | `uv run pytest -q` passed with 353 passed, 1 skipped. `just phase9-bundle-smoke` passed targeted MCP tests and live smoke called `get_training_aggregates:daily_brief`, `:weekly_digest`, and `:historical_facts`. `just test` passed Docker build/recreate/smoke-basic. `just mcp-read-model-perf 20 2 500` passed with every product call under 500 ms warm p95. |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/mcp_strava/types.py` | Status fact output contracts | VERIFIED | `StatusFactDefinition` and `StatusFact` exist at lines 928 and 940. |
| `src/mcp_strava/application/metric_registry.py` | Bundle/status/gear/read-model registry metadata | VERIFIED | Historical fact aggregate metadata at lines 732-758; fact-column registry at 1081-1100; status registry at 1157-1248. |
| `src/mcp_strava/adapters/duckdb/schema.py` | DuckDB read-model views for historical context | VERIFIED | `v_historical_context_facts` derives streak and last-hike facts at lines 415-487. |
| `src/mcp_strava/adapters/duckdb/aggregate_queries.py` | Bundle/status query execution over registry metadata | VERIFIED | Validates registry-backed requests, splits scoped requests, queries status facts, and filters rolling per-sport rows. |
| `src/mcp_strava/application/product_facts.py` | Shared product fact bundle services | VERIFIED | Daily, weekly, historical services and completeness helpers are substantive and wired. |
| `src/mcp_strava/application/aggregate_services.py` | Existing aggregate service adds optional product bundle payload while preserving rows | VERIFIED | Rows remain in `data["rows"]`; `data["bundle"]` added only when formatter returns a product bundle. |
| `src/mcp_strava/cli.py` | Thin product/admin CLI dispatcher | VERIFIED | Product commands call product/metric/freshness services; admin operations remain under `ADMIN_COMMANDS`. |
| `src/mcp_strava/application/reports.py` | Retired legacy report path | VERIFIED | Intentionally absent; import spec is `None`; tests assert retirement and replacement by `product_facts`. |
| `src/mcp_strava/application/workouts.py` | Retired legacy workout path | VERIFIED | Intentionally absent; import spec is `None`; tests assert replacement by `metric_services`. |
| `src/mcp_strava/devtools/mcp_client/client.py` | Direct MCP bundle smoke and warm latency call identity | VERIFIED | Live smoke loops over product bundle aggregate calls at lines 480-487; latency keys include bundle id at 643-648. |
| `tests/test_*` Phase 9 files | Registry, bundle, CLI, MCP, security, and latency coverage | VERIFIED | Full suite passed; targeted Phase 9 smoke passed. |
| `docs/cli.md`, `docs/deployment.md`, `docs/metrics.md`, `Justfile` | Replacement docs and direct verification commands | VERIFIED | CLI replacement mapping in `docs/cli.md`; Phase 9 direct verification sequence in `docs/deployment.md`; `Justfile:23` defines `phase9-bundle-smoke`. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `metric_registry.py` | `aggregate_queries.py` | `metrics_for_aggregate_bundle`, `STATUS_FACT_REGISTRY`, aggregate metadata | VERIFIED | SDK key-link check passed; source imports registry metadata at `aggregate_queries.py:12`. |
| `metric_registry.py` | `schema.py` | `MATERIALIZED_FACT_COLUMN_REGISTRY` and `v_historical_context_facts` | VERIFIED | Registry points historical metrics at the view; schema creates the view. |
| `product_facts.py` | `aggregate_services.py` and `metric_services.py` | Service composition | VERIFIED | Product facts call aggregate, fitness, workout list/detail, comparison, and status read-model services. |
| `aggregate_services.py` | `product_facts.py` | Bundle formatter | VERIFIED | `_product_bundle_payload` imports `format_aggregate_product_bundle` only for bundle shaping. |
| `cli.py` | `product_facts.py` and `metric_services.py` | Thin command handlers | VERIFIED | Command handlers call the shared services directly. |
| `devtools/mcp_client/client.py` | `interfaces/mcp_http.py` | Direct `get_training_aggregates` bundle calls | VERIFIED | `just phase9-bundle-smoke` exercised direct server calls against `/mcp`; no gateway command used. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `product_facts.py` daily brief | `data.sections`, `rows`, `bundle_completeness` | `get_training_aggregates_service`, `get_fitness_state_service`, `list_workouts_service`, `query_status_facts` | Yes - live smoke returned bundle rows/sections and workout data shapes. | FLOWING |
| `product_facts.py` weekly digest | `data.sections.load/volume/efficiency/by_sport/period_trends` | Aggregate service plus `compare_periods_service` | Yes - targeted tests and live smoke returned weekly digest bundle payload. | FLOWING |
| `product_facts.py` historical facts | `activity_context`, `calendar_context`, `coverage` | `v_historical_context_facts` through aggregate service | Yes - fixture tests assert non-unavailable values for historical metrics. | FLOWING |
| `aggregate_services.py` `data.rows` and `data.bundle` | `row_payloads`, `read_model` | DuckDB aggregate query plus repository read-model status | Yes - full suite and Docker smoke returned aggregate rows and read-model metadata. | FLOWING |
| `cli.py` product commands | Service envelopes | Product fact, metric, and freshness services | Yes - CLI registry and spy tests prove service delegation; usage exposes only current product/admin surface. | FLOWING |
| `mcp_http.py` tool responses | Structured MCP payload | Application service envelopes via six tool handlers | Yes - direct Docker smoke returned structured data for all product tools/bundles. | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full Python test suite | `uv run pytest -q` | `353 passed, 1 skipped in 21.68s` | PASS |
| Direct MCP bundle smoke | `just phase9-bundle-smoke` | Targeted tests `19 passed`; live smoke `status:"ok"` and called all three product bundles through `get_training_aggregates` | PASS |
| Docker smoke/basic MCP surface | `just test` | Docker build/recreate healthy; smoke-basic `status:"ok"` and six product tools | PASS |
| Warm p95 performance target | `just mcp-read-model-perf 20 2 500` | `status:"ok"`; worst reported p95 was `115.171 ms`, below 500 ms; daily/weekly/historical aggregate bundle entries were distinct | PASS |
| CLI root surface | `uv run python -m mcp_strava` | Usage listed only `report, weekly, workouts, workout, freshness, admin` | PASS |
| Legacy module retirement | `importlib.util.find_spec(...)` | `mcp_strava.application.reports=None`; `mcp_strava.application.workouts=None` | PASS |

### Probe Execution

| Probe | Command | Result | Status |
|---|---|---|---|
| Conventional probes | `find scripts -path '*/tests/probe-*.sh' -type f` | No probe scripts found; phase verification uses pytest, direct MCP smoke, Docker smoke, and p95 gates. | SKIPPED |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| APP-01 | 09-01, 09-02, 09-03 | Daily training report from local mirror with freshness/completeness/warnings/rationale | SATISFIED | `get_daily_brief_facts_service`; CLI `report daily`; MCP aggregate daily bundle smoke. |
| APP-02 | 09-01, 09-02, 09-03 | Weekly load summary with sport-aware aggregation and trend context | SATISFIED | Weekly digest service uses aggregate rows and compare-period trend context; per-sport rolling regression passes. |
| APP-03 | 09-02, 09-03 | Recent workouts and per-workout analytics without request-time Strava calls | SATISFIED | CLI and MCP call `list_workouts_service`/`get_workout_detail_service`; security guards block Strava imports/calls in product reads. |
| APP-04 | 09-02, 09-03 | Freshness metadata without exposing sync as user-facing operation | SATISFIED | Freshness service remains product command; sync/admin controls are under `admin` and excluded from MCP/product registries. |
| CLI-01 | 09-03 | Local CLI provides retained product and admin/debug workflows | SATISFIED | Root commands are product plus `admin`; admin commands preserve local operator workflows. |
| CLI-02 | 09-03 | CLI commands use application services/adapters instead of owning business logic | SATISFIED | Product command handlers delegate directly to services; spy/AST tests enforce routing. |
| CLI-03 | 09-03 | Retained capabilities have documented replacements | SATISFIED | `docs/cli.md:7` maps removed commands to current product/admin paths. |
| MCP-01 | 09-01, 09-02, 09-04 | MCP exposes only read-only intent-level training tools | SATISFIED | Exact six-tool allowlist and read-only annotations; no product bundle tool added. |
| MCP-02 | 09-03, 09-04 | MCP excludes sync/backfill/raw/API/SQL/token/admin/log tools | SATISFIED | Tests and live smoke show six product tools only; forbidden schema/field guards pass. |
| MCP-03 | 09-01, 09-02, 09-04 | MCP responses include freshness/completeness metadata | SATISFIED | `_envelope_payload` emits metadata for every tool; bundle tests assert read-model metadata. |
| READMODEL-01 | 09-01 | Activity-level derived metrics persisted with source provenance/version metadata | SATISFIED | Registry and aggregate rows preserve metric-version/materialized metadata; full read-model tests passed. |
| READMODEL-04 | 09-01, 09-02 | MCP tools read materialized facts and avoid raw stream recompute during request handling | SATISFIED | Aggregate services query DuckDB read-model views; security guards block raw stream/recompute paths. |
| PERF-01 | 09-04 | Product MCP tools under 500 ms warm p95 with startup separate | SATISFIED | `just mcp-read-model-perf 20 2 500` passed; startup reported separately as `44.209 ms`. |
| TEST-03 | 09-01, 09-03, 09-04 | Tests cover MCP allowlist and forbidden tools absent | SATISFIED | `tests/test_mcp_surface.py` and `tests/test_security_guards.py`; full suite passed. |
| TEST-04 | 09-02, 09-03, 09-04 | Tests cover freshness, missing-HR handling, daily/weekly parity | SATISFIED | Product bundle, metric service, CLI, and security tests passed in full suite. |
| TEST-06 | 09-01, 09-02, 09-04 | Tests/live Docker smoke cover read-model materialization, query shape, MCP guards, warm p95 | SATISFIED | Full pytest, direct bundle smoke, Docker `just test`, and warm p95 gate all passed. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| None | - | No unreferenced `TBD`, `FIXME`, or `XXX` markers in Phase 9 modified files | - | No blocker debt markers found. |
| `src/mcp_strava/types.py` | 104 | `not available` in comment | INFO | Domain note for Run-only metric availability, not a stub. |
| `tests/*` | various | `placeholder` / empty fixture collections | INFO | Test fixture text and helper defaults only; no runtime placeholder data source. |
| `src/mcp_strava/application/product_facts.py` | 401, 408, 411 | `return []` helper fallbacks | INFO | Defensive parsing fallbacks; data sources are populated by aggregate/metric services and live smoke. |

### Human Verification Required

None.

### Gaps Summary

No gaps found. The phase goal is achieved: MCP and CLI product reads expose factual read-model-backed bundles and facts, the MCP surface remains exactly six product tools, legacy CLI/recompute paths are retired, review fixes are present, and current automated/Docker/performance gates pass.

---

_Verified: 2026-05-26T15:28:09Z_
_Verifier: the agent (gsd-verifier)_
