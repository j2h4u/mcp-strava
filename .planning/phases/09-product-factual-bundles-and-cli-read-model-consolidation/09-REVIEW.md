---
phase: 09-product-factual-bundles-and-cli-read-model-consolidation
reviewed: 2026-05-26T15:09:49Z
depth: standard
files_reviewed: 26
files_reviewed_list:
  - Justfile
  - docs/cli.md
  - docs/deployment.md
  - docs/metrics.md
  - src/mcp_strava/adapters/duckdb/aggregate_queries.py
  - src/mcp_strava/adapters/duckdb/repository.py
  - src/mcp_strava/adapters/duckdb/schema.py
  - src/mcp_strava/adapters/sqlite/repository.py
  - src/mcp_strava/application/aggregate_services.py
  - src/mcp_strava/application/metric_registry.py
  - src/mcp_strava/application/metric_services.py
  - src/mcp_strava/application/product_facts.py
  - src/mcp_strava/application/registry.py
  - src/mcp_strava/cli.py
  - src/mcp_strava/devtools/mcp_client/client.py
  - src/mcp_strava/types.py
  - tests/test_application_reports.py
  - tests/test_application_workouts.py
  - tests/test_cli_surface.py
  - tests/test_mcp_surface.py
  - tests/test_mcp_test_client.py
  - tests/test_metric_registry.py
  - tests/test_product_fact_bundles.py
  - tests/test_security_guards.py
  - tests/test_smoke.py
  - tests/test_training_aggregates.py
findings:
  critical: 1
  warning: 1
  info: 0
  total: 2
status: issues_found
---

# Phase 09: Code Review Report

**Reviewed:** 2026-05-26T15:09:49Z
**Depth:** standard
**Files Reviewed:** 26
**Status:** issues_found

## Summary

Reviewed the Phase 09 product factual bundles, aggregate read model, CLI surface, MCP test client, docs, and tests. `uv run pytest -q` passes with 351 passed and 1 skipped, but the suite does not cover a sport-filtered rolling aggregate regression that can return all-sport facts as sport-specific output.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Per-sport rolling aggregates relabel all-sport facts

**Classification:** BLOCKER
**File:** `src/mcp_strava/adapters/duckdb/aggregate_queries.py:930`
**Issue:** Rolling metrics such as `rolling_median_cc` are registered as per-sport metrics in `src/mcp_strava/application/metric_registry.py:672`, but the DuckDB aggregate query always constrains `rolling_period_fact` to `scope = 'all'` at lines 930-931. When a caller passes `scope="per_sport"` and a `sport_filter`, `_sport_output_expression()` returns the requested sport literal at lines 902-905 while the `WHERE` clause never filters rolling facts by that sport. A reproduced query for `rolling_median_cc` with `sport_filter="Run"` and then `sport_filter="Hike"` returned the same all-sport value, sample size, and activity count, only changing the output `sport_type` label. This makes product factual bundles and CLI/MCP aggregate consumers report fabricated sport-specific training facts.

**Fix:**
```python
if source == "rolling_period_fact":
    if request.scope == "per_sport":
        where.append("scope = 'sport'")
        if request.sport_filter is not None:
            where.append("sport_type = ?")
            params.append(request.sport_filter)
    else:
        where.extend(["scope = 'all'", "sport_type = 'all'"])
```

If per-sport rolling rows are not yet materialized, reject per-sport rolling metric requests or remove these metrics from `supported_scopes=("per_sport",)` until the facts exist. Also change `_sport_output_expression()` so it returns stored `sport_type` for per-sport rows instead of synthesizing the caller's filter, and add a regression test that proves `Run` and `Hike` rolling queries do not return the same relabeled all-sport row.

## Warnings

### WR-01: Warm latency results collapse product bundle aggregate calls

**Classification:** WARNING
**File:** `src/mcp_strava/devtools/mcp_client/client.py:424`
**Issue:** `default_warm_latency_calls()` now includes three `get_training_aggregates` calls for `daily_brief`, `weekly_digest`, and `historical_facts` at lines 313-346, but `measure_warm_tool_latency()` stores results in `tool_results[name]`. Because all three calls have the same tool name, each result overwrites the prior one and the returned warm-latency report only exposes the last aggregate bundle. Failures can still flip the top-level status, but the diagnostic payload cannot show which product bundle passed or failed, which weakens Phase 09's product-bundle verification surface.

**Fix:** Key each latency result by a stable call identifier, such as `get_training_aggregates:daily_brief`, or return a list of result rows containing the tool name, arguments, and measured timings. Add a regression test that runs `measure_warm_tool_latency()` with `default_warm_latency_calls()` and asserts all three aggregate bundle entries are preserved separately.

---

_Reviewed: 2026-05-26T15:09:49Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
