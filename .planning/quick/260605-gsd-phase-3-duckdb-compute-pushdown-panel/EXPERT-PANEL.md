# Phase 3 DuckDB Compute Pushdown Expert Panel

Date: 2026-06-05
Context: post-v1.1 performance sweep; milestone v1.1 complete but not yet archived.
Scope: design only. No runtime code or DuckDB mirror changes were made.

## Scope

Design the next performance slice for `read_model_materializer._activity_fact`.

The bottleneck is statement count, not product-read latency. `materialize_read_model`
still calls `_activity_fact` once per dirty activity, and the normal HR-present
path issues roughly a dozen repository reads per activity before the already-batched
fact upsert.

Blast radius is data-integrity critical for the local read model: activity facts feed
daily, model, rolling, aggregate, CLI, and MCP product reads. The design must preserve
byte-identical fact output and must not delete, overwrite, or resync the DuckDB mirror.

## Panel

Panel composition:

- DuckDB/SQL performance
- Software architecture and domain boundary
- Python data engineering
- Correctness/parity QA

## Converged Recommendation

Use a staged batch-fetch refactor, not a full SQL rewrite of the metric algorithms.

DuckDB should own set-oriented reads, joins, grouping, and running-window scans. Python
should remain the canonical owner of the complex metric semantics until a separate,
measured parity effort proves a SQL port is worth the contract change.

This resolves the Phase 10 tension as:

> Phase 3 DuckDB pushdown preserves Phase 10 domain purity. DuckDB owns bulk reads,
> grouping, joins, running windows, and simple relational projections; pure metric
> functions remain the DB-free semantic oracle. Any future SQL port of HR recovery or
> cardiac drift requires an explicit decision, byte-parity against the pure
> implementation, fingerprint coverage, and measured speedup.

## Recommended Data Flow

Keep `dirty_activity_rows_for_materialization()` as the claim source. It already
extends limited batches to whole-day boundaries, which protects daily/rolling rollups.

Inside the existing materializer transaction, process claimed dirty rows in chunks:

- Start with `MATERIALIZATION_ACTIVITY_BATCH_ROWS` around 100-250.
- Build a chunk ID set in dirty-row order.
- Fetch activity/source rows for the chunk in one `VALUES`/join query.
- Fetch stream scalar aggregates in one grouped stream scan.
- Fetch running max HR by relevant activity day in one day-level window query.
- Compute zone bounds in Python with the existing zone model.
- Fetch zone seconds and TRIMP with a bounds-driven grouped SQL query.
- Fetch stream rowsets in bounded ordered batches and partition by `activity_id`.
- Call the existing pure metric functions per activity.
- Build fact dicts in dirty-row order with the same shape as `_activity_fact`.
- Use the existing batched `upsert_activity_metric_facts()`.
- Do not commit per chunk; daily/model/rolling facts still run after all claimed
  activity facts are written inside the same transaction.

Lease renewal should remain at least per activity and per chunk. A visible
cross-connection lease heartbeat during a long single SQL statement is a separate
runtime design, not part of this refactor.

## Repository API Shape

Suggested new repository methods:

```python
def activity_materialization_sources(ids) -> dict[int, ActivityMaterializationSource]
def activity_stream_scalars_for_materialization(ids, min_velocity) -> dict[int, ActivityStreamScalars]
def running_max_heartrate_to_dates(days) -> dict[str, int | None]
def activity_zone_trimp_for_bounds(bounds_by_activity_id) -> dict[int, ActivityZoneTrimp]
def iter_activity_materialization_stream_rows(ids, *, fetch_size=50_000) -> Iterator[ActivityStreamRow]
```

Use dataclasses for repository boundary shapes, then index them by `activity_id` or
`day` in the materializer.

## What To Push Into DuckDB Now

- Base activity plus `activity_source_state` lookup.
- `stream_counts_for_activity`.
- `activity_hr_range`.
- `activity_median_heartrate`.
- `activity_cc` with the current filter: `heartrate IS NOT NULL AND velocity > VEL_MOVING`.
- `max_heartrate_to_date`, implemented as a day-level running max.
- Zone seconds and TRIMP from Python-supplied bounds.
- Optionally vertical speed as raw `total_ascent` plus `elapsed_sec`, with current
  Python rounding preserved.

## What To Keep Python-Canonical For This Slice

- `calc_hr_recovery`: stateful pause segmentation, duplicate time-offset collapse,
  gap tolerance, sampled-rest duration, and rate/median behavior are already pinned
  in pure tests.
- `calc_cardiac_drift`: Jenks clustering, outlier replacement, subsampling, temporal
  segment extraction, sport thresholds, and quality gates are too branchy for this
  first pushdown.
- `_detail_calories()` and `_start_time_local()` should stay in Python for byte
  identity.
- `%HRR` may be SQL-owned only if it keeps the current WR-03 behavior: median HR
  divided by per-activity observed max when present, not the running max.

## Running Max HR Rule

Do not implement running max with activity-row order. Current semantics are
day-inclusive: every activity on a given `activity_day` sees all HR samples from all
activities with `activity_day <= target_day`.

Correct shape:

```sql
day_hr AS (
  SELECT a.activity_day AS day, MAX(s.heartrate) AS day_hr_max
  FROM activities a
  JOIN streams s ON s.activity_id = a.id
  WHERE s.heartrate IS NOT NULL
    AND a.activity_day <= CAST(? AS DATE)
  GROUP BY a.activity_day
),
running_hr AS (
  SELECT day,
         MAX(day_hr_max) OVER (
           ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
         ) AS hr_max_observed
  FROM relevant_days LEFT JOIN day_hr USING (day)
)
```

The implementation can vary, but the observable result must equal
`repo.max_heartrate_to_date(day)` for every dirty day.

## Validation Plan

Use two parity layers before changing behavior broadly.

1. Method-level parity:

- Keep the current sequential `_activity_fact` or equivalent reference path while
  developing.
- Add `_activity_facts_batched(...)` tests that compare exact fact dicts against
  `[_activity_fact(repo, row, ...)]`.
- Add method-level repository tests for each new batch method against the existing
  per-activity methods.

2. Full materialization parity:

- Seed two identical DBs.
- Run the reference path on one and the batched path on the other with fixed `now`
  and `metric_version`.
- Dump all four fact tables with deterministic ordering:
  `activity_metric_facts`, `daily_load_facts`, `training_model_daily`,
  `rolling_period_facts`.
- Assert exact equality. No float tolerances.

3. Statement-count gate:

- Add a test-only counting repository or monkeypatch `_execute`, `_fetchone`, and
  `_fetchall`.
- Run an N-activity fixture through the reference and batched paths.
- Assert hot-path activity-fact reads collapse from O(N) scalar reads to O(chunks)
  grouped/bulk reads.
- Do not assert wall-clock time in unit tests.

## Edge Cases To Pin

- HR zone samples exactly at zone boundaries.
- No HR before a target day.
- Future high HR does not leak backward.
- Same-day high HR affects all same-day activities.
- Missing streams -> `unknown`.
- Missing details or missing HR -> `partial` where current behavior says so.
- Sorted `missing_reasons_json`.
- Zero zones/TRIMP when `hr_count == 0`.
- HR recovery includes HR rows even when velocity is null or stopped.
- Cardiac drift keeps `heartrate IS NOT NULL AND velocity > VEL_MOVING`.
- Altitude rows exclude null altitude.
- Vertical speed uses first/last returned `time_offset` span.
- `start_time_local` uses `parse_local_hhmm`, not slicing.
- `%HRR` uses per-activity observed max first, then running max only as fallback.
- Whole-day batching under `limit` remains intact.

## Stop Criteria

Stop and do not continue implementation if any of these happen:

- No retained sequential reference path exists for parity.
- Any full four-table dump differs byte-for-byte.
- Running max HR has duplicate-day order sensitivity.
- `%HRR` switches back to running max.
- Stream metric SQL ports lack direct parity against pure functions.
- Statement counts still scale with per-activity scalar reads.
- The Phase 10 contract revision is not explicit.

## Go Criteria

Proceed when:

- Method-level parity is green.
- Full materialization parity is green.
- Existing focused tests remain green for no-HR, HR recovery, `%HRR`, local start
  time, rollback, and whole-day limits.
- Statement-count evidence shows the intended O(chunks) reduction.
- Chunking/memory bounds are explicit.
- Final gates pass: `ruff check`, `ruff format --check`, `pyright`, `vulture`,
  and `pytest` or the repo's current consolidated check target.

## Suggested Next Implementation Order

1. Add parity scaffolding and a sequential reference gate.
2. Add batch source/scalar/running-HR repository reads.
3. Refactor `_activity_fact` into a per-row fact builder fed by preloaded maps.
4. Add zone/TRIMP batch read with Python-provided bounds.
5. Add bulk stream row partitioning for pure metric calls.
6. Add statement-count regression test.
7. Run targeted tests, then full gates.

The cheap independent follow-up remains valid: hoist
`repo.training_model_row(as_of_day, metric_version)` out of the `ROLLING_WINDOWS`
loop in `_materialize_rolling_facts`.
