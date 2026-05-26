---
quick_id: 260526-lal
slug: centralize-materialized-analytic-fact-re
status: completed
created_at: "2026-05-26T10:19:54+05:00"
---

# Quick Task: Centralize Materialized Analytic Fact Registry

## Goal

Make the metric registry the source of truth for materialized analytic fact columns and rolling read-model windows, with tests that fail when schema/query columns drift outside the registry.

## Scope

- Add a compact materialized fact column registry near the metric registry.
- Derive DuckDB aggregate query column allowlist from that registry instead of a private duplicate set.
- Centralize materialized rolling window days and use them from both DuckDB and SQLite materializers.
- Add focused tests that compare DuckDB read-model schema columns to the registry.

## Acceptance Criteria

- Every DuckDB read-model fact-table column is registered as metric, dependency, dimension, or provenance.
- Aggregate query columns are registry-derived and still reject unknown columns.
- Materialized rolling windows match the central registry.
- Focused tests and full test suite pass.
