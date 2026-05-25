# Phase 08 Source Coverage Audit

SOURCE | ID | Feature / Requirement | Plan | Status | Notes
--- | --- | --- | --- | --- | ---
GOAL | ROADMAP | DuckDB primary mirror plus aggregate analytics surface | 08-02, 08-03, 08-04, 08-06, 08-07, 08-08 | COVERED | Migration, primary runtime, aggregate queries, MCP surface, and Docker validation are planned.
REQ | P8-SC-01 | Back up, migrate, and parity-check SQLite mirror into DuckDB | 08-02, 08-08 | COVERED | Includes pinned backup, lease gate, casts, parity, rollback, and final live evidence.
REQ | P8-SC-02 | Runtime repository, refresh, migration, preflight, healthcheck, Docker, and CLI use DuckDB primary | 08-03, 08-04, 08-08 | COVERED | Includes repository cutover and single-owner runtime topology.
REQ | P8-SC-03 | DuckDB bucketed aggregate queries | 08-05, 08-06, 08-07, 08-08 | COVERED | Registry semantics, query builders, service, MCP smoke/perf.
REQ | P8-SC-04 | `compare_periods` uses aggregate layer | 08-05, 08-07, 08-08 | COVERED | Comparison delegates to aggregate layer twice with `bucket=all_time`.
REQ | P8-SC-05 | Python 3.14 and Docker DuckDB runtime | 08-01, 08-08 | COVERED | Dependency gate and Docker import smoke.
RESEARCH | R-01 | Human package-legitimacy checkpoint before installing `duckdb` | 08-01 | COVERED | Blocking checkpoint before package metadata edits.
RESEARCH | R-02 | DuckDB single read-write owner topology | 08-04, 08-08 | COVERED | Healthcheck/smoke through owner/HTTP path.
RESEARCH | R-03 | Migration-only SQLite import with controlled casts | 08-02 | COVERED | No runtime SQLite bridge.
RESEARCH | R-04 | Views/query builders before physical aggregate tables | 08-06 | COVERED | Physical period aggregate tables are not planned.
RESEARCH | R-05 | 100 ms p95 Docker acceptance gate | 08-08 | COVERED | Six-tool p95 gate.
RESEARCH | R-06 | Security controls for raw SQL/admin leakage, data loss, concurrency, dependency, and secrets | 08-01 through 08-08 | COVERED | Threat models included in every plan.
CONTEXT | D-01 | Fast one-shot cutover | 08-02 | COVERED | Migration-only, no dual-primary.
CONTEXT | D-02 | Backup, parity, Docker/MCP smoke, p95 before acceptance | 08-02, 08-08 | COVERED | Final validation checkpoint.
CONTEXT | D-03 | Stop/quiesce writers and prove no active lease | 08-02, 08-04, 08-08 | COVERED | Lease blocks cutover.
CONTEXT | D-04 | Runtime paths use DuckDB primary | 08-03, 08-04 | COVERED | Repository and deploy refit.
CONTEXT | D-05 | Keep pinned SQLite backup | 08-02, 08-08 | COVERED | Backup retention through first accepted refresh pass.
CONTEXT | D-06 | Rollback via pinned SQLite and previous runtime, no full resync | 08-02, 08-08 | COVERED | Runbook and checkpoint.
CONTEXT | D-07 | DuckDB primary, no permanent bridge/dual-primary | 08-02, 08-03 | COVERED | Guards and runtime cutover.
CONTEXT | D-08 | Preserve physical source and fact tables | 08-02, 08-03 | COVERED | DuckDB schema and repository.
CONTEXT | D-09 | No permanent period aggregate tables initially | 08-06 | COVERED | Views/query builders only.
CONTEXT | D-10 | Use DuckDB views for aggregate-ready facts | 08-06 | COVERED | View inventory.
CONTEXT | D-11 | No expensive domain recompute in MCP calls | 08-06, 08-07 | COVERED | Prepared facts only.
CONTEXT | D-12 | DATE days and half-open intervals | 08-02, 08-06 | COVERED | Casts and query contract.
CONTEXT | D-13 | DuckDB concurrency single owner | 08-03, 08-04, 08-08 | COVERED | Owner-process topology.
CONTEXT | D-14 | Controlled casts from weak SQLite types | 08-02 | COVERED | Cast-failure reports.
CONTEXT | D-15 | Add `get_training_aggregates` | 08-07 | COVERED | One new tool.
CONTEXT | D-16 | Keep existing five tools | 08-07, 08-08 | COVERED | Exact six-tool allowlist.
CONTEXT | D-17 | Scenario-oriented aggregate tool | 08-05, 08-07 | COVERED | Registry bundles and MCP tool.
CONTEXT | D-18 | Product-level aggregate parameters | 08-06, 08-07 | COVERED | Validation before query layer.
CONTEXT | D-19 | Registry-defined bundles | 08-05, 08-06, 08-07 | COVERED | No handler-built bundles.
CONTEXT | D-20 | No gear aggregation/filtering | 08-05, 08-06, 08-07 | COVERED | Explicit rejection tests.
CONTEXT | D-21 | No raw/admin/sync/debug/storage MCP surface | 08-07, 08-08 | COVERED | Allowlist and forbidden schema tests.
CONTEXT | D-22 | Factual aggregate responses | 08-06, 08-07 | COVERED | No coaching language.
CONTEXT | D-23 | `compare_periods` over aggregate layer | 08-07 | COVERED | Delegation tests.
CONTEXT | D-24 | Two `bucket=all_time` calls for comparison | 08-07 | COVERED | Spy/fake tests.
CONTEXT | D-25 | Remove separate row-scan comparison path | 08-07 | COVERED | Rewrite task.
CONTEXT | D-26 | Supported buckets | 08-06 | COVERED | day/week/month/year/all_time tests.
CONTEXT | D-27 | Monday week buckets | 08-06 | COVERED | `time_bucket` tests.
CONTEXT | D-28 | All-time earliest activity default | 08-06 | COVERED | All-time tests.
CONTEXT | D-29 | Global/per-sport scopes from registry | 08-05, 08-06 | COVERED | Registry and query validation.
CONTEXT | D-30 | Rolling windows whitelist | 08-05, 08-06 | COVERED | 7/14/28/42/90.
CONTEXT | D-31 | Gear unsupported | 08-05, 08-06, 08-07 | COVERED | Rejection tests.
CONTEXT | D-32 | Aggregation semantics in registry | 08-05 | COVERED | MetricDefinition fields.
CONTEXT | D-33 | Volume/load sum | 08-05, 08-06 | COVERED | Registry and query tests.
CONTEXT | D-34 | Daily averages denominator | 08-05, 08-06 | COVERED | Calendar/active-day denominator metadata.
CONTEXT | D-35 | Weighted HR/power averages | 08-05, 08-06 | COVERED | Weight metadata and missing-denominator tests.
CONTEXT | D-36 | Pace/speed ratio of sums | 08-05, 08-06 | COVERED | Ratio metadata.
CONTEXT | D-37 | Median plus distribution for skewed metrics | 08-05, 08-06 | COVERED | Quantile metadata.
CONTEXT | D-38 | p25/median/p75 and sample size | 08-05, 08-06 | COVERED | Quantile tests.
CONTEXT | D-39 | Model-state last-known state | 08-05, 08-06 | COVERED | Last-state mode.
CONTEXT | D-40 | Categorical distributions/counts | 08-05, 08-06 | COVERED | Distribution mode.
CONTEXT | D-41 | Kudos aggregate counts, no names | 08-05, 08-06 | COVERED | Response exclusion tests.
CONTEXT | D-42 | Aggregate row fields | 08-06, 08-07 | COVERED | Exact key tests.
CONTEXT | D-43 | Coverage and missing denominators explicit | 08-06 | COVERED | HR/watts/stream/GPS tests.
CONTEXT | D-44 | Mixed metric versions degraded/reported | 08-05, 08-06, 08-07 | COVERED | Version-status tests.
CONTEXT | D-45 | Use expert/research lenses for hard technical choices | 08-01 | COVERED | Research and pattern map are execution context.
CONTEXT | D-46 | Ask only product/business questions not answerable from context | 08-01 | COVERED | No new questions in plans beyond required package/live verification.

Deferred CONTEXT ideas are excluded: gear/equipment aggregation, physical period aggregate tables without benchmark evidence, permanent raw archive/Parquet/lakehouse/CDC/multi-user storage, and training-model redesign/coaching interpretation.
