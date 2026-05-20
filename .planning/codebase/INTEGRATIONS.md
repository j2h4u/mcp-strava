# External Integrations

**Analysis Date:** 2026-05-20

## APIs & External Services

**Strava API:**
- Strava Web API is the only live remote service detected.
- SDK/Client: none; `scripts/strava_lib/db.py` and `scripts/strava_lib/sync.py` call Strava directly with `urllib.request`.
- Auth: OAuth 2.0 refresh-token flow using `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`, and `STRAVA_ACCESS_TOKEN` from `.env`.
- Endpoints used by the code:
  - `https://www.strava.com/oauth/token` - token refresh in `scripts/strava_lib/db.py::refresh_token()`
  - `https://www.strava.com/api/v3/athlete` - shoe/athlete profile lookup in `scripts/cli.py::cmd_gear()`
  - `https://www.strava.com/api/v3/athlete/stats` - aggregate stats in `scripts/cli.py::cmd_stats()`
  - `https://www.strava.com/api/v3/athlete/zones` - HR zone cache in `scripts/strava_lib/db.py::get_zones()`
  - `https://www.strava.com/api/v3/athlete/activities` - incremental activity sync in `scripts/strava_lib/sync.py::sync_activities()`
  - `https://www.strava.com/api/v3/activities/{id}` - detailed activity fetch in `scripts/strava_lib/sync.py::sync_activities()` and `backfill_activities()`
  - `https://www.strava.com/api/v3/activities/{id}/streams` - second-by-second stream sync in `scripts/strava_lib/sync.py`
  - `https://www.strava.com/api/v3/activities/{id}/kudos` - kudos sync in `scripts/strava_lib/sync.py::_sync_kudos()`

## Data Storage

**Databases:**
- SQLite local database at `data/strava.db`.
  - Client: stdlib `sqlite3`
  - Managed by: `scripts/strava_lib/db.py::DbConn` and `init_db()`
  - Tables: `activities`, `streams`, `athlete_zones`, `sync_log`, `kudos`

**File Storage:**
- Local filesystem only.
- `data/strava.db` stores all persisted activity, stream, zone, sync, and kudos data.
- `.env` stores refreshable auth state and is rewritten by token refresh logic.

**Caching:**
- SQLite cache tables act as the cache layer.
- `athlete_zones` caches Strava HR zones.
- `activities.detail_json` and `streams` cache activity detail and stream payloads.

## Authentication & Identity

**Auth Provider:**
- Strava OAuth 2.0.
- Implementation: manual refresh-token exchange in `scripts/strava_lib/db.py::refresh_token()`.
- Token lifecycle: access tokens are refreshed on `401` responses and the new tokens are persisted back to `.env`.

## Monitoring & Observability

**Error Tracking:**
- None detected as an external service.
- Local sync failures are recorded in the `sync_log` SQLite table in `scripts/strava_lib/db.py` and reported to stderr in `scripts/strava_lib/sync.py`.

**Logs:**
- CLI output is plain JSON on stdout for command results.
- Sync progress and retry/rate-limit messages are printed to stderr in `scripts/strava_lib/sync.py`.

## CI/CD & Deployment

**Hosting:**
- None detected.

**CI Pipeline:**
- None detected.
- Local verification is driven by `Justfile` and `scripts/run_tests.py`.

## Environment Configuration

**Required env vars:**
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REFRESH_TOKEN`
- `STRAVA_ACCESS_TOKEN`

**Secrets location:**
- `.env` in the repository root.
- `.gitignore` excludes `.env` and `data/*.db*`.

## Webhooks & Callbacks

**Incoming:**
- None detected.

**Outgoing:**
- Direct HTTPS requests to Strava only.
- No webhook delivery, callback endpoint, or event subscription flow is implemented in this repository.

---

*Integration audit: 2026-05-20*
