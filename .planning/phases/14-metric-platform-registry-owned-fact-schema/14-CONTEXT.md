# Phase 14 - Metric Platform registry-owned fact schema

**Status:** Promoted from backlog; ready to plan.
**Captured:** 2026-05-31, from the session that added the `calories` metric (commit `d114e2a`).
**Backlog source:** Phase 999.1 - Metric Platform declarative metric registry.
**Active scope:** slice 1 only: registry-owned SQL types, generated fact DDL, and additive migration generation.

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

## Decision (2026-05-31): incremental path (Option B), not big-bang (Option A)

Reviewed via expert panel. Code was verified against the claims above — the ~11-touchpoint
map is accurate. Decided to do this as **sequenced slices, not one big refactor**.

### Two kinds of metric (this is the crux)
The proposed declarative engine is easy for some metrics and hard for others. They split cleanly:

- **Simple / copy metrics** (`distance`, `calories`, `moving_time`, `elapsed_time`,
  `elevation_gain`): the value already arrives from Strava ready-made. We just copy it into
  our fact row, sometimes with a unit scale (`m → km`). A declaration like
  `source="detail_json.calories"` or `source="summary.distance" scale=0.001` describes these
  perfectly — the origin is a *single field*.
- **Computed metrics** (`trimp`, the five `zoneN_seconds`, `cardiac_*`, `hr_recovery_*`,
  `vertical_speed`): Strava does NOT provide these. The materializer computes them from raw
  HR/stream data, and the computations **share intermediate state** — e.g. the zone-seconds
  feed BOTH `trimp` AND `time_in_hr_zones`, and HR samples feed many metrics
  (`read_model_materializer.py:175-220`). For these there is no "one field" source string;
  the real source is "a chunk of computation that also produced several other metrics."

A declarative `source=...` engine shines for the simple metrics and gets awkward for the
computed ones — covering them needs a computation-context/DAG layer, or `computed:fn` escape
hatches that break the "one declaration per metric" promise for exactly the hard cases.

### Why B over A
A and B reach the **same end state**. B's early slices are literally the prefix A would build
anyway. The only real difference: A commits to the hard computed-metric engine **up front and
non-optionally**; B builds the cheap certain wins first and puts a **decision gate** before the
computed-metric engine — so we decide whether it's worth building with evidence, not a guess.

A is not *dangerous* here (single dev instance, no prod, rebuildable DB — migration/blast-radius
risk is low). A's problem is that it front-loads the most speculative, ambiguous work and delivers
no value until the whole thing is done. The metric that triggered this (`calories`) is a *simple*
metric — building a full computed-metric engine to onboard copy-from-Strava fields would be
solving a problem we have not confirmed we have.

### Key verified finding that makes slice 1 cheap
`MATERIALIZED_FACT_COLUMN_REGISTRY` (`metric_registry.py:1588`) already declares every fact
column (table, column, role, metric_ids, description). The hand-written `CREATE TABLE` in
`schema.py` exists in parallel ONLY because the registry does not carry the SQL type. Add a
`sql_type` field to `FactColumnDefinition` and the DDL + `ALTER` migrations can be generated
FROM the registry — killing the parallel-DDL duplication outright. The drift test
(`test_metric_registry.py:272`, names-only set-equality) then becomes redundant: the registry
*is* the schema.

### Sequencing (each slice independently valuable, keeps tests green as a ratchet)
1. Add `sql_type` → generate the `activity_metric_facts` DDL + additive migrations from the
   fact-column registry. Retires the parallel-DDL smell and its drift test.
2. Registry-driven per-tool payloads — loop `exposed_in` instead of hand-built dicts in
   `metric_services.py`; delete the manual `test_tool_metric_payloads_match_registry_exposure`
   maintenance burden.
3. Simple-metric source grammar (`summary.<field> scale=`, `detail_json.<field>`) — covers the
   actual `calories`-style pain. After this, a copy-from-Strava metric = one declaration.
4. **Decision gate:** only now decide whether to build the computed-metric engine (shared-state
   context layer) or leave computed metrics explicit. Defer until a computed metric actually
   forces it.
- Fold in along the way: unify the dual exposure model (`exposed_in` vs
  `AGGREGATE_METRIC_BUNDLES` + the auto-add at `metric_registry.py:1529`), and add a
  `rematerialize-all` / backfill admin command (closes the "version bump doesn't re-enqueue
  stale facts" gap).

### Open question (deferred by design, not a blocker)
Are more *computed* metrics coming, or is the near-term backlog mostly copy-from-Strava fields?
The answer decides whether slice 4 is ever worth doing. B does not need it answered now — that
is the whole point of the gate.
