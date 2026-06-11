# Phase 16: DuckDB-native storage cleanup - Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 12 modified files across 5 tasks
**Analogs found:** 12 / 12 (all modifications of existing files — no new modules)

---

## File Classification

| Modified File | Role | Data Flow | Closest Analog (within file or sibling) | Match Quality |
|---|---|---|---|---|
| `schema_tables.py` | config/DDL | batch | `activity_day DATE` col (line 10) — the one native DATE already in the file | exact |
| `metric_registry_fact_column_sql.py` | config/registry | batch | `_sql("DATE", nullable=False)` entries (lines 18,19,64,85) — same allowlist + metadata pattern | exact |
| `kudos_store.py` | query | request-response | `activity_selectors.py` DATE range predicate with `CAST(? AS DATE)` | role-match |
| `activity_lookup_queries.py` | query | request-response | `activity_selectors.py` line 22 — `a.activity_day` in SELECT/GROUP BY | exact |
| `activity_selectors.py` | query | request-response | self — `a.activity_day` already used on lines 22/29 alongside `a.date` | exact |
| `stream_coverage_queries.py` | query | request-response | self line 43 — `CAST(? AS DATE)` bound param pattern already present | exact |
| `read_model_repository.py` | repository | CRUD | self lines 178,202 — other `AS activity_date` aliases in same SELECT | exact |
| `refresh_state_store.py` | repository | CRUD | self — `enqueue_refresh_request` write + `pending_refresh_requests` read (lines 196-233) | exact |
| `stream_write_repository.py` | repository | batch | self line 137 — `row.get("is_moving")` binding site | exact |
| `read_model_activity_facts.py` | service | transform | self line 184 — `cardiac_drift_significant: 1 if … else 0` | exact |
| `aggregate_queries.py` | query | batch | self line 293 — `list(DISTINCT completeness_status)` as analog for array aggregation | exact |
| `aggregate_rows.py` | decoder | transform | self lines 160-166 — `isinstance(values, list)` + `.extend()` pattern for flat list decode | exact |
| `schema_views.py` | config/DDL | batch | self lines 9,55 — existing `CAST(x AS DATE)` targets | exact |
| `read_model_materializer_utils.py` | utility | transform | self — `_json_list()` function (write helper to convert) | exact |
| `read_model_period_facts.py` | service | transform | self — hardcoded `"[]"` literals | exact |
| `status_fact_queries.py` | query | request-response | self line 247 — `>= ?` predicate site | exact |
| `tests/test_duckdb_repository.py` | test | — | self lines 638-669 — `test_activities_missing_kudos_filters_and_returns_typed_ids` | exact |

---

## Pattern Assignments

### Task 1 — Drop `activities.date`; make kudos native

#### `schema_tables.py` — remove `date VARCHAR` column

**Analog:** `schema_tables.py` line 10 — `activity_day DATE NOT NULL` is the template for how a native DATE column is declared in `DUCKDB_SCHEMA_SQL`.

**DDL pattern to keep** (`schema_tables.py:9-10`):
```sql
id BIGINT PRIMARY KEY,
activity_day DATE NOT NULL,
```

**Line to delete** (`schema_tables.py:11`):
```sql
date VARCHAR,
```

No migration, no ALTER. The whole `DUCKDB_SCHEMA_SQL` string is re-executed on a fresh DB.

---

#### `kudos_store.py` — rewrite `window_days` branch (lines 51-54)

**Current (SQLite-only, dead branch)** (`kudos_store.py:51-54`):
```python
if window_days is not None:
    query += " AND a.date >= date('now', ?)"
    params.append(f"-{window_days} days")
query += " ORDER BY a.date DESC"
```

**Analog for native DuckDB date arithmetic:** `stream_coverage_queries.py:43` already uses a bound ISO param with `CAST(? AS DATE)` against `activity_day`:
```python
"""
  AND (? IS NULL OR a.activity_day >= CAST(? AS DATE))
""",
[since, since],
```

**Target pattern** for `kudos_store.py` (bind plain `int`, use `INTERVAL`):
```python
if window_days is not None:
    query += " AND a.activity_day >= (CURRENT_DATE - (? * INTERVAL '1 day'))"
    params.append(window_days)          # plain int, NOT a formatted string
query += " ORDER BY a.activity_day DESC"
```

---

#### Readers of `a.date` → `a.activity_day`

All four files follow the same mechanical swap. The `activity_selectors.py` self-analog shows the correct form already in use:

**Analog** (`activity_selectors.py:22,29`) — already uses `a.activity_day`:
```python
# line 22 (SELECT list):  a.activity_day,
# line 29 (GROUP BY):     a.activity_day
```

The residual `a.date` entries at lines 22 and 29 (if any remain) follow the same pattern — replace with `a.activity_day`.

**`stream_coverage_queries.py:40`** — `SELECT a.id, a.date` → `SELECT a.id` (the `date` value is unused downstream; only `row["id"]` is consumed at line 52).

**`read_model_repository.py:178,202`** — alias pattern:
```python
# Current:
a.date AS activity_date
# After:
a.activity_day AS activity_date
```
`str(datetime.date(2026,5,21))` == `"2026-05-21"` — payload shape unchanged.

**`activity_lookup_queries.py` lines 23,37,57,78`** — remove `date` from SELECT lists; change `MAX(date)` to `MAX(activity_day)`. `str(MAX(activity_day))` on a DATE column still yields `"YYYY-MM-DD"`.

---

#### New test — `test_activities_missing_kudos_with_window_days`

**Analog:** `test_duckdb_repository.py:638-669` — `test_activities_missing_kudos_filters_and_returns_typed_ids`

The existing test pattern to copy:
```python
def test_activities_missing_kudos_filters_and_returns_typed_ids(tmp_path: Path) -> None:
    fixture = tmp_path / "strava.duckdb"
    _create_duckdb_fixture(fixture)

    def _seed(repo: DuckDBRepository, activity_id: int, kudos_count: int) -> None:
        repo.upsert_activity_summary(
            activity_id=activity_id,
            date="2026-05-21T06:00:00Z",    # ← use CURRENT_DATE-relative dates for window test
            ...
            summary_json=f'{{"id":{activity_id},"kudos_count":{kudos_count}}}',
            ...
        )

    with DuckDBRepository.from_path(fixture) as repo:
        _seed(repo, 201, kudos_count=3)
        ids = activities_missing_kudos(repo)
        assert ids == [201]
```

**New test shape** — seed three activities with `start_date_local` at today-1, today-5, today-20; call `activities_missing_kudos(repo, window_days=7)`; assert only today-1 and today-5 returned; call with `window_days=None` and assert all three returned.

---

### Task 2 — `refresh_requests.requested_for_day` VARCHAR → DATE

#### `schema_tables.py:97`

**Analog:** `schema_tables.py:104` — `activity_source_state.activity_day DATE NOT NULL` is the pattern for a non-nullable DATE in DDL.

**Change:**
```sql
-- Current (line 97):
requested_for_day VARCHAR NOT NULL,
-- After:
requested_for_day DATE NOT NULL,
```

#### `refresh_state_store.py` — write path (lines 196-216)

**Current write** (`refresh_state_store.py:196,205,214`):
```python
def enqueue_refresh_request(self, reason: str, requested_for_day: str, ...) -> bool:
    ...
    WHERE reason = ? AND requested_for_day = ? AND consumed_at IS NULL
    ...
    [reason, requested_for_day],
    ...
    [self._next_id("refresh_requests"), reason, requested_for_day, timestamp],
```

**Target:** change signature to `requested_for_day: datetime.date`, pass `datetime.date` object directly — DuckDB Python connector binds `datetime.date` to `DATE` natively (same mechanism as `activity_day`).

**Read path** (`refresh_state_store.py:232`):
```python
requested_for_day=str(row["requested_for_day"]),
```
`str(datetime.date(2026,5,21))` == `"2026-05-21"` — `RefreshRequestRow.requested_for_day: str` contract preserved.

---

### Task 3 — BIGINT → BOOLEAN

#### 3a. `streams.is_moving` — `schema_tables.py:35`

**Change:**
```sql
-- Current:
is_moving BIGINT,
-- After:
is_moving BOOLEAN,
```

**Write path analog** (`stream_write_repository.py:137`) — current raw bind:
```python
row.get("is_moving"),
```

**Target** — cast at bind time before appending to params tuple:
```python
is_moving_raw = row.get("is_moving")
# bind: bool(is_moving_raw) if is_moving_raw is not None else None
```

DuckDB Python connector accepts Python `bool` for `BOOLEAN` columns. Existing test fixtures pass integer `1` — DuckDB coerces `1`→`TRUE` on INSERT, but update fixtures to `True` for type-safety.

---

#### 3b. `cardiac_drift_significant` — `metric_registry_fact_column_sql.py`

**Registry allowlist pattern** (lines 5, 8 — the gates to update first):
```python
_SUPPORTED_FACT_SQL_TYPES = frozenset({"BIGINT", "DOUBLE", "VARCHAR", "DATE"})
# Add "BOOLEAN":
_SUPPORTED_FACT_SQL_TYPES = frozenset({"BIGINT", "DOUBLE", "VARCHAR", "DATE", "BOOLEAN"})

_SUPPORTED_FACT_DEFAULT_SQL = frozenset({"0", "0.0", "'[]'"})
# No change needed — keep default_sql="0" for BOOLEAN (DuckDB coerces 0→FALSE)
```

**Analog for `_sql()` entry pattern** — existing DATE column entry (line 18):
```python
"activity_day": _sql("DATE", nullable=False),
```

**Target entry** (`metric_registry_fact_column_sql.py:45`):
```python
# Current:
"cardiac_drift_significant": _sql("BIGINT", nullable=False, default_sql="0"),
# After:
"cardiac_drift_significant": _sql("BOOLEAN", nullable=False, default_sql="0"),
```
`default_sql="0"` stays — `"0"` is already in `_SUPPORTED_FACT_DEFAULT_SQL`. No allowlist expansion needed for this sub-task.

**Write path** (`read_model_activity_facts.py:184`, and line 323 identical):
```python
# Current:
"cardiac_drift_significant": 1 if (drift and drift.is_significant) else 0,
# After:
"cardiac_drift_significant": bool(drift and drift.is_significant),
```

**Predicate** (`status_fact_queries.py:247`):
```sql
-- Current:
AND cardiac_drift_significant >= ?
-- After:
AND cardiac_drift_significant = TRUE
```
Remove the bound parameter that was `1`. No `?` placeholder needed.

---

### Task 4 — `missing_reasons_json` VARCHAR → VARCHAR[]

#### `schema_tables.py:135,158,183` + `metric_registry_fact_column_sql.py`

**Allowlist expansions required first** (`metric_registry_fact_column_sql.py:5,8`):
```python
_SUPPORTED_FACT_SQL_TYPES = frozenset({"BIGINT", "DOUBLE", "VARCHAR", "DATE", "BOOLEAN", "VARCHAR[]"})
_SUPPORTED_FACT_DEFAULT_SQL = frozenset({"0", "0.0", "'[]'", "[]"})
#                                                              ^^^^ bare array literal for VARCHAR[]
```

**DDL change** (same pattern in all three tables + `activity_metric_facts` registry entry):
```sql
-- Current:
missing_reasons_json VARCHAR NOT NULL DEFAULT '[]',
-- After:
missing_reasons_json VARCHAR[] NOT NULL DEFAULT [],
```

**Registry entry analog** — `missing_reasons_json` in `daily_load_facts` dict (`metric_registry_fact_column_sql.py:70`):
```python
# Current:
"missing_reasons_json": _sql("VARCHAR", nullable=False, default_sql="'[]'"),
# After (all four tables):
"missing_reasons_json": _sql("VARCHAR[]", nullable=False, default_sql="[]"),
```

#### Write helper `read_model_materializer_utils._json_list()`

```python
# Current:
def _json_list(values: list[str]) -> str:
    return json.dumps(sorted(set(values)), ensure_ascii=True)
# After:
def _json_list(values: list[str]) -> list[str]:
    return sorted(set(values))
```
DuckDB Python connector binds Python `list[str]` to `VARCHAR[]` natively.

#### Write sites `read_model_period_facts.py:113,155`

```python
# Current:
"missing_reasons_json": "[]",
# After:
"missing_reasons_json": [],
```

#### Aggregate SQL `aggregate_queries.py:294,377,462`

**Analog for `list(DISTINCT ...)` aggregation** — line 293 in the same SELECT block:
```sql
list(DISTINCT completeness_status) AS completeness_statuses,
```

**Target** (flatten + deduplicate the list-of-arrays):
```sql
-- Current:
list(missing_reasons_json) AS missing_reason_payloads
-- After:
list_distinct(flatten(list(missing_reasons_json))) AS missing_reason_payloads
```
`flatten` collapses `list[list[str]]` → `list[str]`; `list_distinct` deduplicates. Result is a flat `list[str]` — no Python json.loads needed.

#### Decode path `aggregate_rows._missing_reasons()` (lines 169-181)

**Current** (json.loads per element):
```python
def _missing_reasons(row: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    payloads = row.get("missing_reason_payloads")
    for payload in payloads if isinstance(payloads, list) else []:
        if payload is None:
            continue
        try:
            parsed = cast("object", json.loads(str(payload)))
        except json.JSONDecodeError:
            parsed = [str(payload)]
        if isinstance(parsed, list):
            reasons.extend(str(item) for item in parsed if item)
    return reasons
```

**Analog for flat-list extend pattern** — `aggregate_rows.py:164-166` (quantile decode):
```python
if not isinstance(values, list):
    return None
return {label: as_float(value) for label, value in zip(DEFAULT_AGGREGATE_QUANTILES, values, strict=False)}
```

**Target** — DB is recreated fresh, no mixed rows; drop the `json.loads` branch entirely:
```python
def _missing_reasons(row: dict[str, object]) -> list[str]:
    payloads = row.get("missing_reason_payloads")
    if not isinstance(payloads, list):
        return []
    return [str(item) for item in payloads if item is not None]
```
After this change `import json` in `aggregate_rows.py` has no remaining uses — remove it.

---

### Task 5 — SQL cleanups

#### `schema_views.py` — remove redundant `CAST(x AS DATE)`

**Pattern to remove** — line 9 is the first instance, same idiom repeats at ~55,82,109,121,182:
```sql
-- Current (line 9):
CAST(f.activity_day AS DATE) AS activity_day,
-- After (activity_day is already DATE in activity_metric_facts):
f.activity_day,
```

**WHERE predicate** (~line 125):
```sql
-- Current:
CAST(a.activity_day AS DATE) <= d.day
-- After (both sides are DATE):
a.activity_day <= d.day
```

No behavior change — DuckDB no-ops a `CAST(x AS T)` when `x` is already `T`.

#### `stream_coverage_queries.py:77-90` — Python loop → SQL predicate

**Current Python loop** (lines 77-90):
```python
value_rows = repo._fetchall(
    """
    SELECT values_json
    FROM streams
    WHERE activity_id=?
      AND values_json IS NOT NULL
    """,
    [activity_id],
)
if not any(
    channel in (json.loads(str(item["values_json"])) if item["values_json"] else {})
    for item in value_rows
):
    missing_channels.append(channel)
```

**Analog for `_fetchone` with existence predicate** — `refresh_state_store.py:198-206`:
```python
existing = self._fetchone(
    """
    SELECT id
    FROM refresh_requests
    WHERE reason = ? AND requested_for_day = ? AND consumed_at IS NULL
    LIMIT 1
    """,
    [reason, requested_for_day],
)
if existing is not None:
    return False
```

**Target** — replace the entire fetch+loop block with one SQL predicate call:
```python
exists_row = repo._fetchone(
    """
    SELECT 1 FROM streams
    WHERE activity_id = ?
      AND json_extract_string(values_json, '$.' || ?) IS NOT NULL
    LIMIT 1
    """,
    [activity_id, channel],
)
if exists_row is None:
    missing_channels.append(channel)
```
`values_json` remains `VARCHAR` — `json_extract_string` operates on VARCHAR in DuckDB. The `'$.' || ?` channel-key concatenation uses a bound param — no injection risk.

---

## Shared Patterns

### Native DATE binding
**Source:** `stream_coverage_queries.py:43` + `schema_tables.py:10`
**Apply to:** Tasks 1, 2 — all write/read paths for DATE columns.

DuckDB Python connector binds `datetime.date` directly to `DATE` columns. `str(datetime.date(...))` → `"YYYY-MM-DD"`. No explicit `CAST(? AS DATE)` needed when binding a `datetime.date` object; the cast form is only needed when binding an ISO string.

### `_fetchone` existence check
**Source:** `refresh_state_store.py:198-206`
**Apply to:** Task 5b stream coverage predicate.

Pattern: `_fetchone(SELECT 1 ... LIMIT 1)` → `None` means absent, non-None means present. Used throughout the adapter — this is the canonical existence probe.

### Registry-owned fact column: allowlist → metadata → DDL → write → predicate chain
**Source:** `metric_registry_fact_column_sql.py:5,8,45` + `metric_registry_fact_columns.py` validator
**Apply to:** Tasks 3b and 4 (BOOLEAN, VARCHAR[]).

Order of changes is mandatory: update `_SUPPORTED_FACT_SQL_TYPES` and `_SUPPORTED_FACT_DEFAULT_SQL` **first**, then change the metadata entry, then write path, then predicate. The validator runs at import time — wrong order causes startup crash.

---

## No Analog Found

None — all five tasks modify existing files with clear self-analogs or close sibling analogs. No new modules are created.

---

## Metadata

**Analog search scope:** `src/mcp_strava/adapters/duckdb/`, `src/mcp_strava/metric_registry_fact_column_sql.py`, `tests/test_duckdb_repository.py`
**Files read:** 10 source files, 1 test file
**Pattern extraction date:** 2026-06-11
