# Phase 3: Strava Adapter & Refresh Runtime - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 isolates all Strava API transport, OAuth/token persistence, retry/rate-limit handling, and refresh orchestration into adapter/runtime layers. The local `data/strava.db` mirror remains durable state. User-facing read paths must consume the SQLite mirror and freshness metadata rather than calling Strava at request time.

</domain>

<decisions>
## Implementation Decisions

### Freshness and Refresh Runtime Boundary

- **D-01:** Split the system into a read-runtime and a refresh-runtime. MCP/report read paths read SQLite mirror data and refresh metadata; refresh-runtime owns Strava API calls, token refresh, sync execution, checkpointing, leases, and mirror writes.
- **D-02:** MCP/read-runtime must not call Strava, refresh tokens, execute sync/backfill, expose sync tools, or show sync logs. This applies even when the mirror is stale.
- **D-03:** MCP/read-runtime may write only an idempotent local signal into SQLite, such as `refresh_requests(reason=first_use_of_day, requested_for_day=...)`, when it sees that the daily refresh has not completed. Refresh-runtime consumes that signal independently.
- **D-04:** Repeated MCP queries inside a short interval must be served from SQLite state and must not spend Strava quota. Dedupe, lease, backoff, and refresh-state rows prevent thundering-herd refresh scheduling.
- **D-05:** Replace magic freshness windows as the main behavior driver with explicit mirror states: `fresh`, `aging`, `stale`, `refresh_in_progress`, `refresh_failed`, and `refresh_delayed`. Responses should include `data_as_of`, `last_successful_refresh_at`, freshness state, and advisory metadata.
- **D-06:** Automatic refresh must run at least once per local calendar day. First-use-of-day freshness is handled by SQLite refresh-state inspection and an idempotent refresh request, not by direct request-time Strava probing.

### Mirror Completeness

- **D-07:** A refresh is successful only when required summaries, details, streams, and kudos are either fetched or explicitly represented as `partial`, `unknown`, or `unavailable`.
- **D-08:** Missing HR, streams, details, or kudos must never be silently interpreted as rest, zero load, or complete data. Analytics and recommendations must carry completeness metadata.
- **D-09:** Partial refresh progress must be checkpointed so interruptions after summaries, streams, details, or kudos can resume without corrupting or replacing the existing mirror.

### Token, Rate-Limit, and Failure Behavior

- **D-10:** Token persistence belongs to an isolated Strava token provider with atomic write and single-writer protection. Existing `.env` mutation behavior is not safe enough for concurrent refresh attempts.
- **D-11:** On token failure, Strava rate limit, network failure, or partial fetch interruption, fail closed for freshness while keeping old mirror reads available.
- **D-12:** Historical reads, workout lists, and stale-labeled reports may continue from the old mirror. High-confidence readiness and recommendation outputs must be blocked or degraded when freshness is failed/stale.
- **D-13:** Refresh-runtime must persist product-safe reason states such as `token_unavailable`, `rate_limited`, `network_unstable`, `refresh_incomplete`, and `sync_in_progress`. MCP may surface these as freshness metadata without exposing operational sync controls.
- **D-14:** The Strava adapter must track both overall and read/non-upload rate-limit headers, and enforce the stricter remaining budget before continuing refresh work.

### the agent's Discretion

Planning may choose the exact SQLite schema and enum names for `refresh_state`, `refresh_requests`, checkpoint rows, leases, and backoff state as long as the read-runtime/refresh-runtime boundary remains strict and tests prove that read paths do not import or call the Strava adapter.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project and Requirements

- `.planning/ROADMAP.md` — Phase 3 goal and success criteria for Strava adapter isolation and resilient automatic refresh.
- `.planning/REQUIREMENTS.md` — `STRAVA-01`, `STRAVA-02`, `STRAVA-03`, `REFRESH-01`, `REFRESH-02`, `REFRESH-03`, and `TEST-02`.
- `.planning/phases/02-sqlite-safety-repository-layer/02-CONTEXT.md` — Preserved mirror, repository boundary, missing-data semantics, and SQLite safety constraints carried into Phase 3.
- `.planning/phases/02-sqlite-safety-repository-layer/02-VALIDATION.md` — Current Nyquist validation baseline and tests that must not regress.

### Current Code

- `src/mcp_strava/db.py` — Current legacy Strava token/HTTP helpers that must move behind the adapter/token-provider boundary.
- `src/mcp_strava/sync.py` — Current sync/backfill flow, retry behavior, stream/detail/kudos fetch phases, and in-memory rate limiter.
- `src/mcp_strava/settings.py` — Current typed settings surface, including freshness settings that should evolve away from magic hour behavior.
- `src/mcp_strava/adapters/sqlite/repository.py` — Existing repository boundary and sync metadata writes to extend for refresh runtime state.
- `tests/test_security_guards.py` — Existing guardrail style for forbidden boundaries.
- `tests/test_repository_boundary.py` and `tests/test_sqlite_safety.py` — Repository and database safety regression patterns.

### External API References

- `https://developers.strava.com/docs/rate-limits/` — Official Strava overall and read/non-upload rate-limit headers and reset behavior.
- `https://developers.strava.com/docs/getting-started/` — Official Strava OAuth/access-token context.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `SQLiteRepository` already centralizes many persistence writes and can be extended with refresh runtime metadata methods.
- Existing sync phases already separate activity summaries, streams, details, schema validation, and kudos; those phases are natural checkpoint boundaries.
- Phase 2 migration/preflight/backup/parity tooling should remain the path for schema changes to refresh-state tables.

### Established Patterns

- Runtime paths must fail closed on missing expected mirror DB rather than creating an empty database.
- Tests use temp or copied SQLite databases by default; live `data/strava.db` must be preserved.
- Direct SQLite access is constrained to adapter/migration/operator boundaries and narrow tests.

### Integration Points

- `db.py` currently owns `refresh_token()`, `api_request()`, and token-file mutation. Phase 3 should extract these into Strava adapter and token-provider modules.
- `sync.py` currently imports `load_env` and `api_request` directly and uses per-process `RateLimiter`. Phase 3 should invert this behind injectable adapter, clock/sleeper, and runtime policy objects.
- `settings.py` currently exposes `warn_age_hours` and `max_age_hours`; planning should decide how to preserve compatibility while shifting behavior to named mirror states and refresh runtime policy.

</code_context>

<specifics>
## Specific Ideas

- Consider SQLite control-plane tables such as `refresh_state` and `refresh_requests`.
- `refresh_state` may track `last_success_at`, `last_attempt_at`, `last_status`, `last_error_code`, `lease_owner`, `lease_expires_at`, `backoff_until`, `checkpoint_stage`, and `checkpoint_cursor`.
- `refresh_requests` may be append-only with a dedupe key such as `(reason, requested_for_day)` so multiple MCP reads cannot enqueue duplicate refresh work.
- Request-facing response metadata should distinguish stale-but-readable history from blocked or degraded readiness/recommendation advice.
- TEST-02 should use fake Strava adapter, fake token provider, fake clock/sleeper, and import/static guards proving read modules do not touch Strava adapter APIs.

</specifics>

<deferred>
## Deferred Ideas

- Exact MCP tool schemas and allowlist tests belong to Phase 5, but Phase 3 must preserve the no-sync-tool boundary.
- CLI replacement mapping belongs to Phase 4, though Phase 3 may expose operator refresh entrypoints below the application layer.
- Docker/service supervision details belong to Phase 5; Phase 3 should keep refresh-runtime shape container-friendly.

</deferred>

---

*Phase: 3-Strava Adapter & Refresh Runtime*
*Context gathered: 2026-05-21*
