# Phase 10: Materialize unwired training metrics and enforce core/domain storage boundary - Research

**Researched:** 2026-05-29
**Domain:** Python service refactor — pure-domain extraction + read-model materialization wiring + import-boundary guard (DuckDB analytics, no external packages)
**Confidence:** HIGH (all claims verified against the codebase this session)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
1. **`metrics.py` → pure domain module.** Extract pure functions from the conn-coupled ones:
   `calc_hr_recovery(rows)`, `calc_vertical_speed(rows)`, `calc_cardiac_drift(rows, sport_type)`,
   and add pure `calc_hrr_pct(median_hr, hr_rest, hr_max)`. Remove
   `from mcp_strava.db import repository_from_connection`. Mirror the clean ideal in
   `src/mcp_strava/training.py` (pure functions over plain data → dataclasses).
2. **Delete abandoned dead code** from `metrics.py`: `enrich_activity`, `calc_decoupling`,
   `_decoupling_invalid`, `calc_decoupling_with_gate`, `_fetch_decoupling_rows`,
   `calc_efficiency_factor`. Verify each is unregistered + unused in `src/` before removing.
3. **Wire pure functions into `read_model_materializer.py::_activity_fact`**: fetch rows via the repo
   (`stream_hr_velocity_time_rows`, `stream_altitude_rows`, `stream_hr_velocity_simple_rows`,
   `activity_median_heartrate`) and populate the ~13 real columns instead of defaults.
   **hr_max for `hrr_pct`:** reuse the existing max-to-date `hr_max_observed` already computed in
   `_activity_fact` (consistent with how zones/TRIMP use it), NOT `metrics.py`'s old all-time
   `max_heartrate()`. Document the choice.
4. **Add the missing boundary guard.** Extend the
   `test_read_modules_do_not_import_strava_or_refresh` family in `tests/test_security_guards.py` to
   ALSO forbid `mcp_strava.db` and `mcp_strava.adapters.duckdb` imports from the domain modules
   (`training`, `hr_zones`, `sports`, `cardiac_drift`, `metrics`).
5. **Update/replace coupled tests:** `test_smoke.py`, `test_metric_services.py`,
   `test_security_guards.py`. Add unit tests for the new pure functions + a materializer test
   asserting the columns are populated (not defaults).
6. **Delete dead `db.py::get_daily_trimp_history`** (unused in `src/`).
7. **LIVE OPS (operator-run, not code):** after deploy, re-materialize the read model so columns
   populate; verify via MCP that metrics return real values.

### Claude's Discretion
- Exact pure-function signatures and dataclass returns (must mirror `training.py` style).
- Where to put the new pure-function unit tests and the materializer-population assertions.
- Plan/wave decomposition.

### Deferred Ideas (OUT OF SCOPE)
- `decoupling` and Efficiency Factor (EF) were deliberately removed from enrichment in May 2026
  and are abandoned — safe to delete as dead code, NOT to revive.
- Deleting the registered metrics (hr_recovery_*, cardiac_drift_*) is OFF THE TABLE — preserve and fix.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| Core/domain separation (PROJECT.md Active) | Domain modules must import no storage/adapter, enforced by a boundary test | The only remaining violation is `metrics.py` line 5: `from mcp_strava.db import repository_from_connection`. Verified by grep that HTTP/MCP/CLI boundaries are already guard-enforced. Removing that import + adding the boundary guard closes the requirement. |
| fix unmaterialized registered metrics (260525-jpo preserve-and-fix) | hr_recovery_*, vertical_speed_*, cardiac_drift_*, hrr_pct + rolling medians are registered+exposed but materialized as null/0 | `_activity_fact` lines 190–205 write hardcoded defaults; registry (`metric_registry.py` lines 873–888) maps each empty column to a registered, `get_workout_detail`/`compare_periods`-exposed metric. Wiring the pure functions populates them. |
</phase_requirements>

## Summary

This is a two-in-one refactor + latent-bug-fix phase with **zero new external dependencies**. The
work is entirely internal Python: (1) split `metrics.py`'s storage-coupled functions into pure
compute functions (fetch stays in the materializer, compute moves to pure functions), (2) wire those
pure functions into `read_model_materializer.py::_activity_fact` to replace ~13 hardcoded
default columns with real computed values, (3) add an AST-based import-boundary test, and (4) delete
verified-dead code in `metrics.py` and `db.py` plus update the tests that referenced it.

The architecture move and the bug fix are the **same change**: the formulas only live in the dead,
coupled `metrics.py`. Making them pure (so the domain module is import-clean) is exactly what lets the
materializer call them. The rolling medians (`rolling_median_hr_recovery`,
`rolling_median_cardiac_drift_pct`) need **no new code** — `_materialize_rolling_facts` already SELECTs
`hr_recovery_median_rate` and `cardiac_drift_pct` from `activity_metric_facts` (verified:
read_model_materializer.py lines 370, 405–406); they populate automatically once the per-activity facts
are non-null.

**Primary recommendation:** TDD this. Write failing unit tests for the four pure functions against
plain-dict / scalar inputs (RED), extract the pure functions and re-point the materializer (GREEN),
then add the import-boundary guard and a materializer-population test, and delete dead code last (so the
test suite stays green throughout). The pure functions are textbook TDD candidates — deterministic
`fn(input) -> dataclass`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Compute hr_recovery / vertical_speed / cardiac_drift / hrr_pct from stream rows | Core / Domain (`metrics.py`) | — | Pure math over plain data; must not touch storage (the requirement being closed). |
| Fetch stream rows for those computations | Database / Storage (`DuckDBRepository`) | — | Row streaming is a repository concern; already implemented (`stream_*_rows`). |
| Orchestrate fetch→compute→store per activity | Adapter (`read_model_materializer._activity_fact`) | Database | The materializer already owns the `repo` handle and the per-activity loop; it is the correct seam to call repo (fetch) then pure functions (compute). |
| Serve materialized columns to MCP/CLI | Application (`metric_services.py`) | — | Already reads fact columns; no change needed — it only ever saw nulls because upstream wrote defaults. |
| Enforce domain has no storage import | Test / CI (`tests/test_security_guards.py`) | — | AST import scan; the existing pattern is the blueprint. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `ast` | 3.14 | Import-boundary test (parse + walk) | Already the project's idiom for boundary guards — `tests/test_security_guards.py` uses `ast.parse`/`ast.walk` throughout. |
| `pytest` | per `pyproject.toml` dev extra | Test runner | Project standard; `testpaths = ["tests"]`. |
| `duckdb` | `>=1.5.3,<1.6` | Read-model storage (no API change in this phase) | Only runtime storage engine. |

**No packages are installed in this phase.** No Package Legitimacy Audit required.

## Architecture Patterns

### System Data Flow (target state)

```
materialize_read_model()                       (read_model_materializer.py)
  └─ for each dirty activity:
       _activity_fact(repo, dirty, ...)
          ├─ rows  = repo.stream_hr_velocity_time_rows(activity_id)     ← FETCH (storage)
          │   hr_recovery = calc_hr_recovery(rows)                       ← COMPUTE (pure domain)
          ├─ rows  = repo.stream_altitude_rows(activity_id)             ← FETCH
          │   vspeed = calc_vertical_speed(rows)                         ← COMPUTE
          ├─ rows  = repo.stream_hr_velocity_simple_rows(id, VEL_MOVING)← FETCH
          │   drift = calc_cardiac_drift(rows, sport_type)              ← COMPUTE
          ├─ median = repo.activity_median_heartrate(activity_id)       ← FETCH
          │   hrr   = calc_hrr_pct(median, hr_rest, hr_max_observed)    ← COMPUTE (reuse line-141 hr_max)
          └─ return {... real columns instead of None/0 ...}
                 └─ repo.upsert_activity_metric_fact(fact)               ← STORE

_materialize_rolling_facts()  ── already SELECTs hr_recovery_median_rate / cardiac_drift_pct
                                  → rolling medians auto-populate, NO new code
```

### Pattern 1: Pure function over plain data → dataclass (mirror `training.py`)
**What:** Functions take plain lists/dicts/scalars, return a frozen-ish dataclass or `None`, never
touch `conn`/`repo`.
**Why:** This is the established clean-module style — `training.py::forward_simulate(...) -> list[SimDay]`,
`calc_banister(daily_trimp) -> BanisterResult`. The result dataclasses already exist in `types.py`
(`HrRecovery`, `VerticalSpeed`, `CardiacDriftResult`) and need no changes.

### Pattern 2: Fetch/compute split at the materializer seam
**What:** Move the `repo = repository_from_connection(conn); rows = repo.stream_*(...)` lines OUT of
`metrics.py` into the caller (`_activity_fact`), leaving only the row-processing math in the pure function.
**Verified mechanics of the current coupled functions:**
- `calc_hr_recovery(conn, activity_id)` → calls `repo.stream_hr_velocity_time_rows(activity_id)` then
  pause-detection math. Pure form: `calc_hr_recovery(rows)`.
- `calc_vertical_speed(conn, activity_id)` → `repo.stream_altitude_rows(activity_id)` then ascent sum.
  Pure form: `calc_vertical_speed(rows)`.
- `calc_cardiac_drift(conn, activity_id, sport_type)` → `repo.stream_hr_velocity_simple_rows(activity_id,
  VEL_MOVING)` then Jenks via `cardiac_drift._drift_algo`. Pure form: `calc_cardiac_drift(rows, sport_type=None)`
  (canonical signature — `sport_type` defaults to `None`; the only caller always passes `activity.sport_type`).
  (Note: it already imports `from mcp_strava.cardiac_drift import cardiac_drift` — a domain module, allowed.)
- `hrr_pct` is computed INLINE inside `enrich_activity` (lines 354–364), not in a standalone function.
  Extract it as new pure `calc_hrr_pct(median_hr, hr_rest, hr_max) -> float | None`.

### Anti-Patterns to Avoid
- **Re-fetching `hr_max` all-time for hrr_pct.** The old inline code used `repo.max_heartrate()`
  (all-time). Decision (locked): use `hr_max_observed = repo.max_heartrate_to_date(activity_day)` already
  computed at `_activity_fact` line 141 — consistent with how zone bounds/TRIMP derive `hr_max_used`.
  This is also stored as `hr_max_used` provenance, so hrr_pct stays consistent with the row's own zones.
- **Leaving a `mcp_strava.db` import in `metrics.py`.** That single import (line 5) is the requirement
  violation; it must be gone, and the new boundary test must fail if it (or `mcp_strava.adapters.duckdb`)
  ever returns.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stream row fetching | New SQL in metrics.py | Existing `repo.stream_*_rows` (verified signatures below) | Already implemented, tested, and on the storage tier. |
| Import-boundary scan | regex over source | `ast.parse` + the existing `_import_violations(rel_path, prefixes)` helper | The helper (test_security_guards.py lines 208–227) already handles `import X`, `from X import`, and `from mcp_strava import X` forms. Reuse it; just extend `read_modules` and the disallowed prefix tuple. |
| Median / percentiles | new code | existing dataclass math already in `calc_hr_recovery` | Pure function already computes median rate internally. |

## Verified Repository Method Signatures (storage tier — call from materializer, NOT from metrics)

| Method | Signature | Returns | Used for |
|--------|-----------|---------|----------|
| `stream_hr_velocity_time_rows` | `(activity_id: int)` | rows `{time_offset, heartrate, velocity}` ordered by time | `calc_hr_recovery` |
| `stream_altitude_rows` | `(activity_id: int)` | rows `{time_offset, altitude}` ordered by time | `calc_vertical_speed` |
| `stream_hr_velocity_simple_rows` | `(activity_id: int, min_velocity: float)` | rows `{heartrate, velocity}` ordered by time | `calc_cardiac_drift` (pass `Config.Thresholds.VEL_MOVING`) |
| `activity_median_heartrate` | `(activity_id: int)` | `float | None` | `calc_hrr_pct` |
| `max_heartrate_to_date` | `(activity_day: str)` | `int | None` | hr_max source — **already called at `_activity_fact` line 141** as `hr_max_observed`; reuse, don't re-call |

## Verified Default Columns to Populate (`_activity_fact`, lines 190–205)

These 14 columns currently hold hardcoded defaults and must be replaced with computed values (the
count is 14, not 13 — `cardiac_drift_significant` defaults to `0` and is handled specially via
`1 if .is_significant else 0`, not a direct field read, but it IS one of the hardcoded defaults to wire):

| Column | Default now | Source (pure fn → field) |
|--------|-------------|--------------------------|
| `hr_recovery_pause_count` | `0` | `calc_hr_recovery(rows).pauses_found` |
| `hr_recovery_total_rest_sec` | `0` | `.total_rest_sec` |
| `hr_recovery_median_rate` | `None` | `.median_rate` |
| `hr_recovery_best_rate` | `None` | `.best_rate` |
| `hr_recovery_worst_rate` | `None` | `.worst_rate` |
| `hr_recovery_avg_rate` | `None` | `.avg_rate` |
| `vertical_speed_vmh` | `None` | `calc_vertical_speed(rows).vmh` |
| `vertical_speed_total_ascent_m` | `None` | `.total_ascent_m` |
| `vertical_speed_duration_hours` | `None` | `.duration_hours` |
| `cardiac_drift_pct` | `None` | `calc_cardiac_drift(rows, sport).drift_pct` |
| `cardiac_drift_severity` | `None` | `.severity` |
| `cardiac_drift_significant` | `0` | `1 if .is_significant else 0` |
| `cardiac_drift_quality` | `None` | `.quality` |
| `hrr_pct` | `None` | `calc_hrr_pct(median_hr, hr_rest, hr_max_observed)` |

**Each pure function returns `None` when data is insufficient** (mirrors current behavior) — the
materializer must keep the column at its default in that case (None-safe access).

## Runtime State Inventory (refactor phase — required)

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | Live DuckDB `data/strava.duckdb` (`/opt/docker/mcp-strava/data/strava.duckdb`): `activity_metric_facts` rows currently hold the 13 default values (null/0). | **Data migration (operator-run, post-deploy):** re-materialize the read model so columns recompute null → real. This is CONTEXT.md scope item 7 (LIVE OPS), NOT a code task. The protected read-only backup `~/backups/mcp-strava-safe/` must remain untouched; confirm intact before re-materialize. |
| **Live service config** | None — no external service stores these strings. | None — verified: metrics are internal DuckDB columns. |
| **OS-registered state** | None — verified: no systemd unit / scheduler references these metric names. | None. |
| **Secrets / env vars** | `MCP_STRAVA_HR_REST` is read for hrr_pct (athlete resting HR) — name unchanged, code-read only. | None — name and consumer unchanged. |
| **Build artifacts** | None — pure source edit, no package rename / egg-info. | None. |

**The canonical question:** after the code change, the live DuckDB still has default-valued fact rows
until the operator re-materializes. That is the one runtime-state action, and it is operator-run by design.

## Dead Code Verification (must confirm before deletion)

Verified this session by grep across `src/` and `tests/`:

| Symbol | File | Importers in `src/` | Importers in `tests/` | Disposition |
|--------|------|---------------------|------------------------|-------------|
| `enrich_activity` | metrics.py | **none** | test_smoke.py:12 (import), test_metric_services.py:251 (negative-assert list), test_security_guards.py:292/490/495 (negative-assert) | Delete from src; update test_smoke import; the negative-assert references are fine to KEEP (they assert it is NOT called) but `hasattr`-guarded so they degrade gracefully. |
| `calc_decoupling` | metrics.py | **none** | test_smoke.py:148 | Delete; remove `test_calc_decoupling`. |
| `_decoupling_invalid` | metrics.py | **none** | test_smoke.py:128 | Delete; remove `test_decoupling_invalid`. |
| `calc_decoupling_with_gate` | metrics.py | **none** | test_smoke.py:12 (import) | Delete; update import. |
| `_fetch_decoupling_rows` | metrics.py | **none** | none | Delete. |
| `calc_efficiency_factor` | metrics.py | **none** | test_smoke.py:12 (import) | Delete; update import. |
| `get_daily_trimp_history` | db.py:241 | **none** | test_smoke.py:11 (import); test_security_guards.py:88 (already in `legacy_db_imports` forbidden set for cli.py) | Delete from db.py; update test_smoke import; the security-guard forbidden-set reference stays (it correctly forbids re-importing it in cli.py). |

**Note on `DecouplingResult`:** the dataclass in `types.py` (line 284) becomes unused once
`calc_decoupling*` are deleted, AND `test_smoke.py::test_imports` imports it (line 10). Discretion: the
phase may leave `DecouplingResult` in `types.py` (harmless) but MUST update the test_smoke import line.
Simplest: drop `DecouplingResult` from the test_smoke import and leave the dataclass defined (low risk),
or delete both. Recommend leaving the dataclass (avoids touching `types.py` and any re-exports) and
fixing only the test import.

## Common Pitfalls

### Pitfall 1: Boundary test too narrow / false-green
**What goes wrong:** Extending only the module list but not the disallowed-prefix tuple (or vice versa)
leaves the leak class open.
**How to avoid:** The new test must add BOTH `mcp_strava.db` and `mcp_strava.adapters.duckdb` to the
disallowed prefixes AND add `hr_zones`, `sports`, `cardiac_drift` (in addition to existing `training`,
`metrics`) to `read_modules`. Verify the test FAILS first (RED) by running it before removing the
`metrics.py` import — it must catch the existing line-5 violation.
**Warning sign:** Test passes before the `metrics.py` import is removed → the guard isn't actually checking `db`.

### Pitfall 2: `_import_violations` prefix collision
**What goes wrong:** `mcp_strava.db` as a prefix also matches nothing unexpected, but note the helper
matches `from mcp_strava import db` via its `mcp_strava.{alias}` branch (line 222–226). Good — that form
is covered. But a domain module legitimately importing a *sibling domain* module
(e.g. `metrics.py` imports `from mcp_strava.cardiac_drift import cardiac_drift`) must NOT be forbidden.
**How to avoid:** Only forbid storage/adapter prefixes (`mcp_strava.db`, `mcp_strava.adapters.duckdb`)
plus the already-forbidden `mcp_strava.adapters.strava`, `mcp_strava.refresh`. Do NOT forbid
`mcp_strava` broadly or sibling domain modules.

### Pitfall 3: Deleting code before tests are updated → red suite mid-phase
**What goes wrong:** Removing `enrich_activity`/`get_daily_trimp_history` while `test_smoke.py` still
imports them breaks collection.
**How to avoid:** Order the wave so test updates land with (or before) the deletions. TDD order:
pure-fn tests + boundary test first; extraction + wiring; then deletions + test_smoke import fixes in the
same task that deletes.

### Pitfall 4: hrr_pct hr_max regression
**What goes wrong:** Using all-time `max_heartrate()` (old behavior) instead of `max_heartrate_to_date`
changes hrr_pct values vs. what zones use, creating internal inconsistency.
**How to avoid:** Locked decision — pass the line-141 `hr_max_observed` into `calc_hrr_pct`. Document in
the action and the registry calc text already says "observed_hr_max" (metric_registry.py line 172) — so
this aligns the code WITH the documented contract.

## Code Examples

### Pure function target shape (mirrors training.py)
```python
# Source: mirror of src/mcp_strava/training.py::forward_simulate style
def calc_hr_recovery(rows: list[dict]) -> HrRecovery | None:
    """Pure: pause-detection + HR-drop math over pre-fetched HR/velocity/time rows."""
    # ... identical body to current calc_hr_recovery minus the repo.stream_* fetch
def calc_hrr_pct(median_hr: float | None, hr_rest: float | None, hr_max: float | None) -> float | None:
    if median_hr is None or hr_rest is None or hr_max is None or float(hr_max) <= hr_rest:
        return None
    return round((median_hr - hr_rest) / (float(hr_max) - hr_rest) * 100, 1)
```

### Boundary test extension (mirrors existing test at line 374)
```python
# Source: tests/test_security_guards.py::test_read_modules_do_not_import_strava_or_refresh
def test_read_modules_do_not_import_storage_strava_or_refresh() -> None:
    read_modules = [
        "src/mcp_strava/training.py", "src/mcp_strava/metrics.py",
        "src/mcp_strava/cardiac_drift.py", "src/mcp_strava/hr_zones.py",
        "src/mcp_strava/sports.py",
    ]
    disallowed = ("mcp_strava.adapters.strava", "mcp_strava.refresh",
                  "mcp_strava.db", "mcp_strava.adapters.duckdb")
    violations = []
    for rel in read_modules:
        violations.extend(_import_violations(rel, disallowed))
    assert violations == []
```

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pytest | running the suite | ✓ (dev extra) | per pyproject | — |
| duckdb | materializer tests | ✓ | >=1.5.3,<1.6 | — |
| `just` | `just test` convenience | likely ✓ (Justfile present) | — | `PYTHONPATH=src python -m pytest` |

No external/network dependencies. Pure code+test change.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| Config file | `pyproject.toml` |
| Quick run command | `PYTHONPATH=src python -m pytest tests/test_smoke.py tests/test_security_guards.py -x -q` |
| Full suite command | `just test` (≡ `PYTHONPATH=src python -m pytest -q`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| Core/domain separation | Domain modules import no storage/adapter | unit (AST) | `PYTHONPATH=src python -m pytest tests/test_security_guards.py -k storage_strava_or_refresh -x` | ⚠ extend existing (test_security_guards.py line 374) |
| fix unmaterialized metrics (pure fns) | `calc_hr_recovery/vertical_speed/cardiac_drift/hrr_pct` compute correctly from plain data | unit | `PYTHONPATH=src python -m pytest tests/test_metrics_pure.py -x` | ❌ Wave 0 (new file) |
| fix unmaterialized metrics (wiring) | `_activity_fact` writes non-default hr_recovery_*/vertical_speed_*/cardiac_drift_*/hrr_pct | integration | `PYTHONPATH=src python -m pytest tests/test_read_model_materialization.py -k populat -x` | ⚠ extend existing (test_read_model_materialization.py) |
| no regression | TRIMP / zones / cardiac_cost values unchanged | regression | `PYTHONPATH=src python -m pytest tests/test_read_model_materialization.py tests/test_metric_registry.py -x` | ✅ existing |

### Sampling Rate
- **Per task commit:** `PYTHONPATH=src python -m pytest tests/test_metrics_pure.py tests/test_security_guards.py -x -q`
- **Per wave merge:** `just test` (full suite)
- **Phase gate:** Full suite green (no regression in TRIMP/zones/cardiac_cost) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_metrics_pure.py` — unit tests for `calc_hr_recovery`, `calc_vertical_speed`,
      `calc_cardiac_drift`, `calc_hrr_pct` (pure, plain-data inputs).
- [ ] Extend `tests/test_security_guards.py` — storage-boundary guard (RED before metrics.py import removed).
- [ ] Extend `tests/test_read_model_materialization.py` — assert the 13 columns are non-default after
      materialization (the existing `_seed_dirty_activity_with_streams` seeds 180 rows incl. altitude,
      sufficient to exercise hr_recovery / vertical_speed / cardiac_drift paths).

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface touched. |
| V3 Session Management | no | — |
| V4 Access Control | no | Local single-user service. |
| V5 Input Validation | minimal | Inputs are internal DuckDB stream rows already validated at ingest; pure functions guard against insufficient data (return None). |
| V6 Cryptography | no | None. |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via stream fetch | Tampering | N/A — repo methods use parameterized queries (`?` placeholders, verified). No new SQL added. |
| Data integrity: re-materialization overwrites live facts | Tampering | Operator confirms read-only backup `~/backups/mcp-strava-safe/` intact before re-materialize; DuckDB single-writer respected (owner-driven). |
| Architectural erosion (domain re-couples to storage) | Tampering | The new import-boundary test is itself the mitigation — it fails CI if a storage import returns. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | (none) | — | All claims verified against the codebase this session. |

**This table is empty:** every claim above was verified by reading the actual source. No user confirmation needed.

## Open Questions (RESOLVED)

1. **Keep or delete `DecouplingResult` dataclass after `calc_decoupling*` removal?**
   - RESOLVED: Leave the `DecouplingResult` dataclass defined in `types.py` (zero risk, avoids touching
     `types.py` exports) and drop it from the `test_smoke.py::test_imports` import line. Plan 10-04 Task 2
     implements exactly this (removes `DecouplingResult` from the test import; does not touch `types.py`).

## Sources

### Primary (HIGH confidence)
- Codebase (read this session): `src/mcp_strava/metrics.py`, `training.py`, `db.py`,
  `adapters/duckdb/read_model_materializer.py`, `adapters/duckdb/repository.py` (lines 1293–1452),
  `application/metric_registry.py`, `types.py` (lines 260–334),
  `tests/test_security_guards.py`, `tests/test_smoke.py`, `tests/test_metric_services.py`,
  `tests/test_read_model_materialization.py`.
- `.planning/phases/10-.../CONTEXT.md` — locked decisions (verified investigation).
- `AGENTS.md` — project constraints (data preservation, `just test`, MCP boundary).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; stdlib + existing pytest/duckdb.
- Architecture: HIGH — fetch/compute seam and repo signatures verified line-by-line.
- Pitfalls: HIGH — derived from reading the exact current code and existing tests.

**Research date:** 2026-05-29
**Valid until:** 2026-06-28 (stable internal-refactor scope; no fast-moving externals)
