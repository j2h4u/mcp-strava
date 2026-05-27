---
quick_id: 260527-nbq
type: execute
wave: 1
depends_on: []
autonomous: true
files_modified:
  - src/mcp_strava/adapters/duckdb/schema.py
  - src/mcp_strava/adapters/duckdb/repository.py
  - src/mcp_strava/adapters/duckdb/read_model_materializer.py
  - src/mcp_strava/constants.py
  - src/mcp_strava/metrics.py
  - src/mcp_strava/adapters/duckdb/aggregate_queries.py
  - src/mcp_strava/application/metric_registry.py
  - tests/conftest.py
  - tests/test_hr_zones.py

must_haves:
  truths:
    - "Zone bounds for hr_rest=53/hr_max=191 produce [122,136,150,163,177,300]"
    - "TRIMP values for existing fixture activities are byte-identical after the change"
    - "Config.Athlete.HR_MAX, Config.Athlete.HR_REST, Config.Zones.BOUNDS, Config.SQL.TRIMP/ZONES/TRIMP_S/ZONES_S are gone from source"
    - "activity_metric_facts gains min_hr, max_hr, hr_zone_model, hr_max_used, hr_rest_used columns via ALTER TABLE IF NOT EXISTS"
    - "Materializer uses running max-heartrate-to-date per activity; raises clear error when hr_rest is None"
    - "Full suite green: uv run pytest -q"
  artifacts:
    - path: "tests/conftest.py"
      provides: "MCP_STRAVA_HR_REST=53 env fixture autouse for full suite"
    - path: "tests/test_hr_zones.py"
      provides: "Byte-identical TRIMP regression test"
    - path: "src/mcp_strava/adapters/duckdb/schema.py"
      provides: "New provenance columns in DUCKDB_SCHEMA_SQL + ensure_provenance_columns()"
    - path: "src/mcp_strava/adapters/duckdb/read_model_materializer.py"
      provides: "On-the-fly zone computation from running hr_max + settings.athlete"
  key_links:
    - from: "read_model_materializer._zone_seconds"
      to: "hr_zones.zone_bounds()"
      via: "computed integer bounds, not Config.Zones.BOUNDS"
    - from: "repository.activity_trimp / observed_trimp_history"
      to: "hr_zones.zone_bounds()"
      via: "build_trimp_sql(bounds) helper, not Config.SQL.TRIMP*"
---

<objective>
Wire HR-zone computation on the fly into TRIMP materialization and drop all
hardcoded athlete HR constants.

Purpose: The service currently freezes HR-zone boundaries from Config.Athlete
(hr_rest=53, hr_max=191) and Config.Zones.BOUNDS into SQL at import time.
This makes the service non-portable for other athletes. Stages 1-2 already
delivered hr_zones.py (KarvonenHRR strategy) and settings.AthleteSettings
(MCP_STRAVA_HR_REST env var). Stage 3 wires those into actual computation,
persists provenance on activity_metric_facts, and removes the frozen constants.

Output: Updated materializer + repository SQL builders + schema migration;
deleted Config.Athlete/Config.Zones.BOUNDS/Config.SQL.*; green test suite.

KEY INVARIANT: KarvonenHRR at 50/60/70/80/90 %HRR reproduces
[122,136,150,163,177,300] exactly for hr_rest=53/hr_max=191 — so existing TRIMP
values must stay byte-identical.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/260527-nbq-wire-hr-zone-computation-on-the-fly-into/260527-nbq-PLAN.md

# Source files — already read during planning, listed for executor reference
# src/mcp_strava/hr_zones.py          — zone_bounds(), get_zone_model(), KarvonenHRR
# src/mcp_strava/settings.py          — AthleteSettings(hr_rest, hr_zone_model)
# src/mcp_strava/constants.py         — Config.Zones.BOUNDS/COEFF, Config.SQL.*, _build_trimp_cases
# src/mcp_strava/adapters/duckdb/read_model_materializer.py — _zone_seconds(), _activity_fact()
# src/mcp_strava/adapters/duckdb/schema.py                  — DUCKDB_SCHEMA_SQL, create_schema()
# src/mcp_strava/adapters/duckdb/repository.py              — activity_trimp(), observed_trimp_history(), max_heartrate()
# src/mcp_strava/metrics.py                                 — _get_hr_max(), check_z5_minutes()
# src/mcp_strava/adapters/duckdb/aggregate_queries.py       — z5_lower_bound default (~line 286)
# src/mcp_strava/application/metric_registry.py             — trimp/hrr_pct description strings
</context>

<tasks>

<task type="auto">
  <name>Task 1: Schema — add provenance columns + ensure_provenance_columns() for live DB</name>
  <files>
    src/mcp_strava/adapters/duckdb/schema.py
    src/mcp_strava/adapters/duckdb/repository.py
  </files>
  <action>
In schema.py, add five columns to the `activity_metric_facts` CREATE TABLE block
in DUCKDB_SCHEMA_SQL (insert after the existing `stream_sample_count` column,
before the closing PRIMARY KEY line):

    observed_min_hr BIGINT,
    observed_max_hr BIGINT,
    hr_zone_model VARCHAR,
    hr_max_used BIGINT,
    hr_rest_used BIGINT,

Add a new module-level function `ensure_provenance_columns(conn) -> None` that
runs five `ALTER TABLE activity_metric_facts ADD COLUMN IF NOT EXISTS` statements
for each of those columns with the same types. This is the live-DB additive
migration path for existing DuckDB files that were created before this change.
DuckDB supports `ADD COLUMN IF NOT EXISTS` natively.

In repository.py, import and call `ensure_provenance_columns` from the
`DuckDBRepository.__post_init__` or from the point where the repo opens the
connection for the first time — the cleanest existing hook is to call it from
`open_expected_mirror_db` callers. The actual right place: add a
`_ensure_schema_extensions(self) -> None` method on `DuckDBRepository` that
calls `ensure_provenance_columns(self._conn)`, and call that method from
`DuckDBRepository.__post_init__` (or `__init__` — check the dataclass
definition). This ensures every live-DB open migrates the columns before any
materialization runs.

Do NOT touch daily_load_facts, training_model_daily, rolling_period_facts, or
the aggregate views — provenance is activity-level only.
  </action>
  <verify>
    <automated>cd /home/j2h4u/repos/j2h4u/mcp-strava && uv run python -c "
import duckdb, mcp_strava.adapters.duckdb.schema as s
conn = duckdb.connect()
s.create_schema(conn)
cols = {r[1] for r in conn.execute(\"PRAGMA table_info('activity_metric_facts')\").fetchall()}
assert 'observed_min_hr' in cols, cols
assert 'hr_zone_model' in cols, cols
assert 'hr_max_used' in cols, cols
print('OK')
"</automated>
  </verify>
  <done>
    DUCKDB_SCHEMA_SQL contains all five provenance columns; ensure_provenance_columns()
    exists and is called on DuckDBRepository open; fresh create_schema() includes
    the columns; uv run python inline check exits 0.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Build on-the-fly zone SQL helpers + rewire repository TRIMP methods</name>
  <files>
    src/mcp_strava/adapters/duckdb/repository.py
    src/mcp_strava/constants.py
    tests/test_hr_zones.py
  </files>
  <behavior>
    - zone_bounds(hr_rest=53, hr_max=191) == [122, 136, 150, 163, 177, 300]
    - build_trimp_sql(bounds) produces a SQL fragment ending "/ 60.0 as trimp" with
      the correct integer literals from bounds embedded (no Config references)
    - build_zones_sql(bounds) produces the z1..z5 SUM CASE fragment with correct literals
    - activity_trimp(activity_id) on a repo with known fixture data produces the same
      float as the old Config.SQL.TRIMP path for bounds [122,136,150,163,177,300]
    - observed_trimp_history() with same bounds also matches old output
  </behavior>
  <action>
In repository.py, add two module-level helper functions (not methods):

  def build_trimp_sql(bounds: list[int], alias: str = "") -> str
  def build_zones_sql(bounds: list[int], alias: str = "") -> str

These replace `_build_trimp_cases()` from constants.py. They take a precomputed
integer list (already validated) and build the same SQL CASE expressions that
the old `_build_trimp_cases` produced. Use Config.Zones.COEFF for weights (it
stays). Mirror the exact structure of the old output so TRIMP values are
byte-identical:

  build_trimp_sql(bounds, alias=''):  produces the "(SUM(CASE ... END) * coeff + ...) / 60.0 as trimp" string
  build_trimp_sql(bounds, alias='s.'): same with "s." prefix on column references

Rewrite `activity_trimp(self, activity_id: int, bounds: list[int]) -> float` to
REQUIRE an explicit `bounds` parameter (NO default). Build the SQL via
`build_trimp_sql(bounds, alias='')`.

Rewrite `observed_trimp_history(...)` similarly: REQUIRE explicit `bounds`,
build SQL via `build_trimp_sql(bounds, alias='s.')`.

DO NOT add any hardcoded fallback bounds. There is NO `_DEFAULT_BOUNDS` and no
`zone_bounds(191, 53)` constant anywhere — the locked design forbids hardcoded
athlete defaults. Every caller computes bounds from (running max-HR-to-date,
hr_rest from settings) and fails fast when hr_rest is unset. Plumb `bounds`
through the callers: the materializer passes its per-activity computed bounds;
any other caller (db.py / metrics.py) must compute bounds the same way (shared
helper) or be updated in Task 4. If a caller cannot obtain bounds, it must fail
loudly — never fabricate a default.

In constants.py, DELETE:
  - `Config.Athlete` class entirely (HR_MAX, HR_REST)
  - `Config.Zones.BOUNDS` (keep Config.Zones.COEFF and the class itself)
  - The `_build_trimp_cases` function and its calls
  - The `ZONES_SQL`, `TRIMP_SQL`, `ZONES_SQL_S`, `TRIMP_SQL_S` module-level
    assignments (lines 156-158)
  - The `Config.SQL = type(...)` block (lines 160-165)
  - The `del _build_trimp_cases` line

In tests/test_hr_zones.py — NOTE: this file ALREADY EXISTS (stage 1, committed)
and already has the Karvonen bounds-exact test. EXTEND it (append new tests);
do NOT recreate/overwrite it and do NOT duplicate the existing bounds test. Add:
  - test_build_trimp_sql_identity: call build_trimp_sql([122,136,150,163,177,300])
    and assert "/ 60.0 as trimp" in result and "122" in result and "177" in result
  - test_trimp_regression: using an in-memory DuckDB fixture with 10 stream rows
    at known heartrates, verify activity_trimp(bounds=[122,136,150,163,177,300])
    returns the same value as a manually computed reference (write the reference
    as a docstring formula, not by calling the old Config path)
  </action>
  <verify>
    <automated>cd /home/j2h4u/repos/j2h4u/mcp-strava && uv run pytest tests/test_hr_zones.py -v</automated>
  </verify>
  <done>
    tests/test_hr_zones.py all pass; no reference to Config.Athlete or Config.SQL
    remains in repository.py or constants.py (verify with grep); Config.Zones.COEFF
    still present in constants.py.
  </done>
</task>

<task type="auto">
  <name>Task 3: Wire on-the-fly bounds into materializer; add running max-to-date query; persist provenance</name>
  <files>
    src/mcp_strava/adapters/duckdb/read_model_materializer.py
    src/mcp_strava/adapters/duckdb/repository.py
  </files>
  <action>
In repository.py, add a new method:

  def max_heartrate_to_date(self, activity_day: str) -> int | None

It runs:
  SELECT MAX(s.heartrate) FROM streams s
  JOIN activities a ON a.id = s.activity_id
  WHERE s.heartrate IS NOT NULL
    AND a.activity_day <= CAST(? AS DATE)

Returns int or None. This is the running-max-to-date used by the materializer
for each activity's zone computation.

Also add:

  def activity_hr_range(self, activity_id: int) -> tuple[int | None, int | None]

Returns (min_hr, max_hr) from streams for that activity (for provenance storage).
Single query: SELECT MIN(heartrate) AS min_hr, MAX(heartrate) AS max_hr FROM streams
WHERE activity_id = ? AND heartrate IS NOT NULL.

In read_model_materializer.py, update the imports to add:
  from mcp_strava.hr_zones import get_zone_model
  from mcp_strava.settings import get_settings

Update the `materialize_activity_facts` entry point (or wherever `_activity_fact`
is called from) to accept a `settings` parameter (default: `get_settings()`).

Update `_zone_seconds(repo, activity_id)` signature to:
  `_zone_seconds(repo, activity_id, bounds: list[int]) -> tuple[int,int,int,int,int,int]`

The function now takes the precomputed bounds list and builds the SQL inline
(same CASE structure as before, using parameterised int literals from bounds).
The SQL uses the 6-zone layout from bounds: z1 is HR < bounds[0], z2..z5 are
bounds[i-1] <= HR < bounds[i], z5 is HR >= bounds[-2] (same logic as before).
Return a 6-tuple of ints (z0..z5 — there is already a Z0/recovery zone in the
old Config; recheck the actual structure: Config.Zones.COEFF has 6 entries
[0.5,1,2,3,4,5] matching 6 zones; existing schema has zone1_seconds..zone5_seconds
= 5 columns. Cross-check with the existing query in materializer.py: it returns
z1..z5, a 5-tuple. Preserve that: bounds has 6 elements including the cap, so
zones are z1=HR<bounds[0], z2..z5 are the 4 middle intervals, but existing code
only emits 5 zones matching the 5 schema columns. Replicate exactly the existing
parameterized query structure — just replace the hardcoded `b = Config.Zones.BOUNDS`
lookup with the passed-in `bounds` list).

In `_activity_fact`, before calling `_zone_seconds`:
  1. Call `repo.max_heartrate_to_date(dirty_row["activity_day"])` → `hr_max_observed`
  2. Load athlete settings: `athlete = settings.athlete`
  3. If `athlete.hr_rest is None`: raise RuntimeError(
       "MCP_STRAVA_HR_REST is not set — cannot compute HR zones. "
       "Set MCP_STRAVA_HR_REST to the athlete's resting heart rate."
     )
  4. If `hr_max_observed is None` (the activity has no heart-rate samples at
     all): there is no HR data to bin, so zone seconds are all zero and TRIMP is
     0. Skip bounds computation entirely, set zone_seconds=(0,0,0,0,0), and
     record hr_max_used=None. DO NOT fabricate a fallback max — there is no
     `_FALLBACK_HR_MAX` and no hardcoded constant.
  5. Otherwise compute `bounds = get_zone_model(athlete.hr_zone_model).zone_bounds(
       hr_max=int(hr_max_observed), hr_rest=athlete.hr_rest)`
  Note: reuse this same `hr_max_observed` (max-to-date) as the hr_max for hrr_pct
  in this activity's fact, so hrr_pct is consistent with the zone bounds and
  stable on re-materialization (do not use a separate global all-time max here).
  6. Call `_zone_seconds(repo, activity_id, bounds)` with the computed bounds.
  7. Also compute TRIMP using `build_trimp_sql(bounds)` (imported from repository)
     to build the SQL — OR simply call the repo method with explicit bounds:
     `repo.activity_trimp(activity_id, bounds=bounds)`. Use the repo method.
  8. Call `repo.activity_hr_range(activity_id)` → `(min_hr, max_hr)`.

Add provenance fields to the returned dict from `_activity_fact`:
    "observed_min_hr": min_hr,
    "observed_max_hr": max_hr,
    "hr_zone_model": athlete.hr_zone_model,
    "hr_max_used": int(hr_max_observed) if hr_max_observed else None,
    "hr_rest_used": athlete.hr_rest,

The `settings` parameter threads through from the public `materialize_activity_facts`
function. Find that function in the materializer (it calls `_activity_fact` in a
loop over dirty rows) and add `settings: Settings | None = None` with
`settings = settings or get_settings()` at the top, then pass settings down.
  </action>
  <verify>
    <automated>cd /home/j2h4u/repos/j2h4u/mcp-strava && uv run pytest tests/test_read_model_queries.py -v -q</automated>
  </verify>
  <done>
    _zone_seconds uses passed bounds not Config.Zones.BOUNDS; _activity_fact
    computes running hr_max per activity; provenance fields are populated in
    upsert dict; test_read_model_queries.py passes; no Config.Zones.BOUNDS
    reference remains in materializer.
  </done>
</task>

<task type="auto">
  <name>Task 4: Rewire remaining consumers + create conftest.py + fix metric_registry descriptions</name>
  <files>
    src/mcp_strava/metrics.py
    src/mcp_strava/adapters/duckdb/aggregate_queries.py
    src/mcp_strava/application/metric_registry.py
    tests/conftest.py
  </files>
  <action>
In metrics.py:
  - Remove the module-level `_hr_max_cache` global and `_get_hr_max(conn)` function.
    All callers of `_get_hr_max` should be audited; for any call sites that remain
    (grep for `_get_hr_max`), replace with `repo.max_heartrate()` directly on a
    repo obtained via `repository_from_connection(conn)`. If hrr_pct computation
    uses _get_hr_max, replace with `repo.max_heartrate()` (global all-time max is
    acceptable for hrr_pct normalization, unlike TRIMP zone computation).
  - In `check_z5_minutes(conn, activity_id, z5_threshold=None, ...)`:
    When `z5_threshold` is None, compute it from the athlete's zones — NO literal
    fallback. Obtain a repo via `repository_from_connection(conn)`, use
    `repo.max_heartrate()` for hr_max and `get_settings().athlete.hr_rest` for
    hr_rest. If `hr_rest is None`, raise RuntimeError with the SAME clear
    MCP_STRAVA_HR_REST message used in the materializer. If `repo.max_heartrate()`
    is None (no HR data anywhere), there is nothing to threshold — return 0
    Z5 minutes. Otherwise compute `bounds =
    get_zone_model(get_settings().athlete.hr_zone_model).zone_bounds(hr_max, hr_rest)`
    and use `bounds[-2]` as the Z5 lower bound. No literal 177, no Config import.

In aggregate_queries.py (~line 286):
  - The line `z5_lower_bound = int(definition.threshold.get("z5_lower_bound_bpm", Config.Zones.BOUNDS[-2]))`.
    The registry-configured `z5_lower_bound_bpm` still wins when present. For the
    DEFAULT (when the registry does not specify one), compute the Z5 lower bound
    from the athlete's zones — NO literal 177. Use a repo over `conn`
    (`repository_from_connection`) for hr_max via `repo.max_heartrate()`, and
    `get_settings().athlete.hr_rest` for hr_rest; if `hr_rest is None`, raise
    RuntimeError with the same MCP_STRAVA_HR_REST message. Compute
    `bounds = get_zone_model(get_settings().athlete.hr_zone_model).zone_bounds(hr_max, hr_rest)`
    and use `bounds[-2]`. No Config import, no hardcoded constant.

In metric_registry.py, update description strings that reference Config symbols:
  - "trimp" description (line ~153): replace
      "sum(seconds in configured HR zones * Config.Zones.COEFF) / 60"
    with:
      "sum(seconds in each HR zone * zone weight) / 60 using the configured HR zone model and athlete resting HR"
  - "hrr_pct" description (line ~172): replace
      "(median_hr - Config.Athlete.HR_REST) / (observed_hr_max - HR_REST) * 100"
    with:
      "(median_hr - athlete_hr_rest) / (observed_hr_max - athlete_hr_rest) * 100, using MCP_STRAVA_HR_REST"

Remove any remaining import of Config from metric_registry.py if Config is no
longer used after these changes (check with grep). Do not remove imports that
are still needed for Config.Plan, Config.Model, Config.Thresholds, etc. — only
remove Config.Athlete and Config.Zones.BOUNDS references.

Create tests/conftest.py with an autouse session-scoped fixture that sets
`MCP_STRAVA_HR_REST=53` in os.environ before the test session runs and removes
it after. Also reset the settings cache around each test that exercises settings.
Minimal implementation:

  import os
  import pytest
  from mcp_strava.settings import reset_settings_cache

  @pytest.fixture(autouse=True, scope="session")
  def set_hr_rest_env():
      os.environ.setdefault("MCP_STRAVA_HR_REST", "53")
      yield
      # leave set — test process exits anyway

  @pytest.fixture(autouse=True)
  def reset_settings():
      reset_settings_cache()
      yield
      reset_settings_cache()
  </action>
  <verify>
    <automated>cd /home/j2h4u/repos/j2h4u/mcp-strava && uv run pytest -q 2>&1 | tail -5</automated>
  </verify>
  <done>
    No reference to Config.Athlete, Config.Zones.BOUNDS, or Config.SQL remains
    anywhere in src/ (verify: grep -r "Config\.Athlete\|Config\.Zones\.BOUNDS\|Config\.SQL" src/
    returns nothing); uv run pytest -q reports all passing with 0 errors; conftest.py
    exists with autouse fixtures.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| env → settings | MCP_STRAVA_HR_REST is operator-supplied; validated as int in 20..120 range already in settings.py |
| streams DB → zone bounds | hr_max observed from mirror data; capped to int, used only as arithmetic input to zone formula |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-nbq-01 | Tampering | build_trimp_sql / build_zones_sql | mitigate | Bounds input is list[int] derived from zone_bounds() — integer arithmetic only, no string injection possible |
| T-nbq-02 | Denial of Service | max_heartrate_to_date() per activity | accept | Single indexed query per dirty activity; materializer already has bounded dirty-queue batching |
| T-nbq-03 | Information Disclosure | hr_rest_used persisted in activity_metric_facts | accept | Local DB only; no PII concern beyond what streams already contain |
</threat_model>

<verification>
After all tasks:

1. grep -r "Config\.Athlete" src/ — must return nothing
2. grep -r "Config\.Zones\.BOUNDS" src/ — must return nothing
3. grep -r "Config\.SQL" src/ — must return nothing
4. uv run pytest -q — all tests pass, 0 failures
5. uv run pytest tests/test_hr_zones.py -v — TRIMP regression test passes explicitly
6. uv run python -c "from mcp_strava.hr_zones import zone_bounds; b = zone_bounds(191, 53); assert b == [122,136,150,163,177,300], b; print('bounds OK')"
</verification>

<success_criteria>
- KarvonenHRR at hr_rest=53/hr_max=191 reproduces [122,136,150,163,177,300] (verified by test)
- TRIMP regression test: known fixture activity produces same float as before
- Five provenance columns present in activity_metric_facts (fresh + live via ALTER TABLE IF NOT EXISTS)
- Config.Athlete, Config.Zones.BOUNDS, Config.SQL.* deleted from source
- Full test suite green: uv run pytest -q
- conftest.py autouse fixture ensures MCP_STRAVA_HR_REST=53 for all test runs
</success_criteria>

<output>
Create `.planning/quick/260527-nbq-wire-hr-zone-computation-on-the-fly-into/260527-nbq-SUMMARY.md` when done.
</output>
