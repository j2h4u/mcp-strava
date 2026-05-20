# Codebase Concerns

**Analysis Date:** 2026-05-20

## Tech Debt

**Schema management**
- Issue: `scripts/strava_lib/db.py` mixes bootstrap, migration, and table creation in one runtime path, with inline `ALTER TABLE` checks instead of versioned migrations.
- Files: `scripts/strava_lib/db.py:37-90`
- Impact: schema changes are hard to replay cleanly across existing DBs, and migration intent is spread across startup code.
- Fix approach: add a schema-version table and explicit migration steps.

**Contract duplication**
- Issue: `scripts/strava_lib/api_schema.py` and `scripts/strava_lib/strava_api_reference.py` encode the same Strava surface in two formats.
- Files: `scripts/strava_lib/api_schema.py`, `scripts/strava_lib/strava_api_reference.py`
- Impact: docs, validation, and sync behavior can drift apart without a single source of truth.
- Fix approach: generate one artifact from the other or collapse both into one authoritative contract.

**Planner entanglement**
- Issue: `calc_weekly_plan()` brute-forces every template combination with `itertools.product()` and hard-coded scoring weights.
- Files: `scripts/strava_lib/training.py:443-553`
- Impact: the planner is difficult to tune, and the current model cannot express deload periods or broader periodization.
- Fix approach: replace exhaustive search with a smaller heuristic search space and explicit training phases.

## Known Bugs

**Missing-HR activity history disappears**
- Issue: `get_daily_trimp_history()` filters on `s.heartrate IS NOT NULL`, so activities without HR streams are dropped from the history entirely.
- Files: `scripts/strava_lib/db.py:216-243`, `scripts/strava_lib/report.py:81-89`, `scripts/strava_lib/analytics.py:178-191`
- Impact: `daily_report()`, `weekly_digest()`, streak calculations, and load history treat sensor-dropout or non-HR sessions as rest.
- Fix approach: separate “activity happened” from “TRIMP was derivable” and surface missing-HR sessions as unknown instead of zero.

**Week bucketing is fragile**
- Issue: `compute_trends()` groups weeks with `%U` and then recomputes average fitness by scanning the whole history again with string-prefix filtering.
- Files: `scripts/strava_lib/trends.py:28-52`
- Impact: week boundaries around year transitions are easy to misread, and the second pass is more fragile than the rest of the analytics pipeline.
- Fix approach: group by ISO week keys and compute per-week aggregates in one pass.

## Security Considerations

**Mutable plaintext secret store**
- Issue: `.env` is used as the token store, and `refresh_token()` rewrites access and refresh tokens back to disk in plaintext.
- Files: `scripts/strava_lib/db.py:95-138`
- Current mitigation: `.env` is ignored by `.gitignore`.
- Recommendations: move tokens to a dedicated secret store, or at minimum use atomic writes and file locking.

**Arbitrary SQL power tool**
- Issue: `cmd_sql` executes arbitrary SQL against the local SQLite database.
- Files: `scripts/cli.py:63-80`
- Current mitigation: this is only a local CLI command, not a remote surface.
- Recommendations: keep it local-only and avoid exposing it in any automated or shared execution path.

## Performance Bottlenecks

**Per-activity stream rescans**
- Issue: `daily_report()` enriches every recent activity and calls `calc_hr_recovery()` and `calc_cardiac_drift()` per row.
- Files: `scripts/strava_lib/report.py:27-39`, `scripts/strava_lib/metrics.py:220-351`, `scripts/strava_lib/metrics.py:419-420`
- Impact: report latency scales with both activity count and stream length.
- Fix approach: cache per-activity metrics and avoid re-scanning the same stream rows when the report is recomputed.

**Quadratic drift analysis**
- Issue: `scripts/strava_lib/cardiac_drift.py` still uses a quadratic Jenks implementation, even though it subsamples long streams to cap runtime.
- Files: `scripts/strava_lib/cardiac_drift.py:18-36`, `scripts/strava_lib/cardiac_drift.py:196-245`
- Impact: long activities are approximated, and the subsample can smooth away short but meaningful effort changes.
- Fix approach: keep the runtime cap, but expose when a result was computed from a downsampled stream and consider a lighter clustering method.

**Repeated rolling-window scans**
- Issue: `weekly_digest()` recomputes load, efficiency, and volume with repeated window walks over the same history.
- Files: `scripts/strava_lib/analytics.py:171-257`
- Impact: the current cost is acceptable for small histories, but it scales poorly as the dataset grows.
- Fix approach: precompute daily aggregates once and reuse them across all rolling windows.

## Fragile Areas

**Load model depends on HR availability**
- Issue: the same HR filter that powers TRIMP also drives streak counting and daily load history.
- Files: `scripts/strava_lib/db.py:216-243`
- Why fragile: training load becomes a function of sensor quality instead of actual activity presence.
- Safe modification: keep load derivation and activity presence separate before changing any recommendation logic.
- Test coverage: no targeted test covers a workout with missing HR data.

**Week-based trend math**
- Issue: `compute_trends()` depends on `%U` week numbering and a second-pass fitness lookup.
- Files: `scripts/strava_lib/trends.py:12-107`
- Why fragile: week numbering around year boundaries is easy to get wrong, and the current implementation is harder to validate than the rest of the analytics code.
- Safe modification: switch to ISO week keys and assert the bucketing rules in tests.

**Downsampled cardiac drift**
- Issue: `calc_cardiac_drift()` changes resolution by subsampling when streams exceed `max_points`.
- Files: `scripts/strava_lib/cardiac_drift.py:206-245`
- Why fragile: results depend on point density, not just athlete physiology.
- Safe modification: preserve the original resolution metadata and expose when the result was computed from a downsampled stream.

## Scaling Limits

**Single-file SQLite state**
- Issue: the system keeps all state in one local SQLite database.
- Files: `scripts/strava_lib/db.py:14-33`, `data/strava.db`
- Current capacity: fine for one local user and serial CLI use.
- Limit: concurrent report, sync, and CLI activity will eventually hit SQLite contention, and there is no queue or retry layer around writes.
- Scaling path: move write-heavy state behind a server or serialize jobs through a runner if multi-process use grows.

**Synchronous rate-limit backoff**
- Issue: sync retries are blocking and sleep inside the process when Strava returns 429s.
- Files: `scripts/strava_lib/sync.py:90-129`
- Current capacity: acceptable for occasional manual syncs.
- Limit: large backfills can sleep for long windows and tie up the process.
- Scaling path: split long syncs into resumable jobs and persist retry state across runs.

## Dependencies at Risk

**Implicit Python environment**
- Issue: there is no package manifest or lockfile.
- Files: `Justfile`, `scripts/run_tests.py`
- Risk: the runtime is implicit, so reproducing the exact interpreter environment depends on the host.
- Impact: environment drift is harder to detect than it should be.
- Migration plan: add a `pyproject.toml` even if the project remains stdlib-only, so Python version and tooling are explicit.

## Missing Critical Features

**No subjective signal in load decisions**
- Issue: `perceived_exertion` is parsed but not fed into the progressive signal.
- Files: `scripts/strava_lib/types.py`, `scripts/strava_lib/metrics.py:356-420`, `scripts/strava_lib/training.py:253-436`
- Problem: the recommendation loop only sees load proxies, not the athlete’s actual perceived state.
- Blocks: deload decisions and conservative overrides remain weakly informed.

**No environment correction or recovery trend input**
- Issue: the load model still lacks temperature correction and resting-HR trend tracking.
- Files: `scripts/strava_lib/report.py:146-234`, `scripts/strava_lib/training.py:253-436`
- Problem: hot-weather and baseline-recovery effects are not separated from training quality.
- Blocks: load bonus can still be distorted by environment and baseline recovery shifts.

## Test Coverage Gaps

**Only smoke coverage**
- What’s not tested: sync retry behavior, OAuth refresh failure, schema migration, `.env` rewrite behavior, and the missing-HR history path.
- Files: `tests/test_smoke.py`, `scripts/run_tests.py`, `scripts/strava_lib/db.py`, `scripts/strava_lib/sync.py`
- Risk: the highest-risk paths are only covered indirectly by smoke tests.
- Priority: high.

**No edge-case coverage for analytics hot spots**
- What’s not tested: large-stream cardiac drift behavior, week-boundary handling in `compute_trends()`, and the downsampled result path.
- Files: `scripts/strava_lib/cardiac_drift.py`, `scripts/strava_lib/trends.py`
- Risk: the hardest-to-debug errors are the ones most likely to escape the current suite.
- Priority: medium.

---

*Concerns audit: 2026-05-20*
