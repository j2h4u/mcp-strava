---
phase: 6
reviewers: [opencode, claude]
reviewed_at: "2026-05-22T21:29:30+05:00"
plans_reviewed:
  - .planning/phases/06-full-fidelity-strava-mirror/06-01-PLAN.md
  - .planning/phases/06-full-fidelity-strava-mirror/06-02-PLAN.md
  - .planning/phases/06-full-fidelity-strava-mirror/06-03-PLAN.md
  - .planning/phases/06-full-fidelity-strava-mirror/06-04-PLAN.md
---

# Cross-AI Plan Review - Phase 6

## Invocation

- Requested reviewer set: `--opencode --claude`
- Invoked reviewers: `opencode`, `claude`
- OpenCode command used absolute binary path because `/home/j2h4u/.opencode/bin/opencode` was installed but not on `PATH`.
- Reviewers were launched concurrently against the same `/tmp/gsd-review-prompt-06.md` prompt.
- Prompt constraints included: MCP remains read-only metrics/analytics only; no MCP sync/admin/debug/raw/SQL/backfill/status/coverage tools; SQLite remains primary; DuckDB deferred; stream storage is wide plus extra JSON; canonical GPS is `lat`/`lng`; no full Strava resync; resumable rate-limit-aware stream backfill is local admin CLI/runtime only.

## Consensus Summary

Both reviewers agreed that the Phase 6 decomposition is directionally sound: schema and coverage inventory first, generalized stream ingest second, canonical GPS migration third, and stream-channel backfill last. Both reviews also agreed that the plan preserves the major phase boundaries: SQLite remains the operational mirror, DuckDB is deferred, MCP stays read-only, and full Strava resync is not part of the phase.

The unresolved risk is mostly in migration and merge mechanics. The reviews found that the plans need tighter contracts for versioned schema inventory, explicit migration versioning, GPS table rebuild/precedence behavior, atomic stream point plus channel metadata writes, backfill merge semantics that cannot overwrite existing values, and checkpoint routing for the new stream-channel backfill stages.

### Agreed Strengths

- Correct wave ordering and dependency sequencing across 06-01 through 06-04.
- Strong traceability to Phase 6 decisions and roadmap constraints.
- Reuse of established backup, preflight, post-check, and parity patterns.
- MCP read-only boundary is reinforced rather than expanded.
- Docker/runtime validation remains separate from temp-DB repo-local tests.
- Backfill is scoped away from full account resync and toward missing stream-channel coverage.

### Agreed Concerns

- HIGH: Migration versioning and schema inventory need an explicit versioned contract across v3 and v4.
- HIGH: GPS canonicalization needs a precise table-drop/rebuild strategy and conflict precedence rule before implementation.
- HIGH: Backfill must merge missing channel values without deleting or replacing existing stream rows.
- HIGH: Stream point replacement and channel metadata writes need one atomic consistency contract.
- HIGH: New stream-channel backfill checkpoint stages must be integrated with existing backfill-stage routing.

### Divergent Views

- OpenCode emphasized repository write hazards: `replace_stream_rows_chunked()` delete/rewrite behavior, `INSERT OR REPLACE` risks, and metadata cleanup semantics.
- Claude emphasized migration mechanics: explicit migration version 4, SQLite table rebuild strategy, scalar GPS precedence, malformed `latlng` disposition, and DB-size effects from `values_json`.
- OpenCode rated the stage-routing overlap as HIGH; Claude rated the same area MEDIUM. It is kept as HIGH here because an incorrect checkpoint state can block or misroute refresh/backfill execution.

CYCLE_SUMMARY: current_high=7

## Current HIGH Concerns

- HIGH-01: Stream row replacement and channel metadata writes are not specified as one atomic transaction or safe ordering, so a partial failure could delete stream points while leaving metadata incomplete.
- HIGH-02: Stream-channel backfill lacks a merge/update-only write strategy and could accidentally overwrite or delete existing stream rows when enriching missing channels.
- HIGH-03: New stream-channel backfill stages may collide with existing `STREAMS_BACKFILL`/`COMPLETE_BACKFILL` routing unless checkpoint helper functions and runtime rejection paths are explicitly extended.
- HIGH-04: Schema inventory validation is not versioned, so v3 requiring `latlng` and v4 removing `latlng` could break preflight or post-check behavior between waves.
- HIGH-05: GPS canonicalization does not explicitly define migration version 4 or idempotent `MIGRATIONS` sequencing for the `latlng` removal step.
- HIGH-06: The SQLite strategy for dropping `latlng` is under-specified; the plan needs to commit to a safe `ALTER TABLE DROP COLUMN` preflight or table rebuild pattern with index/PK preservation.
- HIGH-07: GPS conflict precedence is undefined for rows where scalar `lat`/`lng` and `latlng` JSON disagree, risking silent coordinate changes.

## OpenCode Review

Let me read the critical files directly to ground the review.
Now I have a thorough understanding of the codebase and all four plans. Here is the structured review.

---

# Cross-AI Plan Review: Phase 6 — Full-Fidelity Strava Mirror

## 1. Summary

The four plans are architecturally sound, well-sequenced, and correctly implement the core decisions from CONTEXT.md. The wave ordering (schema/coverage first, then ingest generalization, then GPS migration, then backfill) is the correct dependency chain. The TDD approach is consistent throughout. However, there are several integration gaps between plans — particularly around the temporal overlap of `latlng`/`lat`/`lng` columns, the versioning of schema inventory, and the coupling of channel metadata writes to stream point deletion/replacement. These need resolution before execution.

## 2. Strengths

- **Correct wave dependency ordering**: 06-01 (schema), 06-02 (ingest), 06-03 (GPS), 06-04 (backfill) — each depends on the prior wave's contracts, matching the research recommendations exactly.
- **Strong data-safety discipline**: Every plan with schema mutation includes backup, preflight, parity checks, and fail-closed semantics. Plan 06-03's GPS migration is particularly rigorous with row-count parity, GPS-count parity, and analytics parity snapshots.
- **Consistent boundary enforcement**: All four plans respect the MCP read-only constraint. Plan 06-03 correctly forbids any Strava call during GPS migration. Plan 06-01 and 06-02 never cross the product/admin CLI boundary.
- **Preserves the existing mirror**: No plan proposes deleting existing stream rows or running a full resync. Backfill in 06-04 is scoped to activities that already have stream rows.
- **Decision traceability**: Each plan explicitly maps CONTEXT.md decisions (D-01 through D-28) to implementation tasks.
- **Good test design**: Fake transport tests in 06-02 for unknown keys, uneven channels, and rate limits are well-conceived. Plan 06-04's dry-run tests without transport calls are a solid pattern.

## 3. Concerns

### HIGH Severity

1. **06-01: `replace_stream_rows_chunked` deletion+coupling hazard** — Task 2 states the replace method "deletes and rewrites stream point rows for an activity but also writes channel metadata in the same logical operation." If the channel metadata write fails after the DELETE on stream points, stream data is lost. The transaction boundary is not specified. The DELETE+INSERT on stream points and the channel metadata upsert must be in the same SQLite transaction, or at minimum the channel metadata write must occur *before* the DELETE. The plan should specify ordering: metadata first (idempotent upsert), then point replacement.

2. **06-04: Backfill re-fetches full stream response, risks replacing existing rows** — Task 2 says backfill "fetches only missing stream endpoints" but the Strava API endpoint `/activities/{id}/streams?keys=...` returns ALL requested channels, not just missing ones. The plan says "ensure insert/backfill paths do not delete existing rows when only metadata is being enriched" (from 06-02 Task 3). But the current `insert_stream_rows_chunked` uses `INSERT OR REPLACE` which overwrites existing rows by PK, and `replace_stream_rows_chunked` does a full DELETE first. Neither is safe for partial enrichment. The backfill must use an UPDATE-only strategy (or a merge that preserves existing scalar values while adding new `values_json` entries), not the current insert/replace methods. This is a fundamental mismatch that must be addressed in the plan.

3. **06-04: Stage naming collision with existing backfill stages** — The plan proposes `STREAM_CHANNELS_BACKFILL` and `COMPLETE_STREAM_CHANNELS_BACKFILL`, but the existing `checkpoints.py` already has `STREAMS_BACKFILL` (for activities with NO stream rows) and `is_active_backfill_stage()` routes between daily refresh and backfill based on stage names ending in `_backfill`. Adding new stages without touching `is_active_backfill_stage()` and `is_backfill_stage()` will cause the daily refresh to reject running when a stream-channel backfill is in progress, and vice versa. The plan must explicitly extend these routing functions.

4. **06-01/06-03: Schema inventory versioning is underspecified** — `schema.py:REQUIRED_COLUMNS` is a single flat dictionary. Version 2 currently requires both `lat`/`lng` and `latlng`. Version 3 adds `values_json` and `stream_channels`. Version 4 (after Plan 06-03) removes `latlng`. But `validate_required_inventory()` has no version branching — it validates one monolithic `REQUIRED_COLUMNS`. The plans don't specify how to version `REQUIRED_COLUMNS` so that post-migration version 3 correctly requires `latlng` + `values_json`, while version 4 requires `lat`/`lng` + `values_json` but NOT `latlng`. Without this, the preflight will break between waves.

### MEDIUM Severity

5. **06-02: Ambiguous `distance` stream key** — Task 2 adds `distance` to the requested stream keys. In Strava, the `distance` stream channel returns per-point cumulative distance (meters). The plan doesn't specify whether this becomes a scalar column on `streams` or goes into `values_json`. If it becomes a scalar column, schema changes are needed (not mentioned in 06-01). If it goes into `values_json`, that works but users can't aggregate/query it efficiently. The plan must decide.

6. **06-02: `latlng` duplication risk** — Task 2 says `latlng` values are "split into numeric `lat` and `lng` fields for new writes." But `latlng` JSON is also a non-scalar channel that could end up in `values_json` by the "not represented as scalar columns" rule. Since `latlng` IS mapped to scalar columns (`lat`, `lng`), it should be explicitly excluded from `values_json`. The plan should state this explicitly.

7. **06-03: Table rebuild strategy unclear** — Task 2 says "Rebuild the table if SQLite column drop support is not sufficient in this codebase." SQLite 3.35.0+ supports `ALTER TABLE DROP COLUMN`. The plan should check the target SQLite version and decide a strategy. If rebuilding, the column order of the new table may differ, which could break `Config.SQL.TRIMP` if it uses `SELECT *` semantics or positional references. The plan should verify the TRIMP and analytics parity passes against a rebuilt table.

8. **06-01: `upsert_stream_channel_metadata` doesn't address replacement cleanup** — When `replace_stream_rows_chunked` is called for an activity (e.g., during a normal daily refresh), old channel metadata rows should be replaced or cleaned up, not accumulated. The plan mentions "metadata consistency in the same transaction" but doesn't specify whether to DELETE old metadata for the activity first, use UPSERT semantics, or which takes priority when Strava returns fewer channels than previously stored.

9. **06-04: Dry-run and backfill report shape not specified** — The plan mentions `--dry-run` and `--json` flags but doesn't define the output structure. During execution, the executor needs to know exact JSON field names, types, and semantics. The plan should at minimum sketch the output shape.

10. **06-01: `REQUIRED_INDEXES` update timing** — `idx_stream_channels_activity` is mentioned in Task 1 acceptance criteria but not in Task 2's implementation steps. The migration step adding the index should be explicit in Task 2.

### LOW Severity

11. **Plans use `database_path`/settings access patterns inconsistently** — Plan 06-01 Task 3 says `--db <path>` for temp DB inspection, but the existing CLI uses `get_settings().database_path`. Supporting `--db` requires Settings override or a separate connection path. This is manageable but should be noted.

12. **Test fixture version progression between plans** — 06-01 tests create version 2 fixtures → migrate to v3. 06-03 tests create version 2 fixtures → migrate to v3 → migrate to v4. The 06-03 tests could also start from v3 fixtures. Either is fine, but the plans should be consistent about fixture creation strategies.

13. **STRIDE threat ID collisions** — T-06-03 is defined in Plan 06-01 and reused in Plan 06-02. T-06-04 appears in both 06-02 and 06-03. These should be unique per plan for unambiguous traceability.

## 4. Suggestions

- **Add a merge/update stream method to the repository**: For backfill in 06-04, add `update_stream_rows_chunked` or `merge_stream_channel_values` that updates only `values_json` and `stream_channels` metadata without touching existing scalar columns. This is the cleanest fix for concern #2.

- **Version `REQUIRED_COLUMNS` by user_version**: Add a `REQUIRED_COLUMNS_BY_VERSION: dict[int, dict[str, tuple[str, ...]]]` mapping in `schema.py` during 06-01, and update `validate_required_inventory()` to use the version-appropriate inventory. This fixes concern #4 preemptively.

- **Add `is_stream_channel_backfill_stage()` to checkpoints**: Extend `checkpoints.py` with explicit functions for the new stages, and update `run_once` in `runtime.py` to detect incompatible stream-channel backfill states. This fixes concern #3.

- **Specify the backfill merge strategy in 06-04 Task 2**: Add a concrete step: when backfilling channels, fetch the full stream response, extract only the missing channel values as `values_json` updates, use an UPDATE strategy on existing rows (matching by `activity_id, time_offset`), and update channel metadata status.

- **Clarify `distance` stream handling in 06-02**: State that `distance` stream values go into `values_json` (not a new scalar column) since it's not currently used by any analytics path. If needed later, it can be promoted to a scalar column in a future migration.

- **Add explicit `latlng` exclusion from `values_json` in 06-02 Task 2**: After splitting `latlng` into `lat`/`lng`, mark it as excluded from the "non-scalar keys go to values_json" rule to avoid duplication.

- **Sketch the dry-run/backfill output shape in 06-04**: Add a brief JSON schema sketch to give the executor enough information.

## 5. Risk Assessment

**Overall Risk: MEDIUM**

The architecture is well-conceived and the sequencing is correct. The core risk is not in the high-level design but in integration details between plans:

1. The **stream point replacement + metadata coupling** in 06-01 and the **re-fetch-and-merge** strategy in 06-04 are the two highest-risk areas. Both involve operations that, if implemented naively, can silently lose mirror data or produce inconsistent metadata.

2. The **schema versioning gap** (a flat `REQUIRED_COLUMNS` without version branching) is a latent defect that will surface when 06-03 tries to remove `latlng` from inventory while 06-01's migration tests expect it to remain.

3. The **stage naming collision** in 06-04 is a correctness issue in the checkpoint routing logic that could cause the daily refresh to reject runs or the backfill to overwrite daily checkpoint state.

None of these are architectural rejections. They are all fixable with small plan adjustments before execution. With the suggestions above applied, the plans would be solid for execution.

Justification: The plans achieve the phase goals (lossless normalized mirror, generalized ingestion, canonical GPS, resumable backfill), respect all constraints (SQLite-only, no full resync, MCP read-only, backup/preflight), and follow the established codebase patterns. The HIGH concerns are integration-edge issues, not design flaws.

---

## Claude Review

## 1. Summary

The Phase 6 plans cover the full surface of "lossless normalized stream mirror" coherently, with a sensible 4-wave decomposition: schema → ingest → GPS canonicalization → backfill. Decision traceability is strong, TDD is consistently applied, threat models are present, and the MCP read-only boundary is reinforced rather than weakened. The main gaps are in *migration mechanics* (version numbering across waves, SQLite table-rebuild strategy for latlng removal, partial-failure recovery), a few *ambiguous semantics* around channel metadata authority and dry-run estimation, and *under-specified storage implications* for `values_json`.

## 2. Strengths

- Wave ordering is correct: schema/coverage before ingest, ingest before GPS migration, GPS migration before backfill. Each plan's `depends_on` reflects the real coupling.
- Decision traceability blocks tie nearly every constraint (D-01..D-28) to a specific task.
- TDD discipline: every plan starts with a failing-tests task, including assertions on guardrails (e.g., "no `/athlete/activities` calls during backfill", "no live Strava transport during GPS migration").
- MCP boundary is enforced affirmatively (Plan 06-04 Task 3 adds forbidden-name guards for `mirror-coverage`, `backfill-streams`, `coverage`, `status`, etc.) — not just by omission.
- Backup/preflight/post-check/parity pattern from Phase 2 is reused rather than reinvented (Plan 06-03 Task 2 reuses `run_migrations()` backup flow and existing `ParitySnapshot`).
- Repo-local tests vs. live-runtime tests are explicitly separated; `/opt/docker/mcp-strava` is treated as Docker-first verification surface (D-23).
- DuckDB stays deferred with rationale recorded (D-25..D-28); no implementation work touches it.
- Backfill candidate query is correctly scoped to activities that already have stream rows but missing channel data, not a full account walk (D-18).

## 3. Concerns

### HIGH

- **HIGH — Migration version sequencing across 06-01 and 06-03 is implicit.** Plan 06-01 Task 2 explicitly introduces `MIGRATIONS` target version `3` (adds `values_json` + `stream_channels`, keeps `latlng`). Plan 06-03 Task 2 then "transforms `streams` into the final Phase 6 shape without `latlng`" but never names a version `4`, never updates `MIGRATIONS`, and never says whether this is an in-place mutation of v3 or a new step. Without an explicit `4: _gps_canonicalization` entry, idempotency tests (cf. `test_safe03_baseline_migration_sets_user_version_to_2_idempotently_d02`) will not exist and re-running `run_migrations()` becomes undefined. Specify the target version and add to `MIGRATIONS` keyed by integer.

- **HIGH — SQLite table-rebuild strategy for dropping `latlng` is hand-waved.** Plan 06-03 Task 2 says "Rebuild the table if SQLite column drop support is not sufficient in this codebase." SQLite ≥ 3.35 supports `DROP COLUMN` for many cases, but **fails on indexed columns or columns referenced in triggers/views**. The `streams` table has `idx_streams_act` and a composite PK `(activity_id, time_offset)` that the migration must preserve. Commit to a strategy explicitly: either (a) `ALTER TABLE streams DROP COLUMN latlng` after asserting SQLite version + that latlng is not indexed, or (b) the canonical `CREATE TABLE streams_new (...); INSERT INTO streams_new SELECT ... FROM streams; DROP TABLE streams; ALTER TABLE streams_new RENAME TO streams; CREATE INDEX idx_streams_act ...;` pattern. Option (b) is safer and version-agnostic but rewrites the entire table — a real cost on large mirrors that should be acknowledged.

- **HIGH — GPS migration "rows with both lat/lng and latlng" precedence is undefined.** Plan 06-03 Task 1 lists the case explicitly but the acceptance criteria do not say which source wins on conflict. Pick a rule and test it: "if scalar `lat`/`lng` are non-null, keep them; never overwrite from latlng." Without this, the migration can silently change coordinate values for rows where the two sources disagree (e.g., due to historical bugs or differing precision).

### MEDIUM

- **MEDIUM — `values_json` storage cost is not budgeted.** With `watts`, `temp`, `distance` added to `STREAM_KEYS` (Plan 06-02) and per-point JSON serialization, each stream row gains a JSON blob even when the values are scalar. For a typical mirror with O(hundreds of activities × thousands of points), `values_json` can balloon DB size substantially. Mitigations to consider in the plan: (a) `NULL` when no extra channels are returned, (b) compact key naming, (c) move `distance` to a scalar column if it is universally returned, (d) document expected size growth in the migration post-check. At minimum, the plan should assert "`values_json` is NULL when no non-projected channels are present" so the common case doesn't pay JSON overhead.

- **MEDIUM — Channel-name → scalar-projection mapping is implicit.** D-06 enumerates scalar columns by *projection name* (`heartrate`, `velocity`, `grade`, `gap_speed`, `gap_distance`, `is_moving`) but Strava returns channels under *API names* (`heartrate`, `velocity_smooth`, `grade_smooth`, `grade_adjusted_speed`, `grade_adjusted_distance`, `moving`). Plan 06-02 Task 2 says "Build channel metadata for returned channels and requested-but-absent channels" but never pins the canonical mapping in one place. Add an explicit constant (e.g., `STREAM_CHANNEL_TO_COLUMN: dict[str, str]`) so future readers and tests have a single source of truth, and so `stream_channels.channel_key` consistently uses Strava's name while scalar columns continue to use projection names.

- **MEDIUM — Channel metadata authority during normal refresh vs. backfill is fuzzy.** Plan 06-02 Task 3 says replace-on-refresh "leaves metadata aligned with the latest response" and Plan 06-04 Task 2 has backfill writing metadata too. What happens when a daily refresh response is partial (e.g., temp missing) for an activity that previously had temp metadata recorded? Does daily refresh downgrade the metadata to `status='unavailable'`, or only backfill touches metadata? Pick one model and make it testable. Suggestion: daily refresh writes metadata reflecting *that* response; backfill only fills gaps. State this in 06-02 Task 3 acceptance criteria.

- **MEDIUM — `batch_id` in `stream_channels` is unspecified.** Plan 06-01 Task 1 requires the column but never defines what value goes in. Options: `sync_log.id`, a UUID per refresh run, or the refresh checkpoint cursor. Either define it (e.g., FK to `sync_log.id`) or drop it from the schema until a concrete use case appears.

- **MEDIUM — Partial-failure recovery during the latlng-removal migration is undefined.** If post-check parity fails after the table has been rebuilt but before `COMMIT`, the user is left with backup but no automated restore. The existing `run_migrations()` flow raises but does not restore from backup. Plan 06-03 should either (a) wrap the whole rebuild in a single transaction (SQLite supports DDL inside transactions, but `VACUUM` / some `PRAGMA` operations do not), or (b) document the manual restore path explicitly and surface the backup location in the failure message.

- **MEDIUM — `admin backfill-streams` vs. existing `admin backfill` collision.** Phase 4 already registered `backfill: cmd_backfill` in `ADMIN_COMMANDS` (cli.py:658). Plan 06-04 says "Keep existing `run_backfill` semantics for older admin backfill if still needed" — ambiguous. Decide explicitly: keep `admin backfill` (legacy) and add `admin backfill-streams` (new, channel-scoped), or replace. If kept, document the distinction in `--help`. The two commands diverging silently is a footgun.

- **MEDIUM — Malformed `latlng` JSON disposition is contradictory.** Plan 06-03 Task 1 says "malformed `latlng` does not abort the migration and is counted in a post-check warning *or* failure list." A failure list normally fails the migration; a warning does not. Choose one: malformed rows pass (recorded as a warning count, no lat/lng populated, row preserved) or fail (migration aborts with backup intact). The "or" wording makes the test non-binding.

- **MEDIUM — Backfill checkpoint stages overlap with existing ones.** Existing `Stage` enum has `STREAMS_BACKFILL` / `DETAILS_BACKFILL` / `COMPLETE_BACKFILL` (checkpoints.py:14-17). Plan 06-04 Task 2 proposes adding `STREAM_CHANNELS_BACKFILL` / `COMPLETE_STREAM_CHANNELS_BACKFILL`. Need to: (a) update `is_active_backfill_stage` and `is_backfill_stage`, (b) decide whether `run_backfill` (the v1 backfill path that re-fetches missing whole-stream activities) is still reachable via CLI, and (c) ensure `run_once` rejects incompatible new stages with a clear error like it currently does for v1 backfill (runtime.py:57).

### LOW

- **LOW — Coverage output field name drift.** Plan 06-01 Task 3 lists `activities_with_streams` while existing repository uses `activities_missing_streams`. Not a bug, but consider standardizing on one polarity for readability.

- **LOW — `tests/test_full_fidelity_mirror.py` is touched by all four plans.** Likely fine, but consider splitting per concern (e.g., `test_stream_schema.py`, `test_gps_migration.py`, `test_stream_backfill.py`) to keep churn isolated across waves.

- **LOW — Plan 06-03 lists `src/mcp_strava/metrics.py` in files_modified** but the code context doesn't show metrics.py using `latlng`. Verify before assuming the file will be touched; if not used, drop from the list.

- **LOW — Plan 06-04 dry-run `estimated_api_calls`** semantics not defined. Presumably one call per candidate activity (streams endpoint). State this so the test can assert it.

- **LOW — Re-running migration v3 on a v3 DB with `values_json` already present.** Plan 06-01 Task 2 acceptance criteria mention version 3 creation but not idempotency. Existing pattern (`CREATE TABLE IF NOT EXISTS`, `INSERT OR IGNORE`) handles this; please match it for `ALTER TABLE streams ADD COLUMN values_json` which is *not* idempotent without a guard.

## 4. Suggestions

- In Plan 06-03, add a top-level decision section that pins: migration version = 4, table-rebuild strategy = explicit `CREATE TABLE streams_new` + copy + drop + rename, lat/lng precedence = scalar wins over latlng, malformed-latlng disposition = warning + preserved row + null GPS.
- In Plan 06-01 Task 2, add an acceptance criterion: "Running `run_migrations()` against an already-v3 database is a no-op and preserves all row counts."
- In Plan 06-02, introduce an explicit `STREAM_CHANNEL_TO_COLUMN` mapping constant in `_sync_ops.py` (or `types.py`) and assert in tests that every Strava channel in the requested set is either in the mapping or persisted via `values_json`.
- In Plan 06-04 Task 2, add an acceptance criterion: "Daily refresh stream writes update `stream_channels` to reflect the current response (`status='available'` for present channels, `status='unavailable'` for requested-but-missing). Backfill only fills gaps and never downgrades `status='available'` rows."
- For `values_json` size, add a post-migration sanity check or metric: e.g., emit DB size before/after in migration output. Operator can decide whether to act on growth.
- Document the legacy `admin backfill` lifecycle: keep, deprecate, or remove. If keeping, add a `--help` note distinguishing it from `admin backfill-streams`.
- Consider whether the `stream_channels` table needs an FK to `activities(id)` with `ON DELETE CASCADE` (or a documented invariant that activities are never deleted from the mirror). This protects coverage queries from dangling channel rows.
- For Plan 06-04 Task 1, add a test asserting backfill respects the existing `RefreshPolicy.regular_refresh_interval_seconds` lease semantics — i.e., backfill cannot run while daily refresh holds the lease and vice versa.

## 5. Risk Assessment

**Overall risk: MEDIUM.**

Justification: The plans are structurally sound and the boundary discipline (MCP read-only, admin-only coverage/backfill, SQLite-only) is well enforced. The medium-rated risks cluster around *migration mechanics* — version numbering, SQLite table-rebuild semantics for `latlng` removal, partial-failure recovery, and channel-metadata authority during regular vs. backfill writes — which are exactly the areas where a mistake silently corrupts or grows the live mirror. None of these are showstoppers; all are addressable by tightening the 06-03 migration plan and adding 2–3 acceptance criteria. With those clarifications, this becomes a LOW-risk phase. As written, the latlng-removal migration alone is the single dimension most likely to cause production rollback if a test gap meets a real-world edge case (e.g., a row with disagreeing scalar lat/lng vs. latlng JSON, or a SQLite version that refuses `DROP COLUMN` on an indexed column).
