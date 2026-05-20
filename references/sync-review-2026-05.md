# Sync Reliability Review — May 20, 2026

Two-round expert panel review of `sync.py` + `db.py` (Strava API → SQLite sync pipeline).

## Round 1: Initial Audit

Panel: Business Owner, System Architect, Security Analyst, DevOps Engineer, Sys Admin, Researcher, QA Engineer.

### Critical Findings (4 fixes applied)

| # | Finding | Expert | Fix |
|---|---|---|---|
| 1 | `_fetch_with_retry` only caught `_rate_limited` — network errors crashed sync | QA | Added `except (URLError, socket.timeout, OSError)` with backoff 1s→5s→30s |
| 2 | No response type validation — error dict iterated as list | QA | `isinstance(data, list)` before Phase 1 loop; `isinstance(data, dict)` for streams/details |
| 3 | `get_daily_trimp_history` used f-string SQL interpolation for sport filter | Architect | Parameterized: `','.join('?' * len(...))` + `params.extend(...)` |
| 4 | `.env` file was world-readable (644) | Security | `chmod 600` |

### Survivors (deferred, later fixed in R2)

- Backfill lacked type validation (Architect) → fixed in R2
- `refresh_token()` had no error handling (Security) → fixed in R2
- No `X-RateLimit-Usage` header parsing (Researcher) → fixed in R2

## Round 2: Post-Fix Re-Review

Panel: same composition, reviewing final state after 9 improvements.

### Critical Findings (3 fixes applied)

| # | Finding | Expert | Fix |
|---|---|---|---|
| 1 | Backfill lacked `isinstance` checks — same bug as sync Phase 1 but missed | Architect | Added `isinstance(data, dict)` to both backfill phases |
| 2 | `HTTPError` (403/500/502) not caught in `_fetch_with_retry` | Security + QA | Added `urllib.error.HTTPError` to except clause; 404 skips immediately |
| 3 | 429 Retry-After fallthrough had no sleep | QA | Added `time.sleep(15)` in except branch |

### Optional Improvements (2 applied)

| # | Finding | Expert | Fix |
|---|---|---|---|
| 4 | `refresh_token()` — raw urllib traceback on OAuth failure | Security | Wrapped in try/except with `RuntimeError` + actionable message |
| 5 | `import time as _t` duplicated inside `_fetch_with_retry` | SysAdmin | Moved `import time` to module top |

### New Feature: sync_log audit table

Added `sync_log` table + tracking in `sync_activities()` + `cmd_log` CLI command.
Every sync writes: timestamp, status, activities_seen/new, streams_fetched, details_fetched, api_calls, error.

## Improvements Applied Between Reviews

| # | Improvement | Source |
|---|---|---|
| 5 | `api_request` returns `(data, rate_headers)` tuple — `X-RateLimit-Usage`/`X-RateLimit-Limit` parsing | Researcher |
| 6 | `RateLimiter.update_from_headers()` + `Retry-After` handling on 429 | Researcher + QA |
| 7 | `PRAGMA wal_autocheckpoint=1000` + `check_same_thread=False` in DbConn | SysAdmin |
| 8 | `try/except` with traceback around sync/backfill in CLI | DevOps |
| 9 | `_insert_streams` batched `executemany` (5000 rows/batch) | SysAdmin |
| 10 | Quick sync mode with `after=` parameter (default) + `--full` flag | Architect |
| 11 | 404 → immediate skip (no retry) in `_fetch_with_retry` | QA |
| 12 | Kudos sync (Phase 5): `GET /activities/{id}/kudos`, incremental, default all-time window | User request |

### Round 3: Kudos Backfill Discoveries

During the initial kudos backfill (105 activities), two bugs surfaced:

| # | Finding | Fix |
|---|---|---|
| 13 | **Kudos endpoint returns no `athlete.id`** — only `firstname`/`lastname`. `INSERT OR REPLACE` with `(activity_id, athlete_id)` PK silently dropped all rows because `athlete_id` was NULL. Caught by `cli.py kudos` returning empty after successful sync. | Changed PK to `(activity_id, firstname, lastname)`. A person can't kudos the same activity twice — this combination IS unique. See `references/kudos-api.md`. |
| 14 | **429 cascade: 3 rapid retries all failed** — `_fetch_with_retry` slept 15s on 429 but didn't inform `RateLimiter`. Next `wait()` saw no server usage → passed → immediate 429 again. 9 activities lost to this cycle. | Added `RateLimiter.mark_rate_limited()` — sets `_server_usage = _server_limit`, forcing `wait()` to block until the rate window resets. Called from `_fetch_with_retry` on every 429. |

### Key Design Decisions

- **Quick sync 7-day overlap**: Chosen over 1-day to catch late kudos/likes. Overlap is ~7-21 activities for this athlete — still one API page. Idempotent via UPDATE.
- **Full sync preserved as `--full`**: Weekly cron for catching back-dated uploads. Daily quick sync is default.
- **Rate limiter dual-source**: Prefers server `X-RateLimit-Usage` headers; falls back to client-side counter. Essential because phone/watch share the API quota.
- **`api_request` → tuple**: Breaking change to return type — all 5 call sites updated. Tuple unpacking is the new contract.

## Files Modified

| File | Lines changed | What |
|---|---|---|
| `sync.py` | ~80 lines added/modified | RateLimiter, _fetch_with_retry, sync_activities, backfill, _sync_kudos |
| `db.py` | ~40 lines | api_request, _parse_rate_headers, refresh_token, DbConn, kudos table, sync_log table |
| `cli.py` | ~30 lines | cmd_sync, cmd_log, try/except wrappers |
