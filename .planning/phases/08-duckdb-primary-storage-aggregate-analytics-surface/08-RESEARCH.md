# Phase 08: DuckDB Primary Storage & Aggregate Analytics Surface - Research

**Researched:** 2026-05-25
**Domain:** DuckDB Python storage migration, local MCP runtime concurrency, aggregate analytics query layer
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

Source: `.planning/phases/08-duckdb-primary-storage-aggregate-analytics-surface/08-CONTEXT.md` [VERIFIED: codebase read]

### Locked Decisions

## Implementation Decisions

### Cutover Policy

- **D-01:** Use a fast one-shot cutover from SQLite to DuckDB, not a long-running dual-primary or shadow-write architecture.
- **D-02:** Fast cutover still requires a pinned verified SQLite backup, a migration from a stable copy or backup, DuckDB post-checks, parity checks, Docker smoke, MCP smoke, and the current 100 ms p95 MCP latency gate before acceptance.
- **D-03:** Stop or quiesce runtime writers before live cutover and prove there is no active refresh lease. An active lease blocks cutover until resolved.
- **D-04:** After cutover, runtime repository, refresh, preflight, healthcheck, Docker, and CLI paths must use DuckDB primary storage. Runtime code must not keep writing SQLite.
- **D-05:** Keep the pre-Phase-8 SQLite backup pinned outside normal retention until migration parity, Docker smoke, MCP smoke, latency gate, and the first accepted post-cutover refresh pass.
- **D-06:** Rollback means stop the DuckDB runtime, restore or repoint to the pinned SQLite DB plus previous runtime config/image, run preflight, then Docker smoke/perf validation. A full Strava resync is not an acceptable rollback or validation mechanism.

### DuckDB Storage And Query Layer

- **D-07:** DuckDB is the primary runtime database. Avoid a permanent SQLite bridge, bidirectional sync, CDC, or dual-primary system.
- **D-08:** Preserve physical DuckDB tables for mirrored Strava data and explicit derived facts: activities, streams, stream channels, kudos, refresh metadata, activity metric facts, daily load facts, training model facts, and read-model metadata.
- **D-09:** Do not add new permanent period aggregate tables initially. Use DuckDB views plus whitelisted repository query builders for aggregate queries; treat physical aggregate tables as a fallback only if live Docker benchmarks prove they are needed.
- **D-10:** DuckDB views are acceptable for normalizing typed dates, metric columns, completeness metadata, sport/scope fields, and aggregate-ready fact rows. Macros may be used only for small reusable SQL primitives if they remain simple.
- **D-11:** Domain-heavy computation still belongs below the request path. DuckDB aggregates prepared facts; it does not recompute expensive stream-derived metrics inside MCP calls.
- **D-12:** Store and query canonical activity days as `DATE`, not text slicing. Date ranges use half-open intervals `[start_day, end_day_exclusive)`.
- **D-13:** DuckDB runtime must respect native concurrency constraints: one read-write process owns the DB file. Separate healthcheck or smoke processes must not open the same DB read-write while the service owns it.
- **D-14:** SQLite import is migration-only. Because SQLite is weakly typed and DuckDB is strongly typed, migration must use controlled casts and parity checks for dates, JSON/text, numeric fields, and nullable columns.

### MCP Aggregate Surface

- **D-15:** Add one constrained generic MCP tool named `get_training_aggregates`.
- **D-16:** Keep the existing product tools: `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, and `project_fitness_state`.
- **D-17:** `get_training_aggregates` should be designed from agent/user scenarios, not from the old CLI. Primary scenarios are daily briefs, weekly/monthly digests, period comparisons, sport-specific efficiency trends, and historical factual exploration.
- **D-18:** `get_training_aggregates` should accept product-level parameters, not SQL: date range, bucket, metric ids or registry-defined metric bundle, grouping scope, sport filters, registry-default aggregation mode, and whether empty buckets are included.
- **D-19:** Support both explicit metric ids and predefined metric bundles. Bundles must be defined from the metric registry, not hand-built in the MCP handler.
- **D-20:** Do not expose gear/equipment filtering or grouping in Phase 8 aggregate queries.
- **D-21:** Do not expose raw SQL, DuckDB table names, query plans, migrations, preflight, sync, backfill, recompute, dirty queues, token state, raw Strava payloads, raw streams, or debug/admin controls through MCP.
- **D-22:** Aggregate responses remain factual. They include values, units, aggregation mode, denominator, sample size, coverage, missing reasons, freshness, and metric version metadata. They must not say whether the athlete should train, rest, improve, or worry.

### Period Comparison

- **D-23:** Rewrite `compare_periods` over the same aggregate query layer as `get_training_aggregates`.
- **D-24:** `compare_periods` should call the aggregate layer twice with `bucket=all_time` for period A and period B, then format deltas, percentages, trend direction, sample sizes, coverage, missing reasons, and metric version status.
- **D-25:** Do not keep a separate Python row-scanning or per-metric recomputation path for period comparison once the aggregate layer exists.

### Bucket And Filter Contract

- **D-26:** Supported buckets for Phase 8 are `day`, `week`, `month`, `year`, and `all_time`.
- **D-27:** Week buckets use Monday start, matching DuckDB `time_bucket` behavior for week-width date buckets.
- **D-28:** All-time starts at the earliest activity date in the local mirror unless the caller supplies an explicit start date.
- **D-29:** Supported scopes are global and per-sport, controlled by metric registry metadata. Metrics with sport-sensitive semantics default to per-sport comparison unless explicitly marked `global` or `both`.
- **D-30:** Rolling windows use `as_of_day` plus whitelisted `window_days`, with initial windows `7`, `14`, `28`, `42`, and `90`.
- **D-31:** Gear/equipment is not a supported aggregate filter or grouping dimension in Phase 8.

### Aggregation Semantics

- **D-32:** Aggregation semantics belong in the metric registry. Do not mint duplicate metric ids just to represent alternative aggregation math.
- **D-33:** Volume and load metrics aggregate by sum unless the registry defines a different mode. Examples: distance, moving time, elevation, TRIMP, HR-zone seconds, active days, workout count.
- **D-34:** Named daily averages divide by calendar bucket days by default. Active-day averages require an explicit registry metric or explicit denominator metadata.
- **D-35:** Heart-rate and power averages must be weighted averages, not naive averages of activity averages. HR should be weighted by HR sample count or sample seconds; watts should be weighted by watts sample count or sample seconds when available.
- **D-36:** Pace/speed-style aggregate facts should be computed from distance/time ratios, not averages of per-activity pace/speed, unless the registry explicitly defines another denominator.
- **D-37:** Efficiency and skewed metrics should use median plus distribution context by default. Examples include cardiac cost, adjusted cardiac cost, cardiac drift, HR recovery, HRR percentage, vertical speed, elevation density, and kudos-per-activity.
- **D-38:** Default quantiles for distribution context are p25, median, and p75. Responses must include sample size so agents can judge low-N results.
- **D-39:** Model-state metrics such as fitness, fatigue, form, ACWR, ATL, and CTL aggregate as last-known state for the bucket unless the registry explicitly defines another mode.
- **D-40:** Categorical facts such as form zone, ACWR zone, drift severity, completeness status, and warning/status codes aggregate as distributions/counts, not numeric averages.
- **D-41:** Kudos are social/context facts. `kudos_count` may be aggregated as count/sum or distribution where useful; kudos names remain per-workout detail context and should not be emitted as aggregate bucket payloads.

### Completeness And Provenance

- **D-42:** Every aggregate row must include bucket start/end, bucket width, metric id, unit, calculation description or registry reference, aggregation mode, denominator, value, sample size, activity count, null/excluded count, completeness status, missing reasons, metric version status, materialized timestamp, mirror freshness, and read-model freshness.
- **D-43:** HR, watts, stream, and GPS coverage must be explicit where relevant. Missing denominators suppress weighted values or mark them unavailable/partial; they must not silently degrade to naive averages.
- **D-44:** Mixed metric versions in a bucket or comparison must be reported as mixed/degraded and must not be silently compared as if formulas were identical.

### Expert Panel Routing

- **D-45:** Planner should use expert-panel or research lenses for hard technical choices that remain after this context, especially DuckDB cutover mechanics, healthcheck concurrency, and whether any physical aggregate table is justified by benchmark data.
- **D-46:** The user should only be asked product/business questions not answerable from this context. Technical defaults above are locked unless research finds they are unsafe or impossible.

### the agent's Discretion

Planner may choose exact DuckDB table names, view names, repository class names, migration command names, JSON field spelling, metric-bundle names, and test fixture shapes. These choices must preserve the locked constraints above: DuckDB primary, fast-but-backed-up cutover, no permanent dual-primary, no raw/admin MCP surface, metric-registry-driven aggregation semantics, and sub-100 ms p95 MCP acceptance unless explicitly changed.

### Deferred Ideas (OUT OF SCOPE)

- Gear/equipment aggregation and filtering are explicitly out of Phase 8.
- Physical period aggregate tables are deferred until benchmark evidence shows DuckDB views/query builders miss the latency target.
- Permanent raw payload archive, Parquet/lakehouse layering, CDC, bidirectional sync, and multi-user/SaaS storage concerns remain out of scope.
- Training-model redesign and coaching interpretation remain outside the service.
</user_constraints>

## Summary

Phase 8 should be planned as a storage cutover plus aggregate query architecture, not as an incremental analytics feature. The current live runtime is a Docker container named `mcp-strava`, it mounts `/opt/docker/mcp-strava` at `/runtime`, and its live SQLite DB is `/opt/docker/mcp-strava/data/strava.db` with `user_version=7`, `quick_check=ok`, 600 activities, 2,669,762 stream rows, 7,800 stream-channel rows, 124 kudos rows, 600 activity fact rows, 516 daily/model fact rows, 8 rolling-period rows, and zero dirty read-model rows. [VERIFIED: runtime probe]

The biggest planning constraint is DuckDB concurrency. DuckDB's documented in-process model allows one read-write process for a database file, while multiple-process mode is read-only only; the current container starts separate `refresh` and `mcp-http` child processes and the healthcheck opens the DB in a separate process. [CITED: https://duckdb.org/docs/current/connect/concurrency] [VERIFIED: `src/mcp_strava/deploy/service.py`, `src/mcp_strava/deploy/healthcheck.py`] Therefore the planner should include a topology change: make one service process own the DuckDB connection and run refresh/materialization inside that process or behind an in-process DB actor; healthcheck and smoke clients should validate through HTTP/owner-process probes rather than independently opening the DuckDB file. [ASSUMED]

**Primary recommendation:** Use `duckdb` 1.5.3 behind a human package-legitimacy checkpoint, migrate from a stopped pinned SQLite backup into typed DuckDB tables with explicit casts/parity checks, implement registry-driven views plus whitelisted aggregate query builders first, and only add physical aggregate tables if Docker p95 benchmarks exceed 100 ms. [VERIFIED: PyPI JSON] [CITED: https://duckdb.org/docs/current/sql/statements/create_view] [VERIFIED: 08-CONTEXT.md]

## Project Constraints (from AGENTS.md)

- Preserve the existing local mirror; schema/storage work requires backup, preflight, and verification. [VERIFIED: AGENTS.md]
- Avoid full Strava resync as a migration or rollback mechanism because Strava calls are expensive and rate-limited. [VERIFIED: AGENTS.md]
- Keep MCP read-only and product-facing: workouts, analytics, reports, and recommendations only; sync/admin/debug/raw/SQL controls remain below MCP. [VERIFIED: AGENTS.md]
- Keep automatic mirror refresh at least daily; request-time freshness checks belong in core/application logic, not MCP tool design. [VERIFIED: AGENTS.md]
- Keep default HTTP serving local/container-network safe and avoid public unauthenticated exposure. [VERIFIED: AGENTS.md]
- Preserve `just test`; add targeted tests for repository, migrations, freshness, and MCP tools. [VERIFIED: AGENTS.md]
- Put business logic under `src/mcp_strava/` application/domain layers, not in CLI or MCP handlers. [VERIFIED: AGENTS.md]
- Use dataclasses/shared types for cross-module result shapes. [VERIFIED: AGENTS.md]
- Current GSD instruction says file-changing work should stay within GSD workflows; this research file is part of the requested GSD research phase. [VERIFIED: AGENTS.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| SQLite-to-DuckDB one-shot migration | Database / Storage | CLI / Deploy | Migration owns durable data transformation and parity; CLI/deploy only trigger stopped-runtime commands. [VERIFIED: 08-CONTEXT.md] |
| DuckDB primary repository | Database / Storage | API / Backend | Repository owns SQL, transactions, and connection policy; services should not know table details. [VERIFIED: codebase grep] |
| Refresh worker after cutover | API / Backend | Database / Storage | Refresh orchestrates Strava/source writes, but must run inside the one DuckDB-owning process or DB actor. [CITED: https://duckdb.org/docs/current/connect/concurrency] |
| Healthcheck after cutover | API / Backend | Docker runtime | Healthcheck should ask the service/owner process for DB readiness; separate read-write DB opens violate the DuckDB constraint. [CITED: https://duckdb.org/docs/current/connect/concurrency] |
| Aggregate query layer | Database / Storage | API / Backend | DuckDB should perform bucket/group/aggregate SQL over prepared facts; application code validates product parameters and shapes responses. [VERIFIED: 08-CONTEXT.md] |
| `get_training_aggregates` MCP tool | API / Backend | MCP Interface | MCP exposes product-level parameters and factual payloads; it must not expose SQL or storage names. [VERIFIED: 08-CONTEXT.md] |
| `compare_periods` rewrite | API / Backend | Database / Storage | Service formats two aggregate-layer calls; aggregate math is shared with `get_training_aggregates`. [VERIFIED: 08-CONTEXT.md] |
| 100 ms p95 acceptance gate | Docker runtime | MCP smoke client | Existing Justfile has `mcp-read-model-perf` defaulting to `p95_ms=100`; planner must extend it to the sixth tool. [VERIFIED: Justfile] |

<phase_requirements>
## Phase Requirements

No formal requirement IDs are mapped for Phase 8 yet. Use these planning requirement IDs to cover the ROADMAP success criteria and locked D-XX decisions. [VERIFIED: `.planning/ROADMAP.md`] [VERIFIED: `08-CONTEXT.md`]

| ID | Description | Research Support |
|----|-------------|------------------|
| P8-SC-01 | Back up, migrate, and parity-check live SQLite mirror data into DuckDB. | Migration, Runtime State Inventory, Common Pitfalls, Validation Architecture. |
| P8-SC-02 | Runtime repository, refresh, migration, preflight, healthcheck, Docker, and CLI use DuckDB primary. | Architecture Patterns, Runtime State Inventory, Concurrency Pitfalls. |
| P8-SC-03 | DuckDB aggregates answer day/week/month/year/all-time metric queries. | Aggregate Query Layer, Code Examples, Metric Registry Semantics. |
| P8-SC-04 | `compare_periods` uses the same aggregate query layer and preserves metadata. | Period Comparison Pattern, MCP Surface Pattern. |
| P8-SC-05 | Python runtime stays on Python 3.14 and Docker uses the current stable 3.14 patch where available. | Environment Availability, Package Legitimacy Audit. |
| P8-D-ALL | Honor D-01 through D-46. | User Constraints section copies all locked decisions verbatim. |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `duckdb` [ASSUMED: slopcheck unavailable; human verification required before install] | 1.5.3 | In-process DuckDB engine and Python DB-API connection for persistent `.duckdb` primary storage. | Official DuckDB Python docs name `duckdb` as the Python client and PyPI reports 1.5.3 with CPython 3.14 manylinux wheels uploaded on 2026-05-20. [CITED: https://duckdb.org/docs/current/clients/python/overview] [VERIFIED: PyPI JSON] |
| `mcp` | 1.27.1 | Existing FastMCP HTTP server and MCP smoke client. | Already pinned in the repo environment and used by `interfaces/mcp_http.py` and `devtools/mcp_client`. [VERIFIED: `uv pip show mcp`] |
| `pytest` | 9.0.3 | Unit/integration test runner. | Already installed in `.venv` and configured in `pyproject.toml`. [VERIFIED: `uv run pytest --version`] |
| Docker + Docker Compose | Docker 29.3.1 / Compose v5.1.1 | Docker-first runtime smoke and live service validation. | Existing `just test` builds and runs the compose service before MCP smoke. [VERIFIED: runtime probe] [VERIFIED: Justfile] |

### Supporting

| Library / Tool | Version | Purpose | When to Use |
|----------------|---------|---------|-------------|
| `PyYAML` | 6.0.3 | Existing gateway catalog YAML handling. | Preserve for deploy/gateway tooling; not part of DuckDB migration math. [VERIFIED: `uv pip show PyYAML`] |
| DuckDB `sqlite` extension | DuckDB 1.5.3 bundled/loadable in Python smoke | Read SQLite backup/copy during migration using `sqlite_scan` or `ATTACH ... (TYPE sqlite)`. | Use only in migration tooling, not runtime dual-primary access. [CITED: https://duckdb.org/docs/current/guides/database_integration/sqlite] [VERIFIED: Docker Python smoke] |
| `sqlite3` stdlib | Python stdlib | Backup/preflight/parity over the old SQLite input. | Use only for stopped-source backup/parity and rollback validation after Phase 8. [VERIFIED: codebase grep] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| DuckDB primary | Keep SQLite primary with DuckDB read sidecar | Rejected by D-07 because it creates a permanent dual-primary/bridge concern. [VERIFIED: 08-CONTEXT.md] |
| Views + query builders | Permanent physical aggregate tables | Deferred by D-09 until live Docker benchmarks prove views miss 100 ms p95. [VERIFIED: 08-CONTEXT.md] |
| In-process refresh thread/DB actor | Separate refresh and MCP processes both opening DuckDB | Separate read-write processes conflict with DuckDB's documented concurrency model. [CITED: https://duckdb.org/docs/current/connect/concurrency] |
| Registry-driven aggregation | Per-handler metric math | Rejected by D-32 and D-25 because it duplicates semantics and makes `compare_periods` drift. [VERIFIED: 08-CONTEXT.md] |

**Installation:**

Do not install until the package legitimacy checkpoint is cleared, because slopcheck was unavailable. [ASSUMED]

```bash
uv add 'duckdb>=1.5.3,<1.6'
uv lock
docker compose -f deploy/docker-compose.yml build --no-cache mcp-strava
```

**Version verification performed:**

```bash
docker run --rm python:3.14-slim python -m pip index versions duckdb
docker run --rm python:3.14-slim python -m pip install --dry-run 'duckdb==1.5.3'
uv pip install --dry-run 'duckdb>=1.5.3,<1.6'
```

Docker `python:3.14-slim` resolved to Python 3.14.5 and could install/import `duckdb==1.5.3`; the repo-local `python3` is 3.13.5, but `uv run python` uses Python 3.14.2. [VERIFIED: Docker runtime probe] [VERIFIED: local env probe]

## Package Legitimacy Audit

> Required because this phase installs an external Python package. Slopcheck could not be installed because neither system `pip` nor `.venv` pip is available, and `slopcheck` is not already on PATH. [VERIFIED: env probe]

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `duckdb` [ASSUMED: slopcheck unavailable; human verification required before install] | PyPI | First PyPI release found: 2019-05-08; latest 1.5.3 uploaded 2026-05-20. [VERIFIED: PyPI JSON] | Unavailable: PyPI Stats returned HTTP 429 and PePy returned HTTP 401 during research. [VERIFIED: web/API probe] | `https://github.com/duckdb/duckdb-python` from PyPI project URLs. [VERIFIED: PyPI JSON] | unavailable | Flagged - planner must add `checkpoint:human-verify` before install. |

**Packages removed due to slopcheck [SLOP] verdict:** none; slopcheck did not run. [VERIFIED: env probe]
**Packages flagged as suspicious [SUS]:** none by slopcheck; `duckdb` remains gated only because slopcheck was unavailable. [VERIFIED: env probe]

## Architecture Patterns

### System Architecture Diagram

```text
Stopped runtime / cutover command
  -> verify no refresh lease and create pinned SQLite backup
  -> DuckDB migration connection owns new DB file
      -> load SQLite extension against backup/copy
      -> create typed DuckDB tables
      -> insert with controlled casts
      -> create aggregate-ready views
      -> run row/count/coverage/fact/MCP parity
  -> switch runtime DB path to DuckDB
  -> start single DuckDB-owner service process
      -> MCP HTTP handlers validate product parameters
      -> aggregate service selects registry metric specs
      -> whitelisted query builder runs DuckDB aggregates over prepared facts
      -> factual MCP response includes freshness, coverage, metric version metadata
      -> in-process refresh/materialization worker writes through same DB-owner boundary
  -> HTTP-only smoke/perf clients
      -> list tools, call product tools, enforce 100 ms p95
```

### Recommended Project Structure

```text
src/mcp_strava/
+-- adapters/
|   +-- duckdb/
|   |   +-- __init__.py
|   |   +-- connection.py          # DuckDB connect/read_only policy and row helpers
|   |   +-- schema.py              # typed table/view inventory and post-checks
|   |   +-- migrations.py          # SQLite-backup -> DuckDB cutover command
|   |   +-- repository.py          # DuckDB primary repository replacing runtime SQLite
|   |   +-- aggregate_queries.py   # whitelisted metric/bucket SQL builders
|   +-- sqlite/                    # migration input, rollback, and old backup tools only
+-- application/
|   +-- metric_registry.py         # add aggregate semantics and bundles
|   +-- aggregate_services.py      # get_training_aggregates service
|   +-- metric_services.py         # compare_periods calls aggregate service twice
+-- deploy/
|   +-- preflight.py               # DuckDB runtime validation through owner/offline mode
|   +-- healthcheck.py             # HTTP/owner-process health; no read-write DB open
|   +-- service.py                 # single process owns DuckDB and refresh scheduling
+-- interfaces/
    +-- mcp_http.py                # adds get_training_aggregates allowlisted tool
```

This structure follows the existing adapter/application/interface split and replaces runtime SQLite names instead of hiding DuckDB code under `adapters/sqlite/`. [VERIFIED: `.planning/codebase/ARCHITECTURE.md`] [ASSUMED]

### Pattern 1: Single DuckDB Owner Process

**What:** Open the persistent DuckDB file in one read-write process; share work across threads/cursors or an in-process DB actor, not separate read-write processes. [CITED: https://duckdb.org/docs/current/connect/concurrency] [CITED: https://duckdb.org/docs/current/guides/python/multiple_threads]

**When to use:** Required for the live MCP server plus refresh worker after cutover. [VERIFIED: `src/mcp_strava/deploy/service.py`] [VERIFIED: 08-CONTEXT.md]

**Planning recommendation:** Replace the current two-child supervisor topology with either an in-process refresh thread in the MCP service process or an owner-process command queue; do not let `mcp-http`, `refresh.worker`, healthcheck, and CLI all open the same `.duckdb` file independently. [ASSUMED]

### Pattern 2: Stopped-Source Migration With Explicit Typed Inserts

**What:** Treat SQLite as migration input only: stop writers, create a pinned backup, attach/scan that backup from DuckDB, create typed DuckDB tables, and insert through explicit `TRY_CAST`/validation expressions. [CITED: https://duckdb.org/docs/current/guides/database_integration/sqlite] [CITED: https://duckdb.org/docs/current/core_extensions/sqlite]

**When to use:** Required for D-01 through D-14. [VERIFIED: 08-CONTEXT.md]

**Why:** DuckDB docs state SQLite is weakly typed and DuckDB is strongly typed; invalid values in a column mapped to a strong type can fail reads unless conversion is controlled. [CITED: https://duckdb.org/docs/current/core_extensions/sqlite]

### Pattern 3: Views Normalize Facts; Query Builders Aggregate

**What:** Create DuckDB views for typed dates, scope/sport fields, completeness fields, and aggregate-ready facts; use Python query builders that only emit approved templates from registry metadata. [VERIFIED: 08-CONTEXT.md]

**When to use:** Use for `get_training_aggregates` and `compare_periods`. [VERIFIED: 08-CONTEXT.md]

**Why:** DuckDB views are not physically materialized and are re-run when referenced, so they are good for normalization but do not replace performance benchmarks. [CITED: https://duckdb.org/docs/current/sql/statements/create_view]

### Pattern 4: Registry-Driven Metric Semantics

**What:** Extend `MetricDefinition` with aggregate fields instead of hard-coding math in MCP handlers. The current registry already holds `metric_id`, unit, source, scope, sport scope, comparison mode, directionality, requirements, missing reasons, exposure, calculation, and description. [VERIFIED: `src/mcp_strava/types.py`] [VERIFIED: `src/mcp_strava/application/metric_registry.py`]

**Add fields:** `aggregate_mode`, `fact_source`, `value_column`, `weight_column`, `numerator_column`, `denominator_column`, `category_column`, `default_denominator`, `supported_buckets`, `supported_scopes`, `bundle_ids`, `default_quantiles`, and `version_policy`. [ASSUMED]

**When to use:** Every metric exposed by `get_training_aggregates` or `compare_periods`. [VERIFIED: 08-CONTEXT.md]

### Pattern 5: Product MCP Tool Wrapper

**What:** MCP handler validates product parameters, calls application service, and returns `ServiceEnvelope`-style factual payloads; it never sees DuckDB table names or SQL. [VERIFIED: `src/mcp_strava/interfaces/mcp_http.py`] [VERIFIED: 08-CONTEXT.md]

**Parameters:** `start_day`, `end_day_exclusive` or `as_of_day`, `bucket`, `metric_ids`, `metric_bundle`, `scope`, `sport_types`, `window_days`, and `include_empty_buckets`. [VERIFIED: 08-CONTEXT.md] [ASSUMED: exact JSON field names]

**Response rows:** Include bucket start/end, metric id, unit, aggregate mode, denominator, value, p25/median/p75 where relevant, sample size, activity count, null/excluded count, completeness, missing reasons, metric version status, materialized timestamp, mirror freshness, and read-model freshness. [VERIFIED: 08-CONTEXT.md]

### Anti-Patterns to Avoid

- **Permanent SQLite bridge:** Keeps two storage semantics alive and violates D-07. [VERIFIED: 08-CONTEXT.md]
- **Separate read-write DB processes:** Current `refresh` plus `mcp-http` process split conflicts with DuckDB's documented single read-write process model. [CITED: https://duckdb.org/docs/current/connect/concurrency] [VERIFIED: `src/mcp_strava/deploy/service.py`]
- **Healthcheck opens DuckDB directly while service owns it:** Current healthcheck opens the SQLite DB; Phase 8 should use owner-process/HTTP health for live checks. [VERIFIED: `src/mcp_strava/deploy/healthcheck.py`] [CITED: https://duckdb.org/docs/current/connect/concurrency]
- **Text date slicing in hot paths:** D-12 requires canonical `DATE` and half-open ranges. [VERIFIED: 08-CONTEXT.md]
- **Naive averaging of averages:** D-35 and D-36 require weighted averages or ratio-of-sums where denominators exist. [VERIFIED: 08-CONTEXT.md]
- **MCP raw SQL/table-name exposure:** Violates D-18 and D-21. [VERIFIED: 08-CONTEXT.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Time bucket alignment | Python date bucketing loops | DuckDB `time_bucket` for day/week/month/year query grouping | DuckDB documents weekly grids anchored on a Monday for sub-month buckets. [CITED: https://duckdb.org/docs/current/sql/functions/date] |
| Weighted HR/power averages | Arithmetic mean of activity averages | DuckDB `weighted_avg(value, NULLIF(weight, 0))` | DuckDB supports weighted average and skips NULL weights; missing denominator should produce unavailable/partial metadata. [CITED: https://duckdb.org/docs/current/sql/functions/aggregates] [VERIFIED: 08-CONTEXT.md] |
| Median and quantiles | Python sorting per request | DuckDB `median` / `quantile_cont(value, [0.25,0.5,0.75])` | DuckDB exposes median and continuous quantiles in aggregate SQL. [CITED: https://duckdb.org/docs/current/sql/functions/aggregates] |
| Period comparison math | Separate Python row scanner | Shared aggregate layer with `bucket=all_time` twice | D-23 through D-25 require this shared path. [VERIFIED: 08-CONTEXT.md] |
| SQL exposed through MCP | User-supplied SQL or table names | Product-level parameter validator plus whitelisted query templates | MCP boundary forbids raw SQL, query plans, table names, and admin/debug controls. [VERIFIED: 08-CONTEXT.md] |
| SQLite import type inference | Blind `CREATE TABLE AS SELECT *` | Explicit DuckDB schema plus controlled casts from SQLite backup/staging | DuckDB docs warn SQLite weak typing can fail strong typed reads. [CITED: https://duckdb.org/docs/current/core_extensions/sqlite] |
| Live DB probes | External process opening the DB file | Owner-process health endpoint and HTTP MCP smoke | DuckDB read-write database ownership is process-scoped. [CITED: https://duckdb.org/docs/current/connect/concurrency] |

**Key insight:** DuckDB reduces aggregate-query complexity, but it increases runtime ownership discipline compared with the current SQLite WAL pattern. [CITED: https://duckdb.org/docs/current/connect/concurrency] [VERIFIED: `src/mcp_strava/adapters/sqlite/connection.py`]

## Runtime State Inventory

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | Live DB: `/opt/docker/mcp-strava/data/strava.db`, 537,722,880 bytes, SQLite `user_version=7`, `quick_check=ok`, 600 activities, 2,669,762 streams, 7,800 stream channels, 124 kudos, 600 activity facts, 516 daily load facts, 516 model facts, 8 rolling facts, 0 dirty rows. [VERIFIED: runtime probe] | Stop service, confirm no active lease, create pinned pre-Phase-8 SQLite backup, migrate from stable copy/backup, parity-check all source/fact counts and coverage, then switch runtime to DuckDB. |
| Stored data | Repo `data/strava.db` is absent; the canonical live DB is under `/opt/docker/mcp-strava`. [VERIFIED: runtime probe] | Do not assume repo-local DB exists; tests should use temp fixtures or a copied live DB. |
| Live service config | Docker container `mcp-strava` is healthy, uses image `deploy-mcp-strava`, env `MCP_STRAVA_DB_PATH=/runtime/data/strava.db`, and bind-mounts `/opt/docker/mcp-strava` to `/runtime`. [VERIFIED: Docker inspect] | Change runtime DB path to a DuckDB file such as `/runtime/data/strava.duckdb` and rebuild/recreate container. [ASSUMED: exact filename] |
| Live service config | `/opt/docker/mcp-strava/live.env` contains `MCP_STRAVA_DB_PATH=/opt/docker/mcp-strava/data/strava.db`; `/opt/docker/mcp-strava/.env` contains Strava token keys. [VERIFIED: sanitized runtime probe] | Update DB path in live env; keep Strava token key names unchanged. |
| Live service config | Gateway config references Strava by HTTP URL only: `/opt/docker/mcp-gateway/catalog.yaml` has `strava` at `http://mcp-strava:8080/mcp`, and gateway compose includes `--servers=...,strava`. [VERIFIED: runtime grep] | No DB migration needed in gateway config; only MCP tool-list smoke must pass after surface changes. |
| OS-registered state | Docker compose labels point to `/home/j2h4u/repos/j2h4u/mcp-strava/deploy/docker-compose.yml`; container is on `mcp-backends`. [VERIFIED: Docker inspect] | Recreate compose service after config/image changes; preserve network name and service URL. |
| OS-registered state | No `mcp-strava*` systemd user/system units were found; no user crontab exists. [VERIFIED: systemctl/crontab probe] | No systemd/cron migration required. |
| Secrets/env vars | Strava credential keys remain in `/opt/docker/mcp-strava/.env`; `MCP_STRAVA_TOKEN_PATH=/runtime/.env` in container env. [VERIFIED: sanitized runtime probe] | Do not rename token env keys; migration is DB path/storage only. |
| Secrets/env vars | `MCP_STRAVA_DB_PATH` currently names a SQLite file but the key itself is storage-neutral. [VERIFIED: settings/code grep] | Prefer keeping the env var name and changing the value to the DuckDB path; update docs/tests to clarify it points to DuckDB after Phase 8. [ASSUMED] |
| Build artifacts | Local `.venv` and live container do not have `duckdb` installed; `uv.lock` has no `duckdb` entry. [VERIFIED: env probe] | Add dependency, update lock, rebuild image, and verify import in Docker Python 3.14. |
| Build artifacts | Python `__pycache__` and `.venv` artifacts exist but are untracked. [VERIFIED: filesystem/git probe] | No code migration required; rebuild/sync environment after dependency change. |

## Common Pitfalls

### Pitfall 1: Treating DuckDB Like SQLite WAL

**What goes wrong:** MCP server, refresh worker, healthcheck, and CLI each open the same `.duckdb` file as if SQLite WAL semantics still apply. [VERIFIED: current code topology]  
**Why it happens:** Current SQLite connection policy sets WAL/busy timeout and the container supervises separate `refresh` and `mcp-http` processes. [VERIFIED: `src/mcp_strava/adapters/sqlite/connection.py`] [VERIFIED: `src/mcp_strava/deploy/service.py`]  
**How to avoid:** Plan a single DuckDB-owner process, with refresh/materialization inside that process or through a DB actor; live healthcheck should not directly open DB read-write. [CITED: https://duckdb.org/docs/current/connect/concurrency]  
**Warning signs:** Docker healthcheck imports `validate_runtime_db`, CLI product commands open the DB while the service is running, or refresh worker remains a separate process after cutover. [VERIFIED: codebase grep]

### Pitfall 2: Blind SQLite Type Import

**What goes wrong:** Migration fails or silently coerces data because SQLite columns contain values outside their declared affinity. [CITED: https://duckdb.org/docs/current/core_extensions/sqlite]  
**Why it happens:** SQLite is weakly typed and the current schema stores dates and JSON as text; DuckDB enforces typed columns. [CITED: https://duckdb.org/docs/current/core_extensions/sqlite] [VERIFIED: `src/mcp_strava/adapters/sqlite/schema.py`]  
**How to avoid:** Use staging reads plus explicit `TRY_CAST`, JSON/text preservation, date parsing checks, and reject rows with failed required casts before cutover. [ASSUMED]  
**Warning signs:** `CREATE TABLE AS SELECT * FROM sqlite_scan(...)`, missing cast-failure report, or no min/max/date/null parity output. [ASSUMED]

### Pitfall 3: Views Treated As Materialized Cache

**What goes wrong:** Planner assumes views precompute aggregates and skips benchmarking. [CITED: https://duckdb.org/docs/current/sql/statements/create_view]  
**Why it happens:** "View" sounds cache-like, but DuckDB docs say a view query is run when referenced. [CITED: https://duckdb.org/docs/current/sql/statements/create_view]  
**How to avoid:** Use views for typed normalization; measure live Docker p95 before deciding if physical aggregate tables are necessary. [VERIFIED: 08-CONTEXT.md]  
**Warning signs:** New physical aggregate tables are planned before measuring view/query-builder latency. [VERIFIED: 08-CONTEXT.md]

### Pitfall 4: Registry Drift

**What goes wrong:** `get_training_aggregates` and `compare_periods` compute the same metric differently. [VERIFIED: 08-CONTEXT.md]  
**Why it happens:** Current `compare_periods_service` still has dedicated handlers over fact rows/model rows/rolling rows. [VERIFIED: `src/mcp_strava/application/metric_services.py`]  
**How to avoid:** Add aggregation semantics to `MetricDefinition` and make both tools call one aggregate service. [VERIFIED: 08-CONTEXT.md]  
**Warning signs:** `COMPARE_PERIODS_HANDLERS` grows a second aggregation map instead of being replaced by registry query specs. [VERIFIED: `tests/test_metric_registry.py`]

### Pitfall 5: 100 ms Gate Not Covering the New Tool

**What goes wrong:** Existing product tools pass latency, but `get_training_aggregates` is omitted from smoke/perf calls. [VERIFIED: `src/mcp_strava/devtools/mcp_client/client.py`]  
**Why it happens:** `EXPECTED_TOOL_NAMES` and `LATENCY_TOOL_ORDER` currently contain five tools. [VERIFIED: `src/mcp_strava/devtools/mcp_client/client.py`]  
**How to avoid:** Update tool allowlist, smoke, and `default_warm_latency_calls()` to include `get_training_aggregates`; keep `just mcp-read-model-perf` at 100 ms p95. [VERIFIED: Justfile]  
**Warning signs:** Tool surface tests still assert exactly five tools after Phase 8. [VERIFIED: `tests/test_mcp_surface.py`]

## Code Examples

Verified patterns from official sources and local constraints.

### DuckDB Connection Wrapper

```python
# Source: https://duckdb.org/docs/current/clients/python/dbapi
from pathlib import Path
import duckdb


def connect_duckdb(path: Path, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(
        database=str(path),
        read_only=read_only,
        config={"threads": 4},
    )
```

Use a persistent file connection for runtime storage; `duckdb.sql()` and bare `duckdb.connect()` are in-memory/default connection paths and should not be used for primary storage. [CITED: https://duckdb.org/docs/current/clients/python/overview] [CITED: https://duckdb.org/docs/current/clients/python/dbapi]

### Aggregate Query Skeleton

```sql
-- Source: https://duckdb.org/docs/current/sql/functions/date
-- Source: https://duckdb.org/docs/current/sql/functions/aggregates
SELECT
  time_bucket(INTERVAL '1 week', activity_day) AS bucket_start,
  time_bucket(INTERVAL '1 week', activity_day) + INTERVAL '1 week' AS bucket_end,
  sport_type,
  sum(distance_m) AS distance_m,
  sum(moving_time_s) AS moving_time_s,
  weighted_avg(avg_hr, NULLIF(heartrate_sample_count, 0)) AS avg_hr_weighted,
  quantile_cont(cardiac_cost, [0.25, 0.5, 0.75]) AS cardiac_cost_quantiles,
  count(*) AS activity_count,
  count(cardiac_cost) AS sample_size,
  count(*) FILTER (WHERE cardiac_cost IS NULL) AS null_count
FROM v_activity_aggregate_facts
WHERE activity_day >= ?::DATE
  AND activity_day < ?::DATE
GROUP BY 1, 2, sport_type
ORDER BY bucket_start, sport_type;
```

Week buckets should use DuckDB `time_bucket` because its week-width anchor is Monday; weighted averages must null out missing/zero weights instead of falling back to naive averages. [CITED: https://duckdb.org/docs/current/sql/functions/date] [CITED: https://duckdb.org/docs/current/sql/functions/aggregates] [VERIFIED: 08-CONTEXT.md]

### Registry Aggregate Spec Shape

```python
# Source: src/mcp_strava/types.py and src/mcp_strava/application/metric_registry.py
@dataclass(frozen=True)
class MetricAggregateSpec:
    metric_id: str
    aggregate_mode: str
    fact_source: str
    value_column: str | None = None
    weight_column: str | None = None
    numerator_column: str | None = None
    denominator_column: str | None = None
    category_column: str | None = None
    default_quantiles: tuple[float, ...] = (0.25, 0.5, 0.75)
    bundles: tuple[str, ...] = ()
```

This shape is recommended, not locked; the planner may choose exact names as long as registry metadata owns aggregation semantics. [ASSUMED] [VERIFIED: 08-CONTEXT.md]

### Period Comparison Over Aggregate Layer

```python
# Source: 08-CONTEXT.md D-23 through D-25
period_a = aggregate_service.query(
    start_day=period_a_start,
    end_day_exclusive=period_a_end_exclusive,
    bucket="all_time",
    metric_ids=metric_ids,
    scope=scope,
    sport_types=sport_types,
)
period_b = aggregate_service.query(
    start_day=period_b_start,
    end_day_exclusive=period_b_end_exclusive,
    bucket="all_time",
    metric_ids=metric_ids,
    scope=scope,
    sport_types=sport_types,
)
comparison = format_period_delta(period_a, period_b)
```

The service formatter should calculate deltas from two factual aggregate result sets and carry sample size, coverage, missing reasons, and metric version status through unchanged. [VERIFIED: 08-CONTEXT.md]

## Aggregate Query Layer Design

### Views First

Create views such as `v_activity_aggregate_facts`, `v_daily_aggregate_facts`, `v_training_model_state_facts`, and `v_metric_version_status` to normalize source/fact rows into typed `DATE` columns, common freshness/completeness fields, and aggregate-ready value/denominator columns. [ASSUMED] DuckDB views are cataloged queries, not physical materializations. [CITED: https://duckdb.org/docs/current/sql/statements/create_view]

### Physical Tables Only As Fallback

Do not plan physical period aggregate tables in initial waves. [VERIFIED: 08-CONTEXT.md] If Docker benchmarks show p95 above 100 ms, add a later fallback plan that creates physical aggregate facts with the same provenance fields and explicit refresh/invalidation semantics. [ASSUMED]

### Bucket Contract

Use `DATE` columns and half-open intervals for all normal buckets. [VERIFIED: 08-CONTEXT.md] Use `time_bucket(INTERVAL '1 day'|'1 week'|'1 month'|'1 year', day)` for non-`all_time` buckets; use a synthetic `all_time` bucket with the caller start or earliest mirror activity date. [CITED: https://duckdb.org/docs/current/sql/functions/date] [VERIFIED: 08-CONTEXT.md]

### Aggregation Modes

| Mode | DuckDB primitive | Required metadata |
|------|------------------|-------------------|
| `sum` | `sum(value)` | sample size, activity count, null/excluded count. [CITED: https://duckdb.org/docs/current/sql/functions/aggregates] |
| `calendar_avg` | `sum(value) / bucket_day_count` | denominator must be calendar bucket days. [VERIFIED: 08-CONTEXT.md] |
| `active_day_avg` | `sum(value) / active_day_count` | denominator must explicitly say active days. [VERIFIED: 08-CONTEXT.md] |
| `weighted_avg` | `weighted_avg(value, NULLIF(weight, 0))` | weight column and missing-denominator policy. [CITED: https://duckdb.org/docs/current/sql/functions/aggregates] [VERIFIED: 08-CONTEXT.md] |
| `ratio_of_sums` | `sum(numerator) / NULLIF(sum(denominator), 0)` | numerator and denominator columns. [VERIFIED: 08-CONTEXT.md] |
| `median_quantiles` | `quantile_cont(value, [0.25,0.5,0.75])` | sample size and low-N visibility. [CITED: https://duckdb.org/docs/current/sql/functions/aggregates] |
| `last_state` | ordered last/arg-max by day | state day and metric version status. [CITED: https://duckdb.org/docs/current/sql/functions/aggregates] [VERIFIED: 08-CONTEXT.md] |
| `distribution` | `GROUP BY category, count(*)` | categorical labels and counts, not averages. [VERIFIED: 08-CONTEXT.md] |

## SQLite to DuckDB Migration Plan Recommendations

1. Stop the Docker service and any CLI writer, then read `refresh_state` from the live SQLite DB; an active `lease_owner` or non-complete checkpoint blocks cutover. [VERIFIED: runtime probe] [VERIFIED: 08-CONTEXT.md]
2. Create a pinned pre-Phase-8 SQLite backup outside normal retention and migrate from that backup/copy, not from a changing live file. [VERIFIED: 08-CONTEXT.md]
3. Create typed DuckDB tables for all source mirror and fact tables listed in D-08; do not keep a runtime SQLite attachment after migration. [VERIFIED: 08-CONTEXT.md]
4. Use the DuckDB SQLite extension only in migration tooling; `LOAD sqlite` worked in a Docker Python 3.14 + DuckDB 1.5.3 smoke. [CITED: https://duckdb.org/docs/current/guides/database_integration/sqlite] [VERIFIED: Docker Python smoke]
5. Preserve text JSON columns as `VARCHAR` first, with optional JSON validity reports; converting to DuckDB `JSON` should be a separate explicit decision because the existing schema stores JSON strings. [VERIFIED: `src/mcp_strava/adapters/sqlite/schema.py`] [ASSUMED]
6. Convert canonical activity/fact days to `DATE`; reject required date cast failures and report nullable optional failures separately. [VERIFIED: 08-CONTEXT.md] [CITED: https://duckdb.org/docs/current/sql/data_types/date]
7. Parity-check table counts, stream point counts, GPS point coverage, channel metadata status counts, kudos counts, refresh state, dirty queue count, metric version sets, fact counts, min/max dates, and key MCP output parity. [VERIFIED: `.planning/ROADMAP.md`] [VERIFIED: 08-CONTEXT.md]
8. Switch runtime DB path to DuckDB, rebuild/recreate Docker, run MCP smoke, run `just mcp-read-model-perf samples=20 warmup=2 p95_ms=100`, and keep the SQLite backup pinned until the first accepted post-cutover refresh pass. [VERIFIED: Justfile] [VERIFIED: 08-CONTEXT.md]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SQLite primary with WAL and separate MCP/refresh processes | DuckDB primary with one read-write owner process | Phase 8 | Requires process-topology change before live runtime acceptance. [CITED: https://duckdb.org/docs/current/connect/concurrency] |
| Text `YYYY-MM-DD` slicing for date operations | Native DuckDB `DATE` plus half-open intervals and `time_bucket` | Phase 8 | Avoids brittle string filters and enables native buckets. [VERIFIED: 08-CONTEXT.md] [CITED: https://duckdb.org/docs/current/sql/functions/date] |
| `compare_periods` dedicated service logic over fact rows | Shared aggregate service called twice with `bucket=all_time` | Phase 8 | Prevents metric semantics drift. [VERIFIED: 08-CONTEXT.md] |
| Five MCP tools | Six MCP tools including `get_training_aggregates` | Phase 8 | Requires allowlist, client, smoke, docs, and latency gate updates. [VERIFIED: `src/mcp_strava/devtools/mcp_client/client.py`] [VERIFIED: 08-CONTEXT.md] |

**Deprecated/outdated for Phase 8:**
- Runtime writes to SQLite: superseded by DuckDB primary. [VERIFIED: 08-CONTEXT.md]
- Healthcheck direct DB open against live DB owner: unsafe under DuckDB process ownership. [CITED: https://duckdb.org/docs/current/connect/concurrency]
- Physical aggregate tables before benchmarks: deferred by D-09. [VERIFIED: 08-CONTEXT.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `duckdb` is recommended but marked [ASSUMED] because slopcheck was unavailable. | Standard Stack, Package Legitimacy Audit | Planner must add human verification before install. |
| A2 | Single-process owner can be implemented via in-process refresh thread or DB actor. | Architecture Patterns | Planner may need a different implementation if FastMCP lifecycle makes a thread/actor awkward. |
| A3 | Keep `MCP_STRAVA_DB_PATH` and change only its value to `.duckdb`. | Runtime State Inventory | A rename would require broader env/docs/test edits. |
| A4 | Preserve JSON as `VARCHAR` first rather than DuckDB `JSON`. | Migration Plan | If JSON type is required, migration must add validity/error handling. |
| A5 | Exact file/module names for `adapters/duckdb` and `aggregate_services.py` are recommendations. | Recommended Project Structure | Planner may choose different names if boundaries stay intact. |

## Open Questions

1. **Package legitimacy checkpoint**
   - What we know: DuckDB official docs name `duckdb`; PyPI reports 1.5.3, CPython 3.14 wheels, and source repo. [CITED: https://duckdb.org/docs/current/clients/python/overview] [VERIFIED: PyPI JSON]
   - What's unclear: Slopcheck could not run in this environment. [VERIFIED: env probe]
   - Recommendation: Planner must add `checkpoint:human-verify` before installing `duckdb`. [ASSUMED]

2. **Exact single-owner runtime topology**
   - What we know: Current container starts separate `refresh` and `mcp-http` processes; DuckDB permits one read-write process for a DB file. [VERIFIED: `src/mcp_strava/deploy/service.py`] [CITED: https://duckdb.org/docs/current/connect/concurrency]
   - What's unclear: Whether the simplest implementation is an in-process refresh thread, a DB actor queue, or moving refresh scheduling into the MCP service lifecycle. [ASSUMED]
   - Recommendation: Plan this as Wave 0 or Wave 1 architecture work before repository cutover. [ASSUMED]

3. **Physical aggregate fallback threshold**
   - What we know: Phase 8 acceptance uses 100 ms p95 and D-09 defers physical aggregates until benchmarks prove they are needed. [VERIFIED: Justfile] [VERIFIED: 08-CONTEXT.md]
   - What's unclear: Whether views plus query builders will meet 100 ms on the live 537 MB DB. [VERIFIED: runtime probe]
   - Recommendation: Benchmark before adding physical aggregate tables. [VERIFIED: 08-CONTEXT.md]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| `uv` | Python 3.14 env and lock updates | yes | 0.11.3 | none needed. [VERIFIED: env probe] |
| `uv run python` | Local Python matching project | yes | 3.14.2 | Docker Python 3.14.5. [VERIFIED: env probe] |
| `python3` | System Python | partial | 3.13.5 | Use `uv run python`; project requires >=3.14. [VERIFIED: env probe] |
| `python3.14` binary | Direct local Python 3.14 | no | none | Use `uv run python`. [VERIFIED: env probe] |
| Docker | Docker-first smoke | yes | 29.3.1 | none. [VERIFIED: env probe] |
| Docker Compose | Runtime service | yes | v5.1.1 | none. [VERIFIED: env probe] |
| `python:3.14-slim` | Docker runtime base | yes after pull | Python 3.14.5 | Existing built image also runs 3.14.5. [VERIFIED: Docker runtime probe] |
| Live Docker service | Runtime parity/smoke | yes | `mcp-strava` healthy | Stop service for cutover. [VERIFIED: Docker inspect] |
| DuckDB package | Phase 8 dependency | no in repo/live image | candidate 1.5.3 | Add dependency after human package checkpoint. [VERIFIED: env probe] |
| `ctx7` | Context7 docs fallback | no | none | Used official DuckDB docs directly. [VERIFIED: env probe] |
| `slopcheck` | Package legitimacy | no | none | Human verification checkpoint. [VERIFIED: env probe] |

**Missing dependencies with no fallback:**
- None that block research. [VERIFIED: env probe]

**Missing dependencies with fallback:**
- `slopcheck`; fallback is package install checkpoint. [VERIFIED: env probe]
- Direct `python3.14`; fallback is `uv run python` and Docker Python 3.14.5. [VERIFIED: env probe]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3. [VERIFIED: `uv run pytest --version`] |
| Config file | `pyproject.toml` with `testpaths = ["tests"]` and `pythonpath = ["src"]`. [VERIFIED: pyproject.toml] |
| Quick run command | `uv run pytest tests/test_duckdb_storage.py tests/test_training_aggregates.py tests/test_mcp_surface.py tests/test_mcp_latency_gate.py -q` after Wave 0 creates files. [ASSUMED] |
| Full suite command | `uv run pytest -q` plus Docker smoke/perf gates. [VERIFIED: pytest collect] |
| Docker smoke command | `just test`. [VERIFIED: Justfile] |
| 100 ms p95 command | `just mcp-read-model-perf samples=20 warmup=2 p95_ms=100`. [VERIFIED: Justfile] |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| P8-SC-01 | SQLite backup -> DuckDB migration preserves source rows, stream coverage, kudos, refresh state, read-model facts, metric versions. | integration | `uv run pytest tests/test_duckdb_migration.py -q` | no - Wave 0 |
| P8-SC-02 | Runtime repository/preflight/healthcheck/Docker use DuckDB primary and no runtime SQLite writes remain. | unit/integration/security | `uv run pytest tests/test_duckdb_repository.py tests/test_security_guards.py tests/test_docker_runtime.py -q` | partial - Wave 0 |
| P8-SC-03 | Aggregate layer answers day/week/month/year/all-time with sums, weighted averages, quantiles, distributions. | unit/integration | `uv run pytest tests/test_training_aggregates.py -q` | no - Wave 0 |
| P8-SC-04 | `compare_periods` delegates to aggregate layer and keeps metadata. | unit | `uv run pytest tests/test_metric_services.py::test_compare_periods_uses_aggregate_layer -q` | no - Wave 0 |
| P8-SC-05 | Docker runtime remains Python 3.14 and imports DuckDB. | smoke | `docker compose -f deploy/docker-compose.yml exec -T mcp-strava python -c "import sys, duckdb; print(sys.version, duckdb.__version__)"` | command only |
| P8-D-13 | Separate healthcheck/smoke processes do not open live DuckDB read-write. | security/integration | `uv run pytest tests/test_duckdb_concurrency_guards.py -q` | no - Wave 0 |
| P8-D-15 | MCP exposes `get_training_aggregates` and still excludes admin/raw/sql tools. | unit/smoke | `uv run pytest tests/test_mcp_surface.py -q && just mcp-list-tools` | partial - Wave 0 |
| P8-D-42 | Aggregate rows include required provenance/completeness fields. | unit | `uv run pytest tests/test_training_aggregates.py::test_aggregate_rows_include_required_metadata -q` | no - Wave 0 |

### Sampling Rate

- **Per task commit:** targeted `uv run pytest ... -q` for touched subsystem. [ASSUMED]
- **Per wave merge:** `uv run pytest -q`. [VERIFIED: pytest collect]
- **Phase gate:** `just test`, `just mcp-smoke-full`, and `just mcp-read-model-perf samples=20 warmup=2 p95_ms=100` green against Docker runtime. [VERIFIED: Justfile]

### Wave 0 Gaps

- [ ] `tests/test_duckdb_migration.py` - migration, casts, parity, rollback boundary. [ASSUMED]
- [ ] `tests/test_duckdb_repository.py` - DuckDB repository contract and no runtime SQLite writes. [ASSUMED]
- [ ] `tests/test_training_aggregates.py` - bucket/metric/bundle/metadata semantics. [ASSUMED]
- [ ] `tests/test_duckdb_concurrency_guards.py` - single-owner process, healthcheck, CLI/live DB guards. [ASSUMED]
- [ ] Update `tests/test_mcp_surface.py`, `tests/test_mcp_latency_gate.py`, and MCP client expected tool lists for six tools. [VERIFIED: codebase grep]
- [ ] Update Docker runtime tests to expect DuckDB path/import and Python 3.14. [VERIFIED: `tests/test_docker_runtime.py`]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | No user auth is introduced in this local single-user MCP phase; preserve local/container bind policy. [VERIFIED: 08-CONTEXT.md] [CITED: https://devguide.owasp.org/en/06-verification/01-guides/03-asvs/] |
| V3 Session Management | no | MCP Streamable HTTP session mechanics stay in existing MCP SDK layer; no app session store is added. [VERIFIED: `src/mcp_strava/interfaces/mcp_http.py`] |
| V4 Access Control | yes | Exact MCP tool allowlist and no raw/admin/sync/debug/SQL surface. [VERIFIED: 08-CONTEXT.md] |
| V5 Input Validation | yes | Validate dates, buckets, metric ids, bundles, scopes, sport filters, and window days before query builder dispatch. [VERIFIED: 08-CONTEXT.md] |
| V6 Cryptography | no new crypto | Keep Strava token storage behavior unchanged; do not hand-roll crypto. [VERIFIED: runtime state inventory] |
| V8 Data Protection | yes | Preserve local DB file permissions, do not print secrets, do not expose raw streams/payloads via MCP. [VERIFIED: AGENTS.md] [VERIFIED: 08-CONTEXT.md] |
| V13 API and Web Service | yes | MCP remains local/container-network safe and product parameter based. [VERIFIED: AGENTS.md] [VERIFIED: `src/mcp_strava/interfaces/mcp_http.py`] |
| V14 Configuration | yes | Runtime DB path, container bind policy, and gateway registration must be explicit and fail closed. [VERIFIED: AGENTS.md] [VERIFIED: `src/mcp_strava/deploy/preflight.py`] |

### Known Threat Patterns for DuckDB MCP Aggregates

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Raw SQL injection through metric/filter params | Tampering / Information Disclosure | No SQL parameter maps from user strings; use enum validation plus whitelisted query templates. [VERIFIED: 08-CONTEXT.md] |
| Admin surface leakage through MCP | Elevation of Privilege | Exact MCP allowlist and forbidden surface tests. [VERIFIED: `tests/test_mcp_surface.py`] |
| Live DB corruption or outage from multiple writers | Tampering / Denial of Service | One DuckDB read-write owner process; healthcheck/smoke through HTTP. [CITED: https://duckdb.org/docs/current/connect/concurrency] |
| Silent data loss during migration casts | Tampering | Cast-failure reports, row parity, coverage parity, and rollback backup pinning. [CITED: https://duckdb.org/docs/current/core_extensions/sqlite] [VERIFIED: 08-CONTEXT.md] |
| Secret exposure during migration/runtime probes | Information Disclosure | Sanitize `.env` output; never expose token state through MCP. [VERIFIED: AGENTS.md] [VERIFIED: 08-CONTEXT.md] |

## Sources

### Primary (HIGH confidence)

- `.planning/phases/08-duckdb-primary-storage-aggregate-analytics-surface/08-CONTEXT.md` - locked Phase 8 decisions D-01 through D-46. [VERIFIED: codebase read]
- `.planning/ROADMAP.md` - Phase 8 goal and success criteria. [VERIFIED: codebase read]
- `.planning/REQUIREMENTS.md` - v1/v1.1 requirements and MCP exclusions. [VERIFIED: codebase read]
- `.planning/STATE.md` - current phase routing and recent Phase 7 state. [VERIFIED: codebase read]
- `.planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md` - read-model dependency and MCP no-recompute boundary. [VERIFIED: codebase read]
- `src/mcp_strava/adapters/sqlite/schema.py`, `migrations.py`, `repository.py`, `read_model_materializer.py` - current SQLite/read-model schema and repository behavior. [VERIFIED: codebase grep]
- `src/mcp_strava/application/metric_registry.py`, `metric_services.py`, `interfaces/mcp_http.py` - current registry, compare-periods, and MCP surface. [VERIFIED: codebase grep]
- `deploy/Dockerfile`, `deploy/docker-compose.yml`, `Justfile`, `src/mcp_strava/deploy/*` - Docker/runtime and validation path. [VERIFIED: codebase grep]
- DuckDB Python overview: `https://duckdb.org/docs/current/clients/python/overview`. [CITED]
- DuckDB Python DB API: `https://duckdb.org/docs/current/clients/python/dbapi`. [CITED]
- DuckDB concurrency: `https://duckdb.org/docs/current/connect/concurrency`. [CITED]
- DuckDB date functions: `https://duckdb.org/docs/current/sql/functions/date`. [CITED]
- DuckDB aggregate functions: `https://duckdb.org/docs/current/sql/functions/aggregates`. [CITED]
- DuckDB `CREATE VIEW`: `https://duckdb.org/docs/current/sql/statements/create_view`. [CITED]
- DuckDB SQLite import and SQLite extension: `https://duckdb.org/docs/current/guides/database_integration/sqlite`, `https://duckdb.org/docs/current/core_extensions/sqlite`. [CITED]
- PyPI JSON for `duckdb` package metadata and files. [VERIFIED: PyPI JSON]
- Live runtime probes of `/opt/docker/mcp-strava`, Docker inspect, and SQLite read-only counts. [VERIFIED: runtime probe]

### Secondary (MEDIUM confidence)

- OWASP Developer Guide ASVS category list: `https://devguide.owasp.org/en/06-verification/01-guides/03-asvs/`. [CITED]
- Docker Python image probe for `python:3.14-slim` resolving to Python 3.14.5. [VERIFIED: Docker runtime probe]

### Tertiary (LOW confidence)

- Exact future file/module names and aggregate spec dataclass fields are recommendations only. [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - `duckdb` is confirmed by official docs and PyPI/Docker probes, but slopcheck was unavailable so package installation must be human-gated. [VERIFIED: PyPI JSON] [ASSUMED]
- Architecture: HIGH - DuckDB concurrency docs and current code topology clearly imply a single-owner process change. [CITED: https://duckdb.org/docs/current/connect/concurrency] [VERIFIED: codebase grep]
- Migration: HIGH - SQLite typing hazards, current schema, and parity requirements are explicit. [CITED: https://duckdb.org/docs/current/core_extensions/sqlite] [VERIFIED: codebase grep]
- Aggregate semantics: HIGH - D-32 through D-44 lock semantics and DuckDB docs verify needed primitives. [VERIFIED: 08-CONTEXT.md] [CITED: https://duckdb.org/docs/current/sql/functions/aggregates]
- Validation: HIGH - existing pytest/Docker/MCP latency infrastructure is present; Wave 0 gaps are identifiable. [VERIFIED: pytest collect] [VERIFIED: Justfile]

**Research date:** 2026-05-25
**Valid until:** 2026-06-24 for codebase architecture; 2026-06-01 for package/version claims because DuckDB and Python Docker tags can change. [ASSUMED]
