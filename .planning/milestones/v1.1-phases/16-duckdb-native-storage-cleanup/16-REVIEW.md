---
phase: 16-duckdb-native-storage-cleanup
reviewed: 2026-06-11T09:15:00Z
depth: standard
files_reviewed: 26
files_reviewed_list:
  - src/mcp_strava/adapters/duckdb/activity_lookup_queries.py
  - src/mcp_strava/adapters/duckdb/activity_rows.py
  - src/mcp_strava/adapters/duckdb/activity_selectors.py
  - src/mcp_strava/adapters/duckdb/aggregate_queries.py
  - src/mcp_strava/adapters/duckdb/aggregate_rows.py
  - src/mcp_strava/adapters/duckdb/kudos_store.py
  - src/mcp_strava/adapters/duckdb/read_model_activity_facts.py
  - src/mcp_strava/adapters/duckdb/read_model_materializer_utils.py
  - src/mcp_strava/adapters/duckdb/read_model_period_facts.py
  - src/mcp_strava/adapters/duckdb/read_model_repository.py
  - src/mcp_strava/adapters/duckdb/read_model_source_repository.py
  - src/mcp_strava/adapters/duckdb/refresh_state_store.py
  - src/mcp_strava/adapters/duckdb/repository.py
  - src/mcp_strava/adapters/duckdb/schema_tables.py
  - src/mcp_strava/adapters/duckdb/schema_views.py
  - src/mcp_strava/adapters/duckdb/status_fact_queries.py
  - src/mcp_strava/adapters/duckdb/stream_coverage_queries.py
  - src/mcp_strava/adapters/duckdb/stream_write_repository.py
  - src/mcp_strava/application/freshness.py
  - src/mcp_strava/metric_registry_fact_column_sql.py
  - src/mcp_strava/refresh/freshness.py
  - src/mcp_strava/types_repository.py
  - tests/test_duckdb_repository.py
  - tests/test_metric_registry.py
  - tests/test_read_model_queries.py
  - tests/test_refresh_runtime.py
findings:
  critical: 3
  warning: 5
  info: 2
  total: 10
status: resolved
remediated: 2026-06-11T10:30:00Z
remediation_commit: 85dab88
---

# Phase 16: Code Review Report

**Reviewed:** 2026-06-11T09:15:00Z
**Depth:** standard
**Files Reviewed:** 26
**Status:** resolved (see Remediation below)

## Remediation (2026-06-11, commit 85dab88)

Each finding was re-verified against the codebase before acting (reviewer findings
treated as leads, not facts). The "3 criticals" did not hold as runtime blockers —
the suite was green throughout (`just check` clean, 429→427 tests after deleting
two backward-compat tests). Disposition:

| ID | Verdict | Action |
|----|---------|--------|
| CR-01 | Overstated → fixed | Stale dataclass annotations on **never-instantiated** `*Fact` types; not a runtime bug. Aligned `missing_reasons_json` → `list[str]`, `cardiac_drift_significant` → `bool`. |
| CR-02 | Out of scope | Pre-existing SELECT-then-DELETE on a single-writer DB; not a phase-16 regression. Left as backlog. |
| CR-03 | Real → fixed | Removed the `requested_at` `or`-fallback shim; param now required (fail-fast). |
| WR-01 | Rejected | `str(row["activity_day"])` is the **deliberate** repo-boundary ISO-string contract (column is native DATE), not a dead shim. |
| WR-02 | Real → fixed | Removed dead `ALTER TABLE ADD COLUMN IF NOT EXISTS` migration + its two backward-compat tests. |
| WR-03 | Real → fixed | Removed dead `str(value)[:10]` parse in `_coerce_day`. |
| WR-04 | Rejected | Assembler inlines internal `date.isoformat()` fragments by design; zero injection surface; isolated param-threading would be fragile. |
| WR-05 | Out of scope | Pre-existing `MAX(id)+1` on a single-writer DB; backlog. |
| IN-01/02 | Fixed | Folded into CR-01 + fixture `0` → `False`. |

## Summary

Phase 16 converts the DuckDB storage layer from legacy SQLite-era VARCHAR/BIGINT
representations to native DuckDB types (DATE, BOOLEAN, VARCHAR[]) and removes
no-op CASTs. The migration is structurally sound and the new schema DDL is
correct. However, three correctness bugs survived the cleanup: a compat shim that
silently swallows the newly-native `missing_reasons_json` VARCHAR[] type instead
of binding it as-is; a type mismatch between the domain dataclass (still uses
`str = "[]"`) and the column (now `VARCHAR[]`); and a race condition in the
`clear_dirty_activity_rows` helper that performs an extra SELECT before each
DELETE (not just redundant, but incorrect under concurrent writers). Three
warnings cover an `enqueue_refresh_request` type union that keeps legacy
`str | date` inputs alive, an `isinstance`-shim for `date` objects that should
have been removed with the DATE column promotion, and a `_ensure_column_last_full_summary_sync_at`
DDL migration that was explicitly called out as dead code in project policy.

---

## Critical Issues

### CR-01: `missing_reasons_json` VARCHAR[] binding path is broken — legacy `str` still routed as JSON string

**File:** `src/mcp_strava/adapters/duckdb/read_model_activity_facts.py:164` and
`src/mcp_strava/adapters/duckdb/read_model_materializer_utils.py:19-20`

**Issue:** `_json_list(missing)` returns a plain Python `list[str]`, which is
correct for binding into a `VARCHAR[]` column — DuckDB accepts a Python list
directly. However, in `tests/test_duckdb_repository.py:51` and
`tests/test_read_model_queries.py:152-153` the test fixtures still pass
`"missing_reasons_json": "[]"` (a raw JSON string) to the upsert helpers
(`upsert_activity_metric_fact`, `upsert_daily_load_fact`, etc.). The upsert
helpers (`read_model_fact_write_repository.py`, not in scope but called from
tests) must accept and bind whatever value they receive. If those helpers pass
the string `"[]"` directly to DuckDB as the VARCHAR[] parameter, DuckDB will
coerce it or raise at runtime — the schema now expects a native array, not a
JSON string.

More critically, `types_repository.py:48` still declares
`missing_reasons_json: str = "[]"` in `ActivityMetricFact` (and lines 90, 114,
140 in `DailyLoadFact`, `TrainingModelDailyFact`, `RollingPeriodFact`). This
means any code path that constructs one of these domain objects and then passes
`.missing_reasons_json` into a SQL bind will pass the string `"[]"` — not a
Python `list` — into the `VARCHAR[]` column. DuckDB may or may not coerce this;
whether it silently accepts `"[]"` as a one-element array `["[]"]` or raises
depends on the DuckDB version and cast mode. Either behaviour is wrong.

**Fix:** Update all four domain dataclasses in `types_repository.py` to use
`list[str]` as the type and `field(default_factory=list)` as the default:

```python
# types_repository.py
from dataclasses import dataclass, field

@dataclass
class ActivityMetricFact:
    ...
    missing_reasons_json: list[str] = field(default_factory=list)
    ...

@dataclass
class DailyLoadFact:
    ...
    missing_reasons_json: list[str] = field(default_factory=list)
    ...
```

Then update the test fixtures to pass `[]` instead of `"[]"`:

```python
# test_duckdb_repository.py, test_read_model_queries.py
"missing_reasons_json": [],
```

---

### CR-02: `clear_dirty_activity_rows` has a TOCTOU race — check-then-delete is not atomic

**File:** `src/mcp_strava/adapters/duckdb/read_model_source_repository.py:278-295`

**Issue:** The method does `SELECT 1 ... WHERE ...` then immediately
`DELETE ... WHERE ...` for every row, using the presence/absence of the
SELECT result to decide the return count. This is a check-then-act pattern
without holding a transaction across the pair. Between the SELECT and the DELETE
another writer (or a concurrent materialization batch) can delete the same row,
causing the DELETE to silently affect 0 rows while the SELECT said 1 — the count
is then wrong. The method is called after materialization to report the number of
rows cleared, and the caller uses this count for telemetry and run records.

There is a subtler bug: the SELECT and DELETE are issued via `self._execute` /
`self._fetchone`, which acquire the process lock independently when
`_transaction_depth == 0`. The outer call loop does not begin a transaction, so
each pair of operations runs outside any transaction scope.

**Fix:** Either open a transaction over the entire loop, or — simpler and
correct — drop the SELECT entirely and count `rowcount` on the DELETE result (DuckDB
`execute()` returns a relation whose `rowcount` attribute is set for DML):

```python
def clear_dirty_activity_rows(self, rows: Iterable[DirtyActivityRow]) -> int:
    count = 0
    for row in rows:
        activity_id = _as_int(row["activity_id"])
        activity_day = _as_str(row["activity_day"])
        metric_version = _as_int(row["metric_version"])
        result = self._execute(
            """
            DELETE FROM metric_dirty_activities
            WHERE activity_id = ? AND activity_day = CAST(? AS DATE) AND metric_version = ?
            """,
            [activity_id, activity_day, metric_version],
        )
        # DuckDB relation.rowcount is set for DML statements
        if hasattr(result, "rowcount") and result.rowcount:
            count += result.rowcount
        else:
            # fallback: treat as 1 if DELETE was issued (pre-rowcount DuckDB versions)
            count += 1
    return count
```

---

### CR-03: `enqueue_refresh_request` `timestamp` fallback silently binds a `date` object into a VARCHAR column

**File:** `src/mcp_strava/adapters/duckdb/refresh_state_store.py:200`

**Issue:**

```python
timestamp = requested_at or requested_for_day
```

When `requested_at` is `None`, `timestamp` becomes a `datetime.date` object.
It is then passed as the `requested_at` column value (VARCHAR in the schema, line
98 of `schema_tables.py`). DuckDB will implicitly stringify a date to `"YYYY-MM-DD"`,
so the stored value loses sub-day precision and is technically not an ISO instant.

More importantly, this is a legacy `str | date` union that the project policy
explicitly prohibits ("accept both formats" shims). The ONLY caller that passes
`requested_at=None` is `build_freshness_metadata` in
`application/freshness.py:102` which passes `now.isoformat()` as `requested_at`
— it never passes `None`. The `requested_for_day`-as-fallback branch exists only
as dead shim code.

**Fix:** Remove the fallback. Require `requested_at` to be a non-optional `str`:

```python
def enqueue_refresh_request(
    self, reason: str, requested_for_day: datetime.date, requested_at: str
) -> bool:
    ...
    self._execute(
        """
        INSERT INTO refresh_requests (id, reason, requested_for_day, requested_at)
        VALUES (?, ?, ?, ?)
        """,
        [self._next_id("refresh_requests"), reason, requested_for_day, requested_at],
    )
```

Update all callers to pass `now.isoformat()` explicitly (they already do).

---

## Warnings

### WR-01: `activity_day` read back as `str(row["activity_day"])` — dead decode path survives the DATE conversion

**File:** `src/mcp_strava/adapters/duckdb/activity_rows.py:12`

**Issue:** `activity_day=str(row["activity_day"])` performs a runtime `str()`
call on every row. After the phase-16 conversion `activity_day` is a native
DuckDB `DATE` column, so `row["activity_day"]` comes back as a Python
`datetime.date` object (after passing through `normalize_cell`). The `str()`
call on a `date` object returns `"YYYY-MM-DD"` — the right string — but this is
now a type-coercion shim: `str(date(2026, 5, 21))` == `"2026-05-21"`. The
identical pattern is present at `activity_lookup_queries.py:79`,
`read_model_source_repository.py:85`, and `read_model_period_facts.py` (multiple
`str(row["..."])` call-sites on DATE-typed columns).

This is a mild quality issue — the output is always correct — but it is exactly
the kind of "dead decode path" the phase set out to remove. A type-aware project
should either use `date.isoformat()` explicitly (to document intent) or, better,
expose the `date` object directly in `RepositoryActivityRow` and let consumers
call `.isoformat()` where they need a string.

**Fix:** In `activity_rows.py`, replace:
```python
activity_day=str(row["activity_day"]),
```
with the explicit isoformat call to document intent:
```python
activity_day=row["activity_day"].isoformat() if isinstance(row["activity_day"], date) else str(row["activity_day"]),
```
Or, cleaner for a post-DATE-column world: change `RepositoryActivityRow.activity_day`
from `str` to `date` and push the `isoformat()` call to display boundaries only.

---

### WR-02: `_ensure_column_last_full_summary_sync_at` is a schema migration shim kept alive in production code

**File:** `src/mcp_strava/adapters/duckdb/refresh_state_store.py:35-37`

**Issue:**

```python
def _ensure_column_last_full_summary_sync_at(self) -> None:
    with duckdb_process_lock():
        self.conn.execute("ALTER TABLE refresh_state ADD COLUMN IF NOT EXISTS last_full_summary_sync_at VARCHAR")
```

This is a one-shot schema migration that has been baked into every construction
of `RefreshStateStore`. The column `last_full_summary_sync_at` is now part of
the canonical DDL in `schema_tables.py:90`, so the `ALTER TABLE ... ADD COLUMN IF
NOT EXISTS` on every startup is dead-migration shim code. Project policy is
explicit: "A removed key hitting new code SHOULD raise (fail-fast) — that is
correct, not a regression" and "Разовая миграция сделана — её код мёртв, удали."

On a fresh DB this executes a no-op DDL on every `RefreshStateStore.from_connection()`
call. The `IF NOT EXISTS` guard prevents a crash but the call is still wasted
work and silently masks the intended "schema should be complete at creation"
invariant.

**Fix:** Remove `_ensure_column_last_full_summary_sync_at` and its call from
`from_connection`. The column is in the DDL; any DB missing it should fail loudly
(it's old), not be silently patched.

---

### WR-03: `_coerce_day` in `status_fact_queries.py` is a dual-format compat shim for DATE column values

**File:** `src/mcp_strava/adapters/duckdb/status_fact_queries.py:430-436`

**Issue:**

```python
def _coerce_day(value: object) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
```

After the phase-16 DATE column promotion, `activity_day` values from
`activity_metric_facts` are always `datetime.date` objects (DuckDB returns
Python `date` for DATE columns). The `str(value)[:10]` fallback branch — which
handled legacy VARCHAR `"YYYY-MM-DD"` values — is now unreachable dead code for
any column that has been migrated. The `isinstance(value, date)` check is also a
compat shim: there is no longer any path where a DATE column cell arrives as a
non-`date` Python type after `normalize_cell`.

This pattern was acceptable before the migration; post-migration it is dead code
that should be removed to signal that the type is settled.

**Fix:** Since `activity_day` from the DATE column is always `datetime.date`,
remove the fallback:

```python
def _coerce_day(value: object) -> date | None:
    if isinstance(value, date):
        return value
    return None  # or raise TypeError — a non-date here is a programming error
```

---

### WR-04: `aggregate_queries.py` inlines un-sanitised date literals directly into SQL strings

**File:** `src/mcp_strava/adapters/duckdb/aggregate_queries.py:308-313`

**Issue:** `_aggregate_expression` inlines `effective_start.isoformat()` and
`effective_end.isoformat()` directly into the SQL string:

```python
if mode == "calendar_average":
    return (
        "SUM(value_raw) / "
        f"NULLIF(date_diff('day', DATE '{effective_start.isoformat()}', DATE '{effective_end.isoformat()}'), 0)"
    )
```

`effective_start` and `effective_end` are always `datetime.date` objects produced
by `_parse_day` / `_effective_range_for_metric`, so `.isoformat()` will always
return a safe `"YYYY-MM-DD"` string. There is no injection risk from Strava data
because these values originate from validated request fields, not from
user-supplied strings that flow through to the query builder.

However, this is the pattern the `_ALLOWED_COLUMNS` whitelist and `safe_identifier`
guard were introduced to prevent: user-influenced strings inside SQL fragments.
If the `effective_start`/`effective_end` path ever changes to accept a raw
caller-supplied string (e.g., if `_parse_day` is bypassed), this becomes an
injection point. The cost of switching to a parameter is zero.

**Fix:** Bind as parameters using DuckDB's `DATE` literal via CAST:

```python
if mode == "calendar_average":
    # effective_start/end are added to the outer params list by the caller
    return "SUM(value_raw) / NULLIF(date_diff('day', CAST(? AS DATE), CAST(? AS DATE)), 0)"
```
And add the two values to the params list in `_build_numeric_query` at the point
where `aggregate_expr` is consumed.

---

### WR-05: `_next_id` in `refresh_state_store.py` has a TOCTOU gap — not safe under concurrent enqueue

**File:** `src/mcp_strava/adapters/duckdb/refresh_state_store.py:70-77`

**Issue:**

```python
def _next_id(self, table: str) -> int:
    ...
    row = self._fetchone(f"SELECT COALESCE(MAX(id), 0) + 1 AS id FROM {table}")
    ...
    return _as_int(value, default=1)
```

`_next_id` computes the next id as `MAX(id) + 1` in a separate SELECT from the
INSERT. If two callers race to `enqueue_refresh_request` concurrently, both may
read the same `MAX(id)` and attempt to INSERT with the same id, causing a primary
key violation crash.

In this deployment context there is effectively one writer (the refresh worker),
so the race is unlikely in practice. But the `refresh_requests` table has a
`BIGINT PRIMARY KEY` and there is no sequence/autoincrement in the DDL. The
correct fix is a DuckDB `SEQUENCE` or `BIGINT DEFAULT nextval(...)`.

**Fix:** Add a sequence to the schema and use it:

```sql
CREATE SEQUENCE refresh_requests_id_seq;
CREATE TABLE refresh_requests (
    id BIGINT PRIMARY KEY DEFAULT nextval('refresh_requests_id_seq'),
    ...
);
```

Then remove `_next_id` entirely and drop the explicit `id` from the INSERT.

---

## Info

### IN-01: `types_repository.py` domain dataclasses are disconnected from the DB schema — no shared source of truth

**File:** `src/mcp_strava/types_repository.py:37-163`

**Issue:** The domain dataclasses (`ActivityMetricFact`, `DailyLoadFact`, etc.)
duplicate column names, types, and defaults that are also defined in
`metric_registry_fact_column_sql.py` and the DDL in `schema_tables.py`. After
the phase-16 type migrations (DATE columns, BOOLEAN, VARCHAR[]), the dataclasses
still use the legacy Python types (`str` for days, `int = 0` for
`cardiac_drift_significant` instead of `bool`). This means the dataclasses are
stale documentation at best and incorrect type hints at worst.

**Fix:** Either generate the dataclass fields from the registry metadata
(single source of truth), or at minimum audit and update the types to match the
post-migration schema: `activity_day: date`, `cardiac_drift_significant: bool`,
`missing_reasons_json: list[str]`.

---

### IN-02: `test_duckdb_repository.py` fixture `_activity_fact_values` passes legacy `"cardiac_drift_significant": 0` — not `False`

**File:** `tests/test_duckdb_repository.py:60`

**Issue:** The fixture passes `"cardiac_drift_significant": 0` (an integer) to
`upsert_activity_metric_fact`. The schema column is now `BOOLEAN`. DuckDB accepts
both `0` and `False` for BOOLEAN parameters, but the test is using the
pre-migration integer representation. The `test_read_model_queries.py:175`
fixture does the same (`"cardiac_drift_significant": False`), which is correct.
Inconsistent fixture values make it harder to verify that the BOOLEAN column path
is exercised correctly.

**Fix:** Update `_activity_fact_values` in `test_duckdb_repository.py`:
```python
"cardiac_drift_significant": False,
```

---

_Reviewed: 2026-06-11T09:15:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
