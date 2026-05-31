# Phase 999.1 — Metric Platform (declarative metric registry)

**Status:** BACKLOG (parking lot — not sequenced)
**Captured:** 2026-05-31, from the session that added the `calories` metric (commit `d114e2a`).

## One-liner
Make the metric registry a true single source of truth so **adding a metric is one
declaration, not ~7 coordinated edits across 3 files**.

## Problem
The registry (`src/mcp_strava/metric_registry.py`) centralizes metric **metadata**
(label, unit, aggregate mode, bundles, exposure) but NOT the **value plumbing** —
where the number comes from, how it is stored, extracted, selected, and exposed.
Adding even a trivial passthrough metric (`calories`, raw kcal already present in
`detail_json`) required edits in ~7–11 places. Most of the implementation effort
went to *tracing* the dense existing design, not the change itself (it mechanically
mirrors `distance_km`). The owner flagged this directly: the registry was meant to
be the single source of truth, so onboarding a metric should be declarative.

## The wiring map — what adding ONE metric touches today
(Worked example: `calories`, commit `d114e2a`.)

1. `adapters/duckdb/schema.py` — add column to `activity_metric_facts` CREATE TABLE (`calories_kcal DOUBLE`).
2. `adapters/duckdb/schema.py` — expose it in the `v_activity_aggregate_facts` VIEW (`f.calories_kcal`).
3. `adapters/duckdb/schema.py` `ensure_provenance_columns()` — additive `ALTER ... ADD COLUMN IF NOT EXISTS` migration for existing DBs.
4. `adapters/duckdb/read_model_materializer.py` — extract/compute the value into the fact dict (`_detail_calories()` parses `detail_json`).
5. `metric_registry.py` `METRIC_REGISTRY` — `_metric(...)` entry (base metadata).
6. `metric_registry.py` `_CALCULATION_BY_METRIC_ID` — calculation description text (the `_metric` builder RAISES if missing).
7. `metric_registry.py` `_AGGREGATE_METADATA_BY_METRIC_ID` — `_agg(...)` entry (mode, source, value_column, supported_buckets/scopes).
8. `metric_registry.py` `_fact_table("activity_metric_facts", ...)` — fact-column definition tuple `("calories_kcal","metric",("calories",),"...")`.
9. `metric_registry.py` `AGGREGATE_METRIC_BUNDLES` — add to each bundle it appears in (weekly_digest/monthly_digest/period_comparison).
10. *(sometimes)* `aggregate_queries.py` `_METRIC_VALUE_EXPRESSIONS` — SQL value expression IF unit conversion is needed (`distance_m / 1000.0`); NOT needed when `value_column` is already in the target unit (calories, trimp).
11. *(for per-workout exposure)* `application/metric_services.py` `ACTIVITY_SCALAR_FACTS` + the hand-built `_activity_payload` dict + the tool's metric list. (calories avoided these by being aggregate/digest-only.)

## Key smells
- **Parallel DDL:** `_fact_table(...)` in `metric_registry.py` is a second registry of fact
  columns that DUPLICATES the hand-written `CREATE TABLE` DDL in `schema.py`. They must be
  kept in sync by hand (a consistency test catches drift). The fact-column registry SHOULD
  GENERATE the DDL.
- **Hand-built payloads:** per-tool payloads (`_activity_payload`, list_workouts /
  get_workout_detail) are hand-written dicts (`"distance_km": _activity_value(row, "distance_km")`)
  rather than a loop over the registry filtered by `exposed_in`. The test
  `test_tool_metric_payloads_match_registry_exposure` asserts payload keys == registry
  exposure, so they must be manually kept consistent.
- **Dual exposure control:** `exposed_in` (per-tool payloads) vs `AGGREGATE_METRIC_BUNDLES`
  (digests / aggregates / compare) are two overlapping mechanisms; plus code at
  `metric_registry.py:~1497` auto-adds `"compare_periods"` to `exposed_in` for metrics in
  the `period_comparison` bundle. Confusing.
- **No version-driven re-materialization:** bumping `CURRENT_METRIC_VERSION` does NOT
  re-enqueue stale-version facts, so a new metric column needs a separate backfill. There is
  no `rematerialize-all` admin command — the calories backfill was a stopped-owner one-off
  `UPDATE activity_metric_facts SET calories_kcal = TRY_CAST(json_extract_string(detail_json,'$.calories') AS DOUBLE)`.

## Proposed declarative design (north star)
Each metric declares its value **source** in the registry, e.g.:
- `source="detail_json.calories"` — parse from raw detail JSON
- `source="summary.distance" scale=0.001` — summary column with unit scale
- `source="computed:calc_cardiac_drift"` — pure function in `metrics.py`

A generic engine then DERIVES:
- (a) the fact-table DDL column (from the fact-column registry — eliminating the parallel `schema.py` duplication),
- (b) the materializer extraction (dispatched by source kind),
- (c) the aggregate value selection (value_column / expression),
- (d) the per-tool payload (loop the registry by `exposed_in` instead of hand-built dicts).

Result: **new metric = one declaration**; the ~7 edits collapse to 1.

## Suggested approach
Real refactor, not a quick change — start with a **design/spike phase**:
1. Source-declaration grammar (json-path / summary-column+scale / computed-fn).
2. Whether to GENERATE the DDL from the fact-column registry (and migration strategy for the existing parallel `_fact_table`).
3. Unify `exposed_in` vs `AGGREGATE_METRIC_BUNDLES` into one exposure model.
4. Add a `rematerialize-all` / backfill admin command (folds in the version-bump gap).

**Reference example:** the `calories` metric (commit `d114e2a`) shows every touch-point
concretely — diff it to see the full surface a declarative engine must cover.
