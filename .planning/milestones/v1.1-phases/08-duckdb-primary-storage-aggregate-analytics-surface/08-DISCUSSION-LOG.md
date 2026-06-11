# Phase 8: DuckDB Primary Storage & Aggregate Analytics Surface - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-25
**Phase:** 08-duckdb-primary-storage-aggregate-analytics-surface
**Areas discussed:** Cutover policy, Agent-facing aggregate MCP surface, Aggregation semantics, Granularity and filters

---

## Cutover Policy

| Option | Description | Selected |
|--------|-------------|----------|
| Fast one-shot cutover | Back up SQLite, migrate from a stable copy, parity-check DuckDB, switch runtime, and keep rollback backup. | yes |
| Shadow/dual validation | Keep SQLite and DuckDB running side by side longer before primary replacement. | |

**User's choice:** Fast cutover.
**Notes:** The project has no requirement to preserve intermediate operability while refactoring, but live Strava mirror data must be protected.

---

## Agent-Facing Aggregate MCP Surface

| Option | Description | Selected |
|--------|-------------|----------|
| One constrained generic aggregate tool | Add one agent-facing aggregate tool backed by registry-defined metrics and safe parameters. | yes |
| Multiple specialized aggregate tools | Add several dedicated tools for weekly/monthly/trend use cases. | |
| Extend existing tools only | Avoid a new tool and stretch `compare_periods` or existing tools. | |

**User's choice:** Tool design should start from user/agent scenarios, not the old CLI. The new tool name is `get_training_aggregates`.
**Notes:** Expert panel recommended keeping existing MCP tools and adding one generic aggregate tool. The tool should be product-facing, not SQL-flavored.

---

## Aggregation Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Decide inline | Pick aggregation semantics during the discussion without specialist review. | |
| Profile expert panel | Use specialists for sports metric semantics and SQL aggregation behavior. | yes |

**User's choice:** Use a profile expert panel.
**Notes:** Panel recommendation: registry-driven defaults, weighted averages for HR/watts, medians/quantiles for efficiency metrics, last-known values for model state, distributions for categorical facts, and complete denominator/coverage metadata.

---

## Granularity and Filters

| Option | Description | Selected |
|--------|-------------|----------|
| Decide inline | Pick bucket and filter contract during the discussion without specialist review. | |
| Profile expert panel | Use specialists for bucket/filter contract and DuckDB query layer shape. | yes |

**User's choice:** Use a profile expert panel; no gear filter or grouping for Phase 8.
**Notes:** Panel recommendation: day/week/month/year/all-time buckets, Monday week starts, half-open date ranges, global/per-sport/both scopes from the metric registry, and rolling windows for 7/14/28/42/90 days.

---

## the agent's Discretion

- Exact DuckDB table/view/repository names.
- Exact JSON field spelling for aggregate responses.
- Exact metric bundle names, as long as bundles are registry-defined.
- Exact migration command names and fixture shapes.
- Whether existing `rolling_period_facts` remains as a migrated fact source or becomes redundant after the DuckDB aggregate layer is accepted.

## Deferred Ideas

- Gear/equipment aggregation and filtering.
- Physical period aggregate tables unless benchmark evidence proves they are needed.
- Permanent SQLite plus DuckDB dual-primary, CDC, Parquet/lakehouse layering, raw SQL MCP, or admin/debug MCP surfaces.
