---
phase: 11-tidy-materializer-repository-access-replace-the-6-inline-sql
reviewed: 2026-05-30T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - src/mcp_strava/adapters/duckdb/repository.py
  - src/mcp_strava/adapters/duckdb/read_model_materializer.py
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-05-30T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Phase 11 is a no-behavior-change refactor closing Phase 10 finding IN-03: six inline SQL
queries that reached into the private `repo._fetchone` / `repo._fetchall` API from
`read_model_materializer.py` were relocated into six new public methods on
`DuckDBRepository`.

I traced each of the six relocated queries against its original (diff `d9f614a^..HEAD`)
and verified byte-level equivalence on the three dimensions that would constitute a
behavior change — **SQL text, parameter order, and parameter types**:

| New method | SQL text | Params | Verdict |
|---|---|---|---|
| `stream_counts_for_activity` | identical (incl. the original's non-method-level indentation) | `[activity_id]` | verbatim |
| `zone_seconds_for_activity` | identical | `[b[0], b[0], b[1], b[1], b[2], b[2], b[3], b[-2], activity_id]` | verbatim |
| `daily_fact_sums` | identical | `[activity_day, metric_version]` (caller passes `point.date`) | verbatim |
| `rolling_load_aggregate` | identical | `[start, as_of_day, metric_version]` | verbatim |
| `training_model_row` | identical | `[as_of_day, metric_version]` | verbatim |
| `rolling_cardiac_metric_rows` | identical | `[start, as_of_day, metric_version]` | verbatim |

No SQL drift, no parameter reordering, no type changes. The boundary is fully closed:
`rg` confirms **no source file outside `repository.py` references `_fetchone`/`_fetchall`**.
The remaining `repo.conn.commit()` / `repo.conn.rollback()` in `_record_failed_run`
(materializer lines 374, 376) are pre-existing, untouched by this diff, and outside the
scope of the 6-query relocation. The diff is clean (116 added / 78 deleted) with no stray
edits, across exactly the two stated commits.

**No BLOCKER-tier defects found.** The findings below are quality/maintainability
observations that do not affect correctness.

## Warnings

### WR-01: New aggregate accessors typed `dict | None` but every caller dereferences unconditionally

**File:** `src/mcp_strava/adapters/duckdb/repository.py:1399`, `:1419`, `:1447`
**Issue:** `daily_fact_sums`, `rolling_load_aggregate`, and `training_model_row` are
annotated `-> dict[str, object] | None`, but their callers index the result without a
None-guard:
- `_materialize_daily_facts` (materializer:252-258): `sums["distance_m"]`, `sums["zone4_seconds"]`, ...
- `_materialize_rolling_facts` (materializer:333-342): `row["activity_count"]`, `row["observed_trimp"]`, ...

If any of these ever returned `None`, the materializer would raise `TypeError: 'NoneType'
object is not subscriptable` and the run would roll back. In practice this is **safe today**
— all three are `SELECT SUM(...)/COUNT(...)` with no `GROUP BY`, so DuckDB always returns
exactly one row and `_fetchone` never yields `None`. `training_model_row` is the only one
that *could* miss (it filters on a specific `day`), but its caller already guards with the
`model[...] if model else None` pattern (materializer:343-348), so its `| None` is honestly
typed and handled. The mismatch is therefore latent, not active, and **identical to the
pre-refactor behavior** — the old inline `repo._fetchone(...)` calls had the same shape and
the same unconditional indexing — so this is not a regression introduced by Phase 11.

Flagging as a WARNING because the refactor was the moment to tighten the contract: the two
always-single-row aggregates (`daily_fact_sums`, `rolling_load_aggregate`) advertise a
`None` that their callers neither expect nor handle, which invites a future caller to skip
the guard.

**Fix:** Either narrow the return type to `dict[str, object]` for the two aggregate methods
that are guaranteed to return a row (and document the single-row invariant), or have callers
guard explicitly. Lowest-risk option that preserves behavior exactly:
```python
def daily_fact_sums(self, activity_day: str, metric_version: int) -> dict[str, object]:
    """... A no-GROUP-BY aggregate always returns exactly one row."""
    row = self._fetchone(... )
    assert row is not None  # SUM/COUNT with no GROUP BY always yields one row
    return row
```
Apply the same to `rolling_load_aggregate`. Leave `training_model_row` as `| None` (its
caller correctly handles the miss).

## Info

### IN-01: `_stream_counts` / `_zone_seconds` are now thin pass-through wrappers

**File:** `src/mcp_strava/adapters/duckdb/read_model_materializer.py:42`, `:46`
**Issue:** After the relocation, these two module-level helpers are one-line delegations:
`_stream_counts` returns `repo.stream_counts_for_activity(activity_id)` and `_zone_seconds`
returns `repo.zone_seconds_for_activity(activity_id, bounds)`. They no longer hold any
logic — the unwrapping/`int(... or 0)` and the `tuple(...)` comprehension all moved into the
repository methods. Each has a single caller (`_activity_fact`, lines 110 and 132). They now
add an indirection layer without earning it.
**Fix:** Optional. Inline the two calls at the call sites and delete the wrappers, or keep
them if you prefer a stable internal seam for future test stubbing. The `_zone_seconds`
docstring would need to move or be dropped if inlined. No behavior impact either way.

### IN-02: Verbatim-relocated SQL carries non-conventional indentation into repository.py

**File:** `src/mcp_strava/adapters/duckdb/repository.py:1366-1372`, `:1385-1394`
**Issue:** The `stream_counts_for_activity` and `zone_seconds_for_activity` SQL bodies are
indented flush-left relative to the surrounding method (the `SELECT` sits at column 9, not
aligned under the triple-quote the way every other query in this file is — compare
`daily_fact_sums` at :1405 onward, which is correctly indented). This indentation was copied
verbatim from the materializer originals (intentionally, to keep the change a pure move), so
it is faithful — but it now sits inconsistently against its new neighbors in `repository.py`.
**Fix:** Optional whitespace-only reflow to match the file's prevailing query indentation.
SQL is whitespace-insensitive here, so this is byte-irrelevant to results — purely
readability. Defer if you want to keep this commit a provably pure relocation.

### IN-03: `zone_seconds_for_activity` return value is a plain tuple, not the annotated fixed-arity tuple

**File:** `src/mcp_strava/adapters/duckdb/repository.py:1377`, `:1397`
**Issue:** The signature promises `tuple[int, int, int, int, int]`, but the body returns
`tuple(int(row[f"z{idx}"] or 0) for idx in range(1, 6))` — a runtime `tuple` of length 5
that a type checker sees as `tuple[int, ...]`, not the fixed 5-element form. A static checker
(mypy/pyright) may flag the return as not matching the declared arity. Behaviorally correct
(always 5 elements) and identical to the pre-refactor expression.
**Fix:** Optional. Return an explicit 5-tuple for checker-friendliness:
```python
z = [int(row[f"z{idx}"] or 0) for idx in range(1, 6)]
return z[0], z[1], z[2], z[3], z[4]
```
or annotate the method `# type: ignore[return-value]` if the generator form is preferred.

---

_Reviewed: 2026-05-30T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
