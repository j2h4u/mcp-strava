---
slug: duckdb-art-index-corruption
status: resolved
trigger: DuckDB ART-index corruption on activities upsert — "Failed to delete all rows from index. Only deleted 0 out of 1 rows" on activity 18694535582
created: 2026-05-29
updated: 2026-05-29
---

# Debug Session: duckdb-art-index-corruption

## Resolution (2026-05-29)

- **root_cause:** Upstream DuckDB ART bug (#21394, fixed in 1.5.3) left a stale PK-index
  entry baked on disk for activity 18694535582 → `ON CONFLICT DO UPDATE` delete-from-index
  fatals. The *driver* that both re-corrupted the index and bloated the file was
  `sync_summaries` unconditionally re-upserting all ~604 activities every cycle (synced_at
  always changes) → heavy ART churn. DuckDB never reclaims freed ART blocks → ~10.6 MB/cycle
  (~255 MB/day, 83→800 MB in ~3 days).
- **fix (commit 4d675bc):** (1) skip the activities write when the summary payload is
  semantically unchanged (`summary_payload_changed`) — measured 0 MB/cycle growth, was 10.6;
  (2) refresh worker records each cycle outcome to a status file, Docker healthcheck turns
  unhealthy after N consecutive refresh failures (was: fatal swallowed, container stayed
  healthy, mirror silently stale).
- **repair:** one-time `admin compact` rebuilt the clean index (91.3→83.5 MB); verified the
  repaired file survives the poison upsert; redeployed on the fixed image.
- **verification (live):** `refresh_ok` with all 604 activities incl. the poison row, zero
  FatalException, container healthy, mirror_storage flat (free_blocks=0, delta=0).
- **corrected prior "fact":** the engine fix IS in 1.5.3 — upgrade didn't help only because
  it can't repair already-corrupt on-disk ART; a rebuild does. The "recurs after compact"
  observation was real and explained by the churn driver (now removed), not dev-build contamination.
- **follow-ups:** beads-2zt (deploy/env convention drift); slow test
  `test_repository_methods_cover_…` (~52s, dev backlog); offsite/Borg copy of the .duckdb mirror.

## Symptoms

- **Expected behavior:** Background refresh worker upserts new/changed Strava activities into the DuckDB `activities` table via `ON CONFLICT(id) DO UPDATE` (`upsert_activity_summary`, repository.py:975), keeping the local mirror fresh on the hourly cadence.
- **Actual behavior:** The upsert of activity `18694535582` (dated `2026-05-29`) raises `_duckdb.FatalException` and DuckDB invalidates the whole database until process restart. The worker restarts, reaches the same activity, fails again — a loop. Reads continue to work; only writes/refresh are dead. Mirror is now stale ~24h+.
- **Error message (verbatim):**
  ```
  FATAL Error: Failed: database has been invalidated because of a previous fatal error.
  The database must be restarted prior to being used again.
  Original error: "Invalid Input Error: Failed to delete all rows from index.
  Only deleted 0 out of 1 rows.
  Chunk: Chunk - [12 Columns]
  - FLAT BIGINT: 1 = [ 18694535582]
  - FLAT DATE: 1 = [ 2026-05-29]
  - CONSTANT VARCHAR: 1 = [ NULL]   (x10 more NULL/CONSTANT cols)
  ```
- **Timeline:** DB worked fine all of the past week. Broke only today (2026-05-29, refresh first failed ~09:17 Almaty). Strongly suggests a DATA-SHAPED trigger introduced by a new activity, not slow-burn corruption.
- **Reproduction:** Worker runs upsert for activity `18694535582` → fatal every cycle. Need a clean offline repro on a COPY (never prod, never the read-only safe backup).

## Constraints (BLOCKING — from operator)

- **Durable root-cause fix ONLY.** Operator explicitly does NOT want immediate unblock / compaction band-aids. Do not "fix" by compacting prod.
- **Protected backup must not be deleted/overwritten:** `~/backups/mcp-strava-safe/` (read-only) — only verified-good copy of ~2-day-to-refetch Strava data.
- **Do not assert a root cause without the decisive measurement.** Prior session burned hours on plausible-but-wrong causes (reopen amplification, fact-table churn, summary churn), each refuted by the operator. Form hypothesis → run the disproving measurement → THEN conclude.
- All experiments on a scratch COPY; minimize prod restarts.

## Established facts (do NOT relitigate without new evidence)

- DuckDB **upgrade does NOT fix it** — 1.5.3 / 1.5.4.dev2 / 1.6.0.dev12 all FATAL on the same upsert. RevertCommit index-corruption fix is unreleased (DuckDB PR #21986).

## CONTRADICTION TO RESOLVE FIRST

- Prior session handoff claims: **"compaction (COPY FROM DATABASE) rebuilds the ART index clean and fixes it — proven; a compacted copy survives full re-upsert."**
- Operator says: **export/compact does NOT fix it — the error remains.**
- These conflict. The prior "proof" may have re-upserted a generic row, not THE poison row (activity 18694535582 with today's exact payload). FIRST decisive measurement: take a freshly compacted/exported copy and attempt the upsert of activity 18694535582 with its real current payload. Does it survive or fatal?

## Environment / artifacts

- Prod container `mcp-strava`: healthy, reads OK, refresh broken; interval 3600.
- Prod DB: `/opt/docker/mcp-strava/data/strava.duckdb` (~92M).
- Safe backups (read-only, DO NOT DELETE): `~/backups/mcp-strava-safe/strava-clean-20260529T094705Z.duckdb` (verified 604 activities, 2,684,891 streams) + `strava-raw-…`.
- Failing path: `src/mcp_strava/refresh/_sync_ops.py::sync_summaries` → `src/mcp_strava/adapters/duckdb/repository.py::upsert_activity_summary` (line 975).
- Prior context: `.planning/HANDOFF.json`, `.planning/.continue-here.md`.

## Current Focus

- hypothesis: The corruption is a PERSISTENT ART-index/storage divergence on the `activities` PK, baked into the file. Compaction (COPY FROM DATABASE) rebuilds the ART clean → upsert survives. The operator's "compact does NOT fix it" refers to RECURRENCE: a freshly-compacted index re-corrupts during normal write activity. Durable fix question = what triggers re-corruption, and whether it's avoidable without the ART PK.
- test: (1) real upsert path on RAW copy vs COMPACTED-clean copy — DONE. (2) characterize recurrence: hammer a compacted copy with repeated upserts / sync-shaped sequence to see if/when the clean index re-diverges.
- expecting: RAW=FATAL, COMPACTED=SURVIVE (CONFIRMED). Next: find the write pattern that re-corrupts a clean index.
- next_action: stress a compacted copy: many ON CONFLICT updates on activities (and the source_state/dirty tables) to reproduce re-corruption offline; if it recurs, identify minimal trigger.

## Evidence

- timestamp: 2026-05-29 (this session)
  checked: poison row 18694535582 in both clean+raw copies via SELECT (count, distinct id, dup groups, full payload, source_state/dirty counts)
  found: exactly 1 physical row, id is distinct, NO duplicate PK groups; payload is NORMAL (id, day=2026-05-29, "Night Walk"/"Walk", real numerics, summary_json 1832ch, detail_json 5960ch, NO NULLs). source_state=1 row, metric_dirty=0 rows. The NULLs in the error chunk are unfetched columns DuckDB prints during index delete, NOT the row's data.
  implication: Not a data-shaped payload trigger (no weird NULL/type), and no SELECT-visible duplicate/stale PK. The divergence is internal to the ART index vs storage, invisible at the SQL level.

- timestamp: 2026-05-29 (this session)
  checked: DECISIVE MEASUREMENT #1 — ran the REAL upsert_activity_summary path (DuckDBRepository.from_path → upsert with poison row's actual payload) on fresh writable copies of the protected backups. duckdb 1.5.3 (same as app).
  found: RAW copy (strava-raw, mirrors prod pre-compaction) → FatalException, EXACT same error "Failed to delete all rows from index. Only deleted 0 out of 1 rows", 12-col chunk = activities table layout (id BIGINT, activity_day DATE, then date/name/sport VARCHAR, distance DOUBLE, moving/elapsed BIGINT, elev DOUBLE, summary/detail/synced VARCHAR). COMPACTED clean copy (strava-clean) → SURVIVED upsert.
  implication: (a) Compaction DOES fix the poison-row upsert — contradiction resolved; operator's "compact doesn't fix it" = recurrence, not the upsert itself. (b) Corruption is PERSISTENT in the file (survives copy → not an in-memory transaction-state artifact). (c) The failing index is the ACTIVITIES PRIMARY KEY (12-col chunk matches activities), NOT activity_source_state or metric_dirty_activities — those upserts are never reached because the activities upsert fatals first.

- timestamp: 2026-05-29 (this session)
  checked: UPSTREAM root cause — searched DuckDB issues for the exact error string. Found issue #21394 "Internal errors triggered by DELETE after UPDATE and CREATE INDEX" with minimal reproducer Case 1 (INSERT; UPDATE; CREATE INDEX; DELETE → "Failed to delete all rows from index. Only deleted 0 out of 1 rows", chunk shows the STALE pre-UPDATE value). Fixed by PR #21427 "Fix stale update read during index removal" (merged 2026-03-18 into v1.5-variegata).
  found: The error is a STALE-UPDATE-READ-DURING-INDEX-REMOVAL bug: the ART index retains a stale row reference (from an UPDATE applied before/around index maintenance); a later delete-from-index (which ON CONFLICT DO UPDATE performs internally) cannot match the stale entry against physical storage → "0 out of 1 deleted" → DB invalidated.
  implication: This is a genuine upstream DuckDB engine bug, NOT a data-shaped trigger in activity 18694535582. The poison row is normal; it just happens to be the row whose PK ART entry got corrupted.

- timestamp: 2026-05-29 (this session)
  checked: VERSION ancestry — does v1.5.3 (app's pinned + prod-container version, confirmed `docker exec mcp-strava` = 1.5.3) contain fix commit ffcdeb0 (PR #21427)? `git compare ffcdeb0...v1.5.3` = ahead_by 1016, behind_by 0, status "ahead" → fix commit IS an ancestor of v1.5.3 → FIX IS INCLUDED IN 1.5.3. Then ran upstream issue #21394 Case 1 reproducer on installed duckdb 1.5.3 → SURVIVED (remaining rows 0), i.e. the engine fix is ACTIVE.
  implication: CORRECTS the prior "established fact". Upgrade does not fix it NOT because the fix is unreleased — the fix IS in 1.5.3. Upgrade can't help because the engine fix only prevents CREATING new bad ART state; it cannot REPAIR a file whose ART was already corrupted on disk by an EARLIER DuckDB build. The corruption was baked in before the upgrade (file created 2026-05-25 via legacy_inline migrations; data migrated from an earlier store). Only a full index REBUILD (compaction / COPY FROM DATABASE) repairs it.

- timestamp: 2026-05-29 (this session)
  checked: RECURRENCE on 1.5.3 — stressed fresh compacted copies: (1) 300 in-process upsert cycles with source_state+dirty churn → SURVIVED; (2) 60 reopen+CHECKPOINT cycles → SURVIVED; (3) 25 worker-shaped cycles × 40 activities (summary upsert + detail UPDATE + checkpoint + reopen) → SURVIVED. No new corruption generated under any normal write pattern on 1.5.3.
  implication: A compacted file does NOT re-corrupt under the production 1.5.3 worker. The prior session's "re-corrupted ~30min after compact" is best explained as an artifact of the chaotic earlier investigation (10+ restarts, A/B swapping to buggy builds 1.5.4.dev2 / 1.6.0.dev12, experiments on a still-bloated DB) — i.e. re-corruption was likely re-introduced by running an OLDER/buggy DuckDB build against the file during testing, not by the prod 1.5.3 worker.

## Resolution

root_cause: |
  Upstream DuckDB engine bug — "stale update read during index removal" (DuckDB issue #21394, fix PR #21427). The `activities` table PRIMARY KEY ART index holds a STALE row reference for activity id=18694535582. This bad index entry was WRITTEN INTO THE FILE by an EARLIER DuckDB build (before the file/data was on 1.5.3; the .duckdb was created 2026-05-25 via legacy_inline migrations from an earlier store). When the refresh worker upserts that activity (ON CONFLICT(id) DO UPDATE → internal delete-then-reinsert on the PK ART), the delete-from-index cannot match the stale entry against physical storage → "Failed to delete all rows from index. Only deleted 0 out of 1 rows" → DuckDB invalidates the whole DB until restart. The failing index is the ACTIVITIES PK (12-col error chunk matches the activities row layout); activity_source_state / metric_dirty_activities are never reached.
  The corruption is PERSISTENT in the file (survives copy) and is invisible at the SQL level (SELECT shows exactly 1 row, no duplicate PK). The fix for this bug IS already present in DuckDB 1.5.3 (verified: upstream minimal reproducer survives on 1.5.3), so 1.5.3 does NOT generate new corruption — but the engine fix cannot RETROACTIVELY repair the already-corrupt ART on disk. Only a full index rebuild repairs it.

verification: |
  Decisive measurements (all on writable scratch copies of the read-only protected backups; safe backups left 444/untouched; prod never mutated):
  - RAW copy + real upsert_activity_summary path → FATAL, exact error reproduced. COMPACTED-clean copy + same path → SURVIVED. (compaction fixes the upsert; resolves the contradiction)
  - Corruption survives file copy → persistent on disk, not in-memory.
  - Upstream issue #21394 Case 1 reproducer on installed 1.5.3 → SURVIVED → engine fix (PR #21427) active in 1.5.3.
  - git ancestry: fix commit ffcdeb0 is an ancestor of v1.5.3 → fix included in 1.5.3.
  - Compacted copy survived 300 in-process + 60 reopen/checkpoint + 25 worker-shaped(×40) cycles → no recurrence on 1.5.3.

fix: (NOT APPLIED — diagnose-only run; candidate durable fixes enumerated in Root Cause Report for operator to choose)

files_changed: []

## Current Focus

- hypothesis: CONFIRMED — upstream "stale update read during index removal" bug (DuckDB #21394 / PR #21427) corrupted the activities PK ART under an earlier DuckDB build; the bad entry is persisted in the file; 1.5.3 (engine fix present) cannot repair existing on-disk corruption, only a rebuild can.
- test: (done — see Resolution.verification)
- expecting: (done)
- next_action: DIAGNOSE-ONLY — return Root Cause Report with candidate durable fixes. Do NOT apply a fix.

## Eliminated

- hypothesis: DuckDB version bug fixable by upgrade — ELIMINATED: 1.5.3/1.5.4.dev2/1.6.0.dev12 all fatal on the same upsert (prior session A/B test).

## Disk Bloat Investigation

Distinct from the FATAL bug above. Goal: prove/refute "ART indexes cause 83 MB -> ~800 MB bloat" with block-level measurement, starting from a COMPACTED baseline (free_blocks=0). DIAGNOSE ONLY.

### Method
- Scratch copies of the read-only protected backups (444 left untouched). block_size = 262144 (256 KB). CHECKPOINT before every PRAGMA database_size measurement.
- Attribution: base-table data blocks = union of distinct block_id from pragma_storage_info per table; index+meta blocks = used_blocks - base_data_blocks; free_blocks = reclaimable-in-file (not returned to OS until COPY FROM DATABASE).

### Evidence (block-level)

- BASELINE (compacted clean backup): total=333 used=333 free=0, base_data=195, idx+meta=138, file=83.26 MB. 604 activities, 2,684,891 streams.
- CONTROL (no-op): 20 CHECKPOINTs + 20 empty BEGIN/COMMIT => total 333->333, file flat. Open/close/checkpoint machinery does NOT bloat.
- EXP A (real upsert_activity_summary, 50 existing activities re-upserted with SAME payload, per-cycle): UNBOUNDED LINEAR growth.
  - 0/10/20/30/50 cycles -> file 83.26 / 97.51 / 106.26 / 112.01 / 126.76 MB. base_data ~flat (195->201). idx+meta 138->216 (+78 blk ~19.5MB). free 0->90 (+22.5MB). NO convergence at 2500 upserts.
- EXP ARM1 (raw activities ON CONFLICT only, NO source_state/dirty writes): still UNBOUNDED 83.26->112 MB over 1500 upserts. => source_state/dirty path is NOT the cause; the leak is the activities-PK upsert itself.
- EXP ARM B (1500 upserts, NO intermediate checkpoint, single final CHECKPOINT): 83.26->102.26 MB. => bloat happens even with one checkpoint; per-cycle checkpoint only mildly amplifies. Not a checkpoint-cadence artifact.
- EXP RE-COMPACTED (COPY FROM DATABASE full index rebuild, then same workload): 83.51->112.26 MB, identical to original. => bloat is NOT due to the migrated file's degraded ART state; a brand-new clean rebuild bloats the same. REFUTES "stale migrated index causes bloat."
- SYNTHETIC REFUTATIONS (fresh small/medium DBs, identical upsert/update workloads):
  - PK-only table 2000 rows, 30x UPDATE / 30x ON CONFLICT: NO growth (4 blocks, free reused).
  - 300k-row PK table, 1500 single-tx ON CONFLICT same-payload upserts: ZERO growth (12 blocks).
  - PK + secondary index, 1500 upserts: oscillates 4<->7 blocks, free reused. No leak.
  - Structural replica (small activities PK+secondary idx + 2.7M-row streams composite-PK ART), 1500 activities upserts: oscillates 93<->96 blocks, file stable ~23 MB. No leak.
  => On freshly-built indexes in synthetic DBs, free blocks ARE reused and the workload does NOT bloat. The real strava.duckdb bloats under the SAME workload AND a freshly-recompacted real file ALSO bloats.

### Per-table facts
- activities: 604 rows, avg detail_json ~8 KB, ~5.82 MB JSON total, ALL in ONE row group.
- Every hot table has a PK ART; activities also has secondary idx_duckdb_activities_day_id(activity_day,id); 4 fact tables each have PK + secondary index; streams composite PK over 2.68M rows.

### Working mechanism (under test, see freelist horizon experiment)
The activities table is a single ~6 MB row group with large JSON columns. An ON CONFLICT DO UPDATE rewrites the updated column segments of that row group on checkpoint (copy-on-write at row-group granularity) and rewrites affected ART nodes. Old blocks go to the free list. The decisive open question being measured: free_blocks plateau (reuse, bounded) vs grow forever (true leak), and whether COPY FROM DATABASE fully reclaims.

### CONFIRMED root cause (disk bloat)

DECISIVE long-horizon (real DB, 5000 same-payload upserts, periodic checkpoint):
- 0/1250/2500/3750/5000 ups -> 83.26/100.01/121.26/141.26/161.01 MB. used 333->497 AND free 0->147 BOTH grow monotonic-linear. NO plateau, NO reuse. Leak rate = 15.55 MB / 1000 upserts (~15.9 KB/upsert).
- COPY FROM DATABASE on the 161 MB file -> 83.51 MB (full reclaim to baseline).

UPSTREAM-DOCUMENTED behavior (not our bug): DuckDB issue #19468 "Due to UNIQUE or PRIMARY KEY constraint, the size of duckdb database file keeps growing" — frequent UPDATEs to a PK/UNIQUE (=ART) table grow the file unbounded; CHECKPOINT/VACUUM do NOT reclaim; only COPY FROM DATABASE does. ART index storage is not compacted in place; freed blocks land at non-tail positions so checkpoint truncation can't release them. Matches our measurements exactly.

WHY synthetic replicas did NOT bloat but the real DB does: small/fresh DBs reuse free blocks within the file; the leak manifests at scale (large ART, sustained update volume, 256KB blocks) where freed blocks are not at the file tail and are not reused — i.e. the real workload's churn outpaces in-file reuse. Confirmed: re-compacted real file ALSO bloats identically, so it is the workload+engine behavior, not file provenance.

DRIVER (magnitude reconciliation): src/mcp_strava/refresh/_sync_ops.py sync_summaries (lines 195-210) calls upsert_activity_summary UNCONDITIONALLY for EVERY activity returned by Strava on every page every cycle (the `new` counter is cosmetic). With synced_at=now_iso changing each cycle, every one of ~604 activities is a genuine UPDATE -> ART delete+reinsert + row-group rewrite. Empirically sync_log shows seen=604, new=0 every hour — i.e. 604 no-content-change upserts/cycle.
- 604 upserts/cycle * 15.55 MB/1000 = ~9.4 MB/cycle. Hourly -> ~225 MB/day -> 83->800 MB in ~3.2 days. MATCHES operator's "a few days".

ONE-TIME vs RECURRING (settled): RECURRING, per-cycle accumulating. NOT a one-time Phase-8 migration aftermath. The prior 764 MB was the same leak having run for days, then masked by a free-block pool. Compaction resets to 83 MB; normal hourly refresh re-bloats ~225 MB/day.

WHY PROD IS ONLY ~91 MB RIGHT NOW (not 800): read-only snapshot = total 365, free 22 (6% reclaimable), last successful sync 08:17 (refresh FATAL'd 09:17). The FATAL bug PAUSED the bloat driver ~7h ago — no upserts succeed on an invalidated DB. So the bloat is dormant only because refresh is broken. Fix the FATAL and the leak resumes at ~225 MB/day until compaction.

CONFIRM/REFUTE "ART indexes are the cause": CONFIRMED as the storage mechanism (PK/secondary ART blocks + their freed-but-unreused blocks are the growth; base-table data stays ~flat). But the precise statement is: "frequent UPDATEs against PK/UNIQUE(ART) tables under DuckDB's no-in-place-ART-compaction behavior." REFUTED sub-claims: not source_state/dirty churn, not checkpoint cadence, not migrated-file degradation, not fact-table churn (materializer is dirty-driven, noop when clean).

### Resolution (disk bloat)
root_cause: sync_summaries re-upserts ALL ~604 activities every hourly cycle (synced_at changes => real UPDATE). DuckDB does not compact PK/secondary ART index storage in place and does not reuse/truncate the freed blocks at scale (upstream issue #19468), so each cycle leaks ~9.4 MB. CHECKPOINT does not reclaim; only COPY FROM DATABASE (admin compact) does. ~225 MB/day -> 83->800 MB in ~3 days. Recurring, not one-time.
files_changed: [] (diagnose-only)

### Candidate durable fixes (NOT applied)
1. Make sync_summaries conditional: skip upsert_activity_summary when content unchanged (compare summary_json/fields; ignore synced_at, or store synced_at separately). Cuts ~604 -> ~0 upserts/idle cycle. Smallest, targeted; biggest leak reduction with no schema change. Tradeoff: must define "changed" carefully (don't write synced_at into the indexed row, or track it out-of-band).
2. Scheduled compaction cadence (admin compact already exists): run COPY FROM DATABASE daily. Tradeoff: band-aid, needs owner-stop window; leak still occurs between compactions; operator earlier rejected compaction-as-fix for the FATAL but it is legitimate maintenance for bloat.
3. Remove/loosen ART indexes on hot tables (drop secondary idx_duckdb_activities_day_id; reconsider PK as ART). Tradeoff: invasive (schema+repo+migration+tests); read-query plans change; PK removal loses upsert-by-id ON CONFLICT semantics. This is the same intervention floated for the FATAL, but the FATAL fix and the bloat fix are DIFFERENT problems: FATAL = repair corrupt on-disk ART (rebuild once) + the engine fix already in 1.5.3 prevents NEW corruption; bloat = stop unnecessary UPDATEs and/or periodic compaction. Option 1 fixes bloat without touching indexes; a one-time rebuild fixes the FATAL. They are separable.
4. Move synced_at out of the activities table into a side table (activity_source_state already exists) so the indexed activities row is only UPDATEd on real content change. Combines well with option 1.

Recommendation direction (operator decides): option 1 (conditional upsert / synced_at out of the hot row) addresses the root driver durably with minimal blast radius; pair with option 2 (periodic admin compact) as defense-in-depth. Option 3 is the heavy hammer and is not required to fix bloat.
