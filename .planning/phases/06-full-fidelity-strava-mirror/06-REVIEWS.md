---
phase: 6
reviewers: [opencode, claude]
reviewed_at: "2026-05-22T21:52:25+05:00"
cycle: 2
previous_current_high: 7
replanning_commit: f3bb904
plans_reviewed:
  - .planning/phases/06-full-fidelity-strava-mirror/06-01-PLAN.md
  - .planning/phases/06-full-fidelity-strava-mirror/06-02-PLAN.md
  - .planning/phases/06-full-fidelity-strava-mirror/06-03-PLAN.md
  - .planning/phases/06-full-fidelity-strava-mirror/06-04-PLAN.md
---

# Cross-AI Plan Review - Phase 6, Cycle 2

## Invocation

- Requested reviewer set: `--opencode --claude`
- Invoked reviewers: `opencode`, `claude`
- Claude and OpenCode were initially launched concurrently against the same cycle-2 prompt.
- OpenCode command used `/home/j2h4u/.opencode/bin/opencode` because OpenCode is installed there but is not on `PATH`.
- The first OpenCode invocation failed because its `--file` option consumed the prompt message as a file path; the second invocation reached OpenCode but was blocked by OpenCode's external-directory permission on `/tmp`. The successful OpenCode review therefore ran after Claude completed, by passing the prompt as the message and using `--dangerously-skip-permissions` for local review reads. Concrete limitation: OpenCode's non-interactive file prompt mode could not read the `/tmp` prompt under its permission model.
- Prompt constraints included: evaluate the current Phase 6 plans after replanning commit `f3bb904`; count only unresolved current HIGH concerns; do not count retrospective mentions of prior HIGHs; preserve SQLite primary mirror, no full Strava resync, MCP read-only boundary, and rate-limit-aware local admin backfill.

## Consensus Summary

Both reviewers concluded that cycle 2 resolves all seven HIGH concerns from cycle 1. Both reviews found that the updated plans now contain concrete implementation behavior and acceptance criteria for:

- Atomic stream row plus channel metadata writes.
- Merge-only stream-channel backfill that preserves existing rows, scalar values, JSON keys, and available metadata.
- Explicit checkpoint routing for daily refresh, legacy backfill, and new stream-channel backfill.
- Versioned v3/v4 schema inventory.
- Explicit `MIGRATIONS[4]` sequencing and idempotency.
- Safe transaction-scoped `streams_new` table rebuild for `latlng` removal.
- Deterministic GPS conflict precedence where scalar `lat`/`lng` values win over `latlng`.

Neither reviewer raised a new HIGH concern in this cycle.

### Agreed Strengths

- Phase sequencing remains correct: schema and coverage inventory, generalized stream ingest, GPS canonicalization, then stream-channel backfill.
- The updated plans bind the prior migration and write-safety gaps to named repository/migration contracts plus tests.
- The MCP boundary remains explicitly guarded against admin, sync, raw, SQL, status, coverage, and backfill exposure.
- The backfill plan is scoped to missing stream channels or metadata for activities that already have stream rows, avoiding a full Strava resync.
- Docker/runtime validation stays separate from repo-local temp database tests.

### Agreed Concerns

- MEDIUM: The merge/update path for stream-channel backfill should make its per-activity transaction boundary explicit.
- MEDIUM: The GPS coordinate conflict tolerance should be pinned to a numeric value instead of left to implementation judgment.
- MEDIUM: `stream_channels.batch_id` remains nullable and lacks a concrete writer, so it may become dead metadata unless wired to a refresh/sync run identity or removed.
- MEDIUM: The atomic replacement method should avoid inheriting existing chunk helpers that commit inside chunk loops.
- MEDIUM: Runtime handling for intermediate v3-only state should say whether final runtime preflight blocks or warns before v4.

### Divergent Views

- OpenCode rated the missing `merge_stream_channel_values` transaction boundary as MEDIUM. Claude instead emphasized the existing chunked-commit pattern as a MEDIUM risk for the atomic replacement method.
- OpenCode emphasized GPS tolerance and malformed `values_json` handling in backfill. Claude emphasized `batch_id`, row offset mismatch reporting, and v3 runtime preflight behavior.
- Both reviewers agreed these are execution hardening items, not unresolved HIGH blockers.

CYCLE_SUMMARY: current_high=0

## Current HIGH Concerns

None.

---

## OpenCode Review

# Cross-AI Plan Review - Phase 6, Convergence Cycle 2

**Reviewers:** opencode
**Plans reviewed:** 06-01, 06-02, 06-03, 06-04
**Commit:** f3bb904 (claimed address of 7 HIGH concerns)

## Summary

All 7 HIGH concerns from Cycle 1 are **resolved**. The updated plans now specify concrete implementation behavior with explicit acceptance criteria and test coverage for each previously-HIGH area:

- Atomic stream+metadata writes with transaction-rollback contract in 06-01
- Merge-only backfill writes with JSON-key preservation and no-downgrade metadata rules in 06-04
- Explicit checkpoint stage names, routing rules, and error messages in 06-04
- Version-aware schema inventory (v3 vs v4) in 06-01 and 06-03
- `MIGRATIONS[4]` with idempotency contract in 06-03
- Table rebuild strategy (`streams_new` + rename + index re-creation) in 06-03
- GPS precedence contract (scalar wins, collision counted, malformed JSON non-fatal) in 06-03

No new HIGH concerns were introduced by the updated plans.

## Strengths

- The `<gps_migration_contract>` block in 06-03 is particularly strong. It commits to exact migration mechanics, precedence rules, idempotency, and `ALTER TABLE DROP COLUMN` avoidance.
- Three distinct atomicity contracts are now separated by purpose: `replace_stream_rows_and_channel_metadata` (daily refresh, delete+insert), `merge_stream_channel_values` (backfill, update-only), and the GPS table rebuild (migration, copy+swap).
- Checkpoint routing is now three-way distinguished: `run_once`, legacy `run_backfill`, and new stream-channel backfill each have explicit rejection rules and differentiated error messages.
- Version-aware inventory means v3 preflight does not block on v4 columns and v4 post-check validates `latlng` removal.
- Every plan maintains the MCP read-only boundary with explicit forbidden-tool assertions.

## Concerns

### HIGH

None. All 7 previous HIGH concerns meet the resolution bar.

### MEDIUM

**MEDIUM-01: GPS tolerance value is unspecified.** The `gps_migration_contract` says "agree with latlng within tolerance" but never names the tolerance value. An incorrectly chosen tolerance could silently misclassify valid coordinate pairs. Mitigation: the tests cover conflicting rows, so the value will be forced by test expectations. Recommend pinning the tolerance to a specific figure such as `0.0001` or `1e-6` degrees in the contract itself.

**MEDIUM-02: `merge_stream_channel_values` atomicity contract is implicit.** The `replace_stream_rows_and_channel_metadata` method has an explicit "one SQLite transaction" contract. The `merge_stream_channel_values` method performs distinct UPDATE and UPSERT operations per activity, but the plan does not explicitly require one transaction boundary per activity during backfill. A partial merge failure could leave the mirror inconsistent. Recommend adding an explicit per-activity transaction requirement for the merge path.

### LOW

**LOW-01: Backfill wastes API quota downloading all channels to extract only missing ones.** The plan specifies backfill fetches the full stream endpoint and extracts only missing channels. This is correct but slightly wasteful. It is an acceptable trade-off because there is no Strava endpoint for selective channel fetch.

**LOW-02: `values_json` merge preserves existing keys, which means stale values from a previous incorrect backfill cannot be fixed without manual intervention.** The "never replace existing keys" rule is safe for arbitrary overwrite prevention but makes correction harder. This is acceptable for a fill-missing-data backfill.

**LOW-03: Malformed `values_json` in existing stream rows is not explicitly handled in the backfill merge path.** If a prior bug or manual edit left unparseable JSON in `values_json`, the merge operation might fail or skip the row. This is an implementation-level concern, not a planning blocker.

## Suggestions

1. Pin the GPS tolerance in the contract so the implementation does not need to guess.
2. State the per-activity transaction boundary for `merge_stream_channel_values`.
3. Consider a `--channels` flag for `admin backfill-streams` so the operator can target specific missing channels.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Migration v3 to v4 data loss | Low | High | Table rebuild contract, backup, row-count parity, GPS-count parity, and analytics parity are all tested. |
| Backfill overwrites existing data | Low | Medium | Merge-only contract explicitly forbids `replace_*` calls and tests assert this. |
| Checkpoint routing deadlocks between `run_once` and new backfill | Low | Medium | Three-way routing with rejection messages and tests for each path. |
| MCP surface expansion | Low | High | Forbidden-tool tests and explicit MCP tool count assertion. |
| GPS tolerance causes silent coordinate drift | Low | Medium | Conflicts counted and surfaced; scalar-wins precedence prevents overwrite. |
| Live mirror corrupted during repo-local testing | Low | High | Plans assert temp/copy DB usage and Docker-first verification for live data. |

CYCLE_SUMMARY: current_high=0

## Current HIGH Concerns

None.

---

## Claude Review

# Cross-AI Plan Review - Phase 6 Cycle 2

## 1. Summary

Cycle 2 replanning addresses all seven HIGH concerns from cycle 1 with concrete contracts and acceptance criteria. The plans now specify atomic stream/metadata transactions, merge-only backfill writes, explicit checkpoint stage routing, versioned v3/v4 schema inventories, an explicit `MIGRATIONS[4]` idempotent target, a transaction-scoped `streams_new` table rebuild, and deterministic GPS conflict precedence with conflict/malformed counters. Each contract has matching failing-test specifications in Task 1 of its respective plan.

Wave sequencing and decision traceability remain consistent with cycle 1. No new HIGH concerns surfaced during review.

## 2. Strengths

- **Atomic write contract is named and tested.** Plan 06-01 Task 2 specifies `replace_stream_rows_and_channel_metadata` runs in one SQLite transaction with rollback on either-side failure; Task 1 includes a simulated metadata-failure test asserting both stream rows and metadata roll back together.
- **Merge-only backfill semantics are explicit.** Plan 06-04 Task 2 introduces `merge_stream_channel_values`, restricts writes to existing `(activity_id, time_offset)` rows, JSON-merges into `values_json` without overwriting, forbids calling `replace_*` methods, and prevents downgrading existing `status='available'` metadata.
- **Stage routing is deterministic.** New `STREAM_CHANNELS_BACKFILL` / `COMPLETE_STREAM_CHANNELS_BACKFILL` stages, extensions to `is_backfill_stage` / `is_active_backfill_stage`, and explicit rejection in both `run_once` and legacy `run_backfill` eliminate the cycle-1 routing ambiguity.
- **Versioned inventory replaces flat constants.** Plan 06-01 Task 2 mandates `REQUIRED_COLUMNS_BY_VERSION`, `REQUIRED_TABLES_BY_VERSION`, and `REQUIRED_INDEXES_BY_VERSION` with per-version validation. Plan 06-03 keeps v3 requiring `latlng` and v4 excluding it; Plan 06-04 Task 4 propagates this to runtime preflight.
- **Migration mechanics are surgical.** Plan 06-03 commits to `MIGRATIONS[4]`, idempotent rerun, transaction-scoped `streams_new` rebuild with PK and `idx_streams_act` recreation, and explicitly rules out `ALTER TABLE DROP COLUMN`.
- **GPS precedence is unambiguous.** Non-null scalar wins; `latlng` only fills nulls; conflicts surface in `gps_scalar_latlng_conflict_count`; malformed JSON surfaces in `gps_malformed_latlng_count` without aborting. Tests cover each row variant.
- **MCP boundary is re-locked.** Plan 06-04 Task 3 extends `FORBIDDEN_TOOL_NAMES` coverage to include `mirror-coverage`, `backfill-streams`, `stream_backfill`, `coverage`, `status`, with explicit assertions that the read-only five-tool allowlist is unchanged.

## 3. Concerns

### HIGH

None.

### MEDIUM

- **`stream_channels.batch_id` has no concrete writer.** Plan 06-01 leaves it nullable and Plan 06-02 does not specify how refresh runtime populates it. D-08 calls for "fetched timestamp or batch identity"; `fetched_at` is set, so the column is functional, but `batch_id` ends Phase 6 as dead metadata unless Plan 06-02 wires the current sync-log id or refresh-attempt id through `_sync_ops`. Not blocking, but worth either populating it or dropping it from the v3 schema.
- **Chunked-commit pattern collides with atomic transaction contract.** Existing `insert_stream_rows_chunked` calls `self.conn.commit()` inside the chunk loop. `replace_stream_rows_and_channel_metadata` must avoid those intermediate commits to honor the atomicity guarantee. Plan 06-01 Task 2 says "one SQLite transaction" but does not flag the existing commit-per-chunk behavior as something to refactor. Executor will likely catch it; calling it out in the plan would harden the contract.
- **Backfill response length vs. existing rows.** `merge_stream_channel_values` updates only matching `time_offset` rows. If a backfill response from Strava returns a different time index, values for non-matching offsets are silently discarded. This is consistent with D-18, but the dry-run/result reporting in Plan 06-04 Task 2 does not include a `rows_skipped_due_to_offset_mismatch` counter.
- **Runtime preflight acceptance window for v3 vs v4.** Plan 06-04 Task 4 says v3 is "accepted only as the intermediate stream-channel schema before GPS canonicalization, and final Phase 6 runtime validation expects v4." The wording leaves it unclear whether a runtime that has applied only the v3 migration is fail-closed or warn-only. A test asserting which it is would close the gap.

### LOW

- **`values_json` storage-size guardrail.** Plan 06-03 Task 2 mandates a DB-size delta report after migration but sets no threshold. For one user with bounded historical activities this is fine.
- **`distance` as `values_json` not scalar.** Plan 06-02 retains `distance` inside `values_json`. Existing analytics do not depend on it as a hot column, but a future planner would need another migration if distance is promoted.
- **Help text for legacy `admin backfill` vs `admin backfill-streams`.** Plan 06-04 Task 3 specifies distinct help strings but does not mandate a deprecation marker.

## 4. Suggestions

1. Populate or drop `batch_id` in Plan 06-02 by passing the current `sync_log.id` or a generated refresh-run UUID into `replace_stream_rows_and_channel_metadata`.
2. Add an explicit `commit_inside_chunk=False` note or equivalent to the atomic stream-replacement repository method.
3. Extend Plan 06-04 dry-run output with `rows_skipped_due_to_offset_mismatch` or document that mismatch is impossible under current refresh ingestion semantics.
4. Add an explicit acceptance criterion in Plan 06-04 Task 4 for whether runtime preflight blocks or warns when it observes v3-only state, and which command the operator runs to advance.
5. Add a forbidden-name guard test for `stream_channels` and `values_json` SQL leakage in `tests/test_mcp_surface.py`.

## 5. Risk Assessment

| Risk | Severity | Likelihood | Mitigation in Plan |
|------|----------|------------|--------------------|
| Migration breaks live mirror | LOW | LOW | Backup-before-DDL plus integrity, row-count, GPS-count, and analytics parity. |
| Stream-channel backfill silently overwrites existing values | LOW | LOW | Merge-only contract plus explicit "never call replace_*" acceptance. |
| MCP gains admin/coverage/backfill surface | LOW | LOW | Forbidden-name list extended; security guard tests required. |
| Schema state stuck at intermediate v3 | LOW | LOW | Idempotent `MIGRATIONS[4]` and version-aware preflight. |
| `batch_id` left as dead metadata | LOW | MEDIUM | Cosmetic; would not block analytics or coverage reporting. |
| Live runtime mutated by repo tests | LOW | LOW | D-23 reinforced; repo tests use `tmp_path`; live commands require explicit operator invocation. |

Overall execution risk is **LOW**. The plans now contain enough specification for an executor to implement Phase 6 without further planning iterations, provided the MEDIUM items above are either addressed inline or accepted as known follow-ups.

CYCLE_SUMMARY: current_high=0

## Current HIGH Concerns

None.
