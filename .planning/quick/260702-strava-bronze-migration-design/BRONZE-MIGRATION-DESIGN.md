# Strava Bronze Payload Migration Design

## Decision

Keep the current containment patch small: ignore Strava `id_str` as a
non-semantic summary-field duplicate so the runtime stops rewriting indexed
activity rows for payload noise.

Design the larger migration separately. The durable fix is to stop storing raw
Strava payloads inside the modeled `activities` table and move source payloads
into an explicit bronze namespace.

This is not a compatibility project. Any temporary view or adapter described
below is migration scaffolding for data preservation and blast-radius control;
it should be removed once the code reads the new source boundary directly.

## Current Problem

The current `activities` table mixes three responsibilities:

- silver modeled activity fields used by product logic;
- raw Strava summary/detail JSON used for provenance and some late extraction;
- source-change detection that currently compares raw payload shape.

That made an additive upstream field (`id_str`) look like a meaningful activity
change. The ingest path then rewrote an indexed `activities` row, which exposed a
DuckDB index failure and made the service unhealthy.

The hotfix removes this specific trigger. The migration removes the class of
problem.

## Target Shape

- Bronze: raw Strava source payloads exactly as fetched, plus source metadata and
  schema verdict.
- Silver: modeled mirror tables such as `activities`, `streams`, and
  stream-channel rows.
- Gold: read-model facts and aggregates derived from silver.

Unknown source fields should be preserved in bronze but must not silently change
silver or gold behavior.

The target architecture is a staged data pipeline:

```text
Strava API
    |
    v
Ingest service
    owns source auth, rate limits, fetch policy, raw capture
    writes only bronze.*
    |
    v
Processing / normalization
    reads committed eligible bronze rows
    validates, normalizes, projects, computes modeled hashes
    writes only silver.*
    |
    v
Data marts / facts
    reads normalized silver tables
    computes product-ready facts, aggregates, reports, projections
    writes only gold.*
    |
    v
MCP server
    read-only product surface
    reads gold/product views only
```

Each stage depends only on the previous durable namespace, not on the previous
stage's in-memory code path. The MCP server is the final read-only consumer of
prepared data, not a participant in fetch, normalization, or materialization.

This should stay local and boring. The target is not an enterprise data
platform. Keep one DuckDB database, the existing local/container service shape,
and simple in-process jobs where that is enough. The important boundary is stage
ownership and namespace write rules, not adding queues, distributed workers,
or extra storage engines.

The source-ingest side and the processing/materialization side should be
separate modules that only coordinate through database state:

- Source ingest owns Strava HTTP, auth, rate limits, raw payload capture, source
  schema verdicts, and bronze writes.
- Processing owns bronze-to-silver promotion, validation, modeled projection
  hashes, read-model materialization, and gold facts.
- Source ingest must not call processing services directly.
- Processing must not call Strava directly.
- A failure in source ingest should not corrupt or rewrite existing silver/gold
  data.
- A processing/materialization failure should not prevent preserving fetched raw
  source payloads in bronze.

This split is the main architectural goal of the migration.

The namespaces should also be isolated at the data-mutation level:

- The source ingest service can write only bronze tables and its own bronze
  ingest status tables.
- The source ingest service must not write, delete, invalidate, or enqueue work
  in silver or gold namespaces.
- Bronze writes must be append-only, so a broken ingest cycle cannot damage a
  previously good source snapshot.
- Processing reads only committed, eligible bronze rows and records its own
  cursor/checkpoint before writing silver.
- Processing failures can leave bronze ahead of silver, but must not make silver
  partially reflect an unvalidated source payload.
- Silver-to-gold materialization has its own checkpoint and must not be driven by
  source-ingest side effects directly.

With this boundary, a broken Strava fetcher can at worst stop new bronze rows or
write quarantined bronze rows. It cannot make the existing modeled mirror or
read-model facts unhealthy.

## Proposed Bronze Table

Use a real DuckDB schema namespace:

```sql
CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.activity_payloads (
    activity_id BIGINT NOT NULL,
    activity_day DATE,
    payload_kind VARCHAR NOT NULL,
    endpoint VARCHAR NOT NULL,
    fetched_at VARCHAR NOT NULL,
    payload_json VARCHAR NOT NULL,
    raw_hash VARCHAR NOT NULL,
    modeled_projection_hash VARCHAR,
    schema_status VARCHAR NOT NULL,
    drift_fingerprint VARCHAR,
    recorded_at VARCHAR NOT NULL,
    migrated_from_legacy BOOLEAN NOT NULL DEFAULT FALSE
);
```

Notes:

- `payload_kind` is `summary` or `detail`; this avoids two nearly identical
  tables and leaves room for future source payload kinds.
- Bronze should be append-only for refresh writes. Do not add primary keys or
  secondary indexes until there is measured need.
- Duplicate latest raw payloads are skipped by `raw_hash`, so repeated unchanged
  refreshes do not grow bronze unboundedly.
- `raw_hash` identifies the exact upstream payload.
- `modeled_projection_hash` identifies only fields the parser maps into silver.
- `schema_status` is one of `clean`, `known_ignored`, or `drift_blocked`.
- `drift_fingerprint` groups repeated unresolved schema drift so refresh does not
  waste Strava quota repeating the same failed promotion.

Latest payloads can be exposed through an internal migration view:

```sql
CREATE OR REPLACE VIEW bronze.latest_activity_payloads AS
SELECT *
FROM bronze.activity_payloads
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY activity_id, payload_kind
    ORDER BY fetched_at DESC, recorded_at DESC, raw_hash DESC
) = 1;
```

## Schema Drift Policy

- Known non-semantic fields: write bronze, mark `known_ignored`, allow silver
  promotion.
- Unknown additive fields: write bronze, mark `drift_blocked`, block silver
  promotion with an explicit `schema_drift_blocked` reason.
- Auth, rate-limit, and network failures: do not write partial bronze payloads;
  classify the refresh failure separately.
- DuckDB fatal errors: classify as storage failure and keep the service health
  message specific.

Runtime health should include at least:

- `failure_class`
- `reason_code`
- `blocked_stage`
- `retryable`
- `next_retry_at`

The service should not repeatedly spend API budget on the same unresolved drift
fingerprint. It can retry after the parser/schema registry changes or after an
explicit operator action.

## Migration Plan

1. Stop the single-owner service and take an offline DuckDB backup.
2. Add `bronze.activity_payloads` and `bronze.latest_activity_payloads`.
3. Backfill bronze from existing `activities.summary_json` and
   `activities.detail_json`, using existing activity metadata for
   `activity_id`, `activity_day`, and a migration timestamp or existing sync
   timestamp for `fetched_at`.
4. Verify backfill counts and hashes without calling Strava.
5. Split the code path into two module boundaries:
   - Strava source ingest writes bronze and source status only.
   - Processing promotes eligible bronze rows into silver and triggers gold
     recompute.
6. Change ingest to write bronze before any silver promotion.
7. Change idempotency to compare `modeled_projection_hash`, not raw JSON shape.
8. Change readers that still need raw payload values to read through a narrow
   repository query over bronze.
9. Promote commonly consumed raw JSON fields into modeled columns where they are
   product data:
   - `average_heartrate`
   - `max_heartrate`
   - `kudos_count`
   - `start_date`
   - `start_date_local`
   - `gear_id`
   - `calories` if any remaining code still extracts it from detail JSON
10. Rebuild `activities` offline without `summary_json` and `detail_json`.
11. Drop the internal migration view or adapter once direct bronze reads are in
    place.

No full Strava resync is required for this migration.

## Implementation Progress

Completed first slice:

- `bronze.activity_payloads` table and `bronze.latest_activity_payloads` view
  exist in schema creation and repository schema extension.
- Existing legacy `activities.summary_json` / `detail_json` rows are
  idempotently backfilled into bronze on repository open.
- Summary and detail fetches append raw payloads into bronze.
- Duplicate latest payloads are skipped by `raw_hash`, keeping unchanged refresh
  cycles idempotent in both silver and bronze.
- Summary fetches no longer rewrite existing silver `activities` rows directly;
  changed existing summaries are logged as deferred for the processing stage.
- Detail fetches no longer mutate `activities.detail_json` directly.
- `schema_validate(repo)` now acts as the bronze-to-silver processing boundary:
  it processes source-ingested latest bronze payloads, projects eligible summary
  payloads into silver `activities`, and then updates source-state hashes/dirty
  queue rows for read-model materialization.
- Detail fetch selection treats a latest bronze detail payload as already
  fetched, avoiding repeat Strava calls while silver processing is still split
  out.
- Activity lookup reads (`recent_activities`, `activity_by_id`, and
  `activity_materialization_sources`) prefer latest bronze payloads over legacy
  raw columns, while leaving the physical `activities` columns unchanged.
- Activity selectors, source-state hashing, and dirty-queue enqueue logic prefer
  latest bronze summary/detail payloads over legacy raw columns, so bronze
  source changes can advance `source_revision` without direct source-ingest
  writes to silver.
- Kudos candidate selection, read-model fact fetch joins, and the activity
  aggregate view now prefer latest bronze payloads over legacy raw columns.
- Runtime migration uses Python-supplied `recorded_at` values rather than DuckDB
  default expressions, after DuckDB WAL replay failed on `ALTER TABLE ... DEFAULT
  CURRENT_TIMESTAMP` during a container restart. The runtime DB was backed up
  before removing the failed WAL.

Remaining slices:

- Move any remaining materializer/product SQL dependencies from legacy raw
  columns to bronze reads or modeled silver columns, then remove migration
  fallbacks.
- Promote product fields currently parsed from raw JSON into stable modeled
  columns.
- Remove legacy raw JSON columns from `activities` after consumers no longer
  depend on them.

## Verification

- targeted migration/backfill/selector/read-model tests:
  `109 passed in 153.23s`
- `just check`: green
- `just unit`: `446 passed, 1 skipped in 82.96s`
- `just runtime`: green; final control run returned `list_workouts.count=1`
  with container `healthy running`, restart count `0`, and read-model
  materialization `noop` in 39 ms
- MCP smoke against the container for:
  - `list_workouts`
  - `get_workout_detail`
  - `get_training_aggregates`

Data checks:

- bronze summary count matches legacy non-null `summary_json` count;
- bronze detail count matches legacy non-null `detail_json` count;
- latest bronze payload for a sample activity matches the legacy JSON hash;
- silver row count does not shrink;
- read-model materialization is `noop` after a clean second run.

## Open Questions

- Whether stream source payloads should move into the same bronze table now or in
  a later step. Recommendation: do activity summary/detail first.
- Whether `fetched_at` should be stored as `TIMESTAMP` instead of `VARCHAR`.
  Recommendation: use the existing repository timestamp convention unless the
  schema layer already standardizes DuckDB timestamps.
- Whether `gear` nested detail should be modeled now. Recommendation: model only
  `gear_id` unless product code needs nested gear fields.

## Side Audit Findings

An additional read-only architecture pass found related cleanup candidates that
should be triaged separately from the incident hotfix:

1. `acquire_refresh_lease()` does a separate read and write, so lease ownership
   is not a real compare-and-swap. Make refresh lease acquisition atomic before
   adding more refresh stages.
2. Source invalidation recomputes hashes by rereading stored rows and stream
   data. Move toward incremental component hashes (`summary_hash`,
   `detail_hash`, `streams_hash`, `channels_hash`) so source identity is derived
   from write-time components, not full table reconstruction.
3. Stream coverage validates JSON-backed optional channels more strongly than
   column-backed channels. Coverage should verify each channel against its real
   storage shape.
4. Refresh health uses a `/tmp` sidecar file and missing file can mean "healthy
   enough". Move it to runtime state or treat disappearance after startup as an
   unhealthy condition.
5. `SCHEMA_VALIDATE` is a named refresh stage but currently does no meaningful
   validation. Either implement it as the bronze-to-silver validation barrier or
   remove the stage.
6. Existing read-model logic-version bootstrap can adopt the current fingerprint
   without proving stored facts were produced by that logic. Keep that behavior
   only as an explicit migration/bootstrap path, or force a one-time recompute.
