# Phase 6: Full-Fidelity Strava Mirror - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 6 turns the Strava mirror into a **lossless normalized mirror** for activities and streams. The phase must preserve all useful Strava stream data in structured SQLite form, keep analytics queries fast, unify GPS storage, and provide operator-only coverage/backfill controls. It is not a Strava API wrapper, not a permanent raw JSON archive, and not an MCP/admin feature expansion.

The current roadmap phrase "Full-Fidelity Strava Mirror" means "no data is lost during normalization," not "store every original Strava JSON response forever."

</domain>

<decisions>
## Implementation Decisions

### Mirror Contract

- **D-01:** Phase 6 must implement a lossless normalized mirror, not a permanent raw payload store. Raw JSON is not valuable by itself unless it supports replay, audit, or debugging.
- **D-02:** Downstream agents must reinterpret the existing `MIRROR-01`/`MIRROR-02` wording as "preserve the full information content from Strava in queryable normalized structures." Do not plan a large raw/bronze archive as the primary deliverable.
- **D-03:** Existing `summary_json` and `detail_json` may remain because they already exist and are useful, but the stream contract should be normalized structured storage rather than raw stream response retention.
- **D-04:** Raw stream payload capture may exist as an optional/debug/transient implementation detail if cheap, but it must not become the source-of-truth product contract or a required MCP-visible surface.

### Stream Storage

- **D-05:** Use a "wide + extra JSON" stream point model.
- **D-06:** Keep fast scalar columns for metrics currently used by analytics, such as `heartrate`, `velocity`, `altitude`, `cadence`, `grade`, `gap_speed`, `gap_distance`, `is_moving`, `lat`, and `lng`.
- **D-07:** Add a structured per-point `values_json` or equivalent field for extra stream channels not represented as scalar columns, so unknown or future stream keys are not lost.
- **D-08:** Store stream channel metadata separately per activity/channel, including at least channel key, `original_size`, `resolution`, `series_type`, fetched timestamp or batch identity, and availability/error status where relevant.
- **D-09:** Avoid a pure long/EAV-only model for the hot analytics path because it would multiply rows and make existing SQLite analytics more complex. A long/channel table may be used only if the planner finds it materially simpler for metadata or coverage, not as the only stream storage.
- **D-10:** Do not solve this by adding only fixed columns for currently known Strava keys. That repeats the current problem when Strava adds or returns additional channels.

### GPS Canonical Format

- **D-11:** Canonical GPS storage is `lat` and `lng` REAL columns on stream points.
- **D-12:** `latlng` JSON is not canonical and should be removed in Phase 6 after migration, not kept as permanent compatibility.
- **D-13:** The migration must locally fill `lat`/`lng` from existing `latlng` JSON before removing `latlng`, with no Strava API call needed for coordinates that are already present locally.
- **D-14:** Post-migration writes and reads must use only `lat`/`lng` for canonical GPS data.

### Migration And Safety

- **D-15:** Deleting `latlng` immediately is acceptable despite higher migration complexity. There are no backward-compatibility obligations for old schemas or old CLI JSON shapes.
- **D-16:** Before schema/data migration, create a backup of the live mirror and run preflight checks. After migration, verify SQLite integrity, stream row counts, GPS point counts, channel coverage, and key analytics parity.
- **D-17:** Existing normalized stream rows must not be deleted or replaced just to add the new model. Migration should preserve rows and enrich them with canonical GPS and extra-channel structures where possible.

### Backfill

- **D-18:** Historical backfill should fetch only missing stream channels and channel metadata for activities that already have stream rows. It must not perform a full Strava resync and must not delete existing normalized rows.
- **D-19:** Backfill must be resumable, checkpointed, and rate-limit-aware. If Strava returns rate limit or transport errors, keep existing mirror data and report the backfill as incomplete/delayed.
- **D-20:** Backfill should estimate or report remaining work where possible: activities needing channel metadata, activities missing specific channels, and likely API call count. Exact precision is not required, but the operator needs enough visibility to decide whether to run or resume it.

### Operator Surface

- **D-21:** Coverage and backfill controls belong to local admin CLI commands, not MCP.
- **D-22:** Suggested command shape is local admin-oriented, for example `admin mirror-coverage` and `admin backfill-streams`, but planner may choose exact command names if the product/admin boundary remains clear.
- **D-23:** Live verification must be Docker-first because runtime data lives under `/opt/docker/mcp-strava`. Repo-local tests use temp or copied databases and must not mutate the live mirror.
- **D-24:** MCP must continue to expose only read-only training metrics. It must not expose raw payloads, coverage reports, stream backfill status, admin backfill controls, SQL, or sync logs.

### Storage Engine

- **D-25:** SQLite remains the primary mirror database for Phase 6.
- **D-26:** Do not migrate the operational mirror to DuckDB in Phase 6. The storage engine change would add risk and does not directly solve stream channel/GPS loss.
- **D-27:** DuckDB is a deferred analytics/read-model idea. It may be considered later for heavy stream scans, period comparisons, Parquet/export workflows, or experiments while SQLite remains the source of truth.
- **D-28:** Planner may use official DuckDB/SQLite findings as rationale, but implementation scope should stay on SQLite schema/repository/migration changes.

### the agent's Discretion

Planner may choose exact table names, migration version numbers, DTO/dataclass names, command names, JSON schema details, checkpoint table shape, and whether to keep a temporary raw stream debug field. These choices must preserve the lossless normalized mirror contract, SQLite primary mirror, `lat`/`lng` canonical GPS, `values_json`/equivalent extra-channel retention, channel metadata retention, rate-limit-aware backfill, and no-MCP-admin boundary.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project And Phase Scope

- `.planning/PROJECT.md` - Project goals, durable mirror constraint, MCP boundary, Docker runtime location, and v1.1 milestone scope.
- `.planning/REQUIREMENTS.md` - Phase 6 requirements. Interpret raw payload wording through this CONTEXT.md: normalized lossless retention is the goal.
- `.planning/ROADMAP.md` - Phase 6 goal and success criteria. Interpret "raw payloads" through this CONTEXT.md unless roadmap wording is updated before planning.
- `.planning/STATE.md` - Current milestone and phase routing.

### Prior Phase Context

- `.planning/phases/05-mcp-http-surface-docker-hardening/05-CONTEXT.md` - MCP read-only metric surface, no raw/admin/sync tools, Docker runtime data path, and gateway boundary.
- `.planning/phases/04-application-services-cli-refit/04-CONTEXT.md` - Product/admin CLI split, local mirror read services, freshness/completeness metadata, and no Strava calls from product read paths.
- `.planning/phases/03-strava-adapter-refresh-runtime/03-CONTEXT.md` - Refresh runtime owns Strava calls, checkpointing, rate limits, and mirror writes; read paths do not call Strava.
- `.planning/phases/02-sqlite-safety-repository-layer/02-CONTEXT.md` - Durable SQLite mirror, migration backup/preflight/parity discipline, and missing-stream semantics.

### Current Code

- `src/mcp_strava/refresh/_sync_ops.py` - Current `STREAM_KEYS`, stream fetch call, known-channel stream projection, and insertion flow to replace.
- `src/mcp_strava/types.py` - Current `StravaStreams` known-channel dataclass and parser that currently drops unknown stream channels from typed output.
- `src/mcp_strava/adapters/sqlite/repository.py` - Current stream insert/replace methods and hot analytics repository queries.
- `src/mcp_strava/adapters/sqlite/schema.py` - Current schema inventory that includes both `lat`/`lng` and `latlng`.
- `src/mcp_strava/adapters/sqlite/migrations.py` - Existing backup/preflight/migration/parity style to extend for Phase 6.
- `src/mcp_strava/application/metric_services.py` - Current MCP-facing metric service behavior that must stay read-only and not expose admin/coverage controls.
- `src/mcp_strava/interfaces/mcp_http.py` - MCP allowlist boundary; Phase 6 must not add raw/admin tools here.
- `src/mcp_strava/deploy/prepare_runtime.py` and `src/mcp_strava/deploy/preflight.py` - Docker/runtime DB preparation and fail-closed validation path.

### External References

- `https://developers.strava.com/docs/reference/` - Strava API reference for activity streams and available stream keys.
- `https://developers.strava.com/swagger/swagger.json` - Strava OpenAPI definition; confirms activity stream endpoint shape and required `keys` parameter.
- `https://docs.databricks.com/aws/en/lakehouse-architecture/deployment-guide/delta-lake` - Data-engineering reference for raw/curated layering; useful context only, not a requirement to build a raw archive.
- `https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/scenarios/cloud-scale-analytics/best-practices/data-lake-zones` - Data lake raw/curated zone context; useful background only.
- `https://duckdb.org/docs/stable/connect/concurrency` - DuckDB concurrency model; supports deferring DuckDB as analytics/read model rather than primary operational mirror.
- `https://duckdb.org/docs/stable/core_extensions/sqlite` - DuckDB can query SQLite files via extension, supporting a future hybrid approach without replacing SQLite now.
- `https://www.sqlite.org/wal.html` - SQLite WAL reader/writer concurrency behavior relevant to current MCP/read plus refresh/write runtime.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `SQLiteRepository.insert_stream_rows_chunked()` and `replace_stream_rows_chunked()` already support chunked writes and are the natural insertion point for richer stream rows.
- `RefreshPolicy`, `refresh_state`, and checkpoint stages already exist and should be reused for resumable stream-channel backfill.
- SQLite migration tooling already creates backups and performs preflight/post-checks; Phase 6 should extend that path instead of adding ad hoc live DB edits.
- Existing product/admin CLI split from Phase 4 is the right place to add coverage/backfill commands below the product/MCP surface.

### Established Patterns

- Product and MCP read paths must remain Strava-free.
- MCP tool registry is an explicit allowlist and must not gain operational capabilities.
- Missing streams/HR/details are represented as explicit partial or unavailable data, never as rest or zero load.
- Tests should use temp or copied SQLite databases; live runtime validation is Docker-first.

### Integration Points

- `refresh/_sync_ops.py` must stop treating `STREAM_KEYS` plus `StravaStreams` as the complete data model.
- Repository stream writes must preserve scalar hot-path fields and an extra-channel JSON field or equivalent.
- Schema inventory and preflight must know about new stream metadata / extra-channel storage and the removal of `latlng`.
- Backfill should run below CLI admin/runtime layers and use the Strava adapter/rate limiter rather than raw HTTP.
- SQLite remains the primary source of truth. DuckDB should not be introduced in Phase 6 except as a documented deferred idea.

</code_context>

<specifics>
## Specific Ideas

- "Full fidelity" means "structured data not lost," not "original JSON stored forever."
- Preferred stream point shape: scalar columns for current analytics plus a structured `values_json` for non-scalar or extra stream channel values.
- Preferred channel metadata shape: one row per activity/channel describing `original_size`, `resolution`, `series_type`, fetched status, and missing/error reason.
- Preferred coverage output: counts by activity/date/sport for stream rows, GPS points, channel availability, and backfill-needed status.
- Backfill should be able to say "come back later" when rate-limited, while leaving current analytics usable.
- DuckDB may be useful later for analytical read models, but Phase 6 should not spend complexity budget on a storage-engine migration.

</specifics>

<deferred>
## Deferred Ideas

- Permanent raw Strava stream payload archive is deferred and currently not desired. Revisit only if replay/audit needs become concrete.
- MCP raw mirror payload tools are out of scope.
- Full Strava account archival beyond activities/streams remains out of scope for this phase.
- DuckDB-derived analytics/read model is deferred until SQLite becomes a proven bottleneck for heavy analytical queries.
- Training model changes and new coaching interpretations remain outside Phase 6.

</deferred>

---

*Phase: 06-Full-Fidelity Strava Mirror*
*Context gathered: 2026-05-22*
