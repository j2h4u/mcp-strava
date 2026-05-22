---
analysis_date: 2026-05-22
last_mapped_commit: b207e64f8293ddb0b3432562705b96a0a0264082
---

# Codebase Concerns

**Analysis Date:** 2026-05-22

## Tech Debt

**Repository concentration**
- `src/mcp_strava/adapters/sqlite/repository.py:163-214, 585-714` mixes read helpers, write helpers, refresh state, sync logs, and backup-oriented mutation paths in one class. That keeps transaction boundaries implicit and makes the data layer hard to evolve safely.
- `src/mcp_strava/application/metric_services.py:214-244, 483-516` combines metric routing, activity enrichment, and period-comparison assembly in one service module. The compare-periods path repeats the same heavy work across metrics and sports instead of sharing prepared aggregates.

## Known Bugs

**Schema validation stage is a stub**
- `src/mcp_strava/refresh/_sync_ops.py:145-146` defines `schema_validate()` as `return None`. The refresh pipeline advances through a `schema_validate` checkpoint, but no validation actually occurs, so schema drift can pass through silently.

**Settings cache can go stale**
- `src/mcp_strava/settings.py:113-196` caches settings by environment values and file path, not by the contents of the `.env` file. If the file changes on disk in a long-lived process, `get_settings()` can keep returning stale DB, token, host, and policy values until restart or manual cache reset.

## Security Considerations

**Config enforcement depends on fresh settings**
- `src/mcp_strava/interfaces/mcp_http.py:75-113` is fail-closed for loopback and wildcard binds, but it consumes `Settings` from the cache above. If the operator tightens host or origin policy in `.env`, the running server does not see the change until the process reloads settings.
- `src/mcp_strava/adapters/strava/token_provider.py:30-43` rewrites Strava credentials back to the token file after refresh. That is expected behavior, but it makes filesystem permissions part of the security boundary and requires the token path to stay private and writable only by the service user.

## Performance Bottlenecks

**Cardiac drift is the most expensive per-activity computation**
- `src/mcp_strava/cardiac_drift.py:18-122, 259-280` uses Jenks clustering with O(n^2) time and memory. The `max_points=600` cap limits worst-case cost, but the algorithm still does dense work before subsampling and remains expensive for large stream payloads.

**Compare-periods fans out into repeated enrichment**
- `src/mcp_strava/application/metric_services.py:72-121, 214-244, 483-516` re-enriches activities inside nested loops and rebuilds `daily_report_from_connection()` for each of the model metrics. This multiplies SQL round trips and CPU work as the number of activities or metrics grows.

**Write paths commit too frequently**
- `src/mcp_strava/adapters/sqlite/repository.py:585-714` commits after each stream chunk and after each summary/detail/kudos mutation. That keeps failure windows small, but it makes high-volume sync runs IO-heavy and increases the chance of partially applied state if a batch stops midway.

## Fragile Areas

**Process-global HR max cache**
- `src/mcp_strava/metrics.py:12-28` stores `_hr_max_cache` at module scope and never invalidates it when the mirror changes. `%HRR` calculations can stay pinned to an old maximum heart rate until the process restarts.

**Refresh lease has a fixed lifetime**
- `src/mcp_strava/refresh/runtime.py:47-101` acquires a lease for a fixed window and never renews it during long runs. A refresh that outlives the lease can be overlapped by another worker before the first one finishes.

**Cardiac drift degrades silently on exceptions**
- `src/mcp_strava/cardiac_drift.py:95-122` catches broad exceptions in `auto_jenks()` and falls back to a weaker result. That avoids a hard crash, but it also hides malformed or numerically unstable input behind a low-confidence output.

**Day iteration is more brittle than it needs to be**
- `src/mcp_strava/adapters/sqlite/repository.py:420-423` advances dates with string splitting and a local import inside the loop. It works for ISO dates, but it is a fragile place to extend if timezone-aware or non-ISO day handling is introduced later.

## Test Coverage Gaps

**High-risk paths worth regression tests**
- `src/mcp_strava/settings.py`: add a test that mutates the env file on disk and verifies the cache behavior you want.
- `src/mcp_strava/refresh/runtime.py`: add a lease-expiry and concurrent-refresh regression test.
- `src/mcp_strava/refresh/_sync_ops.py`: add a failing test that proves the schema-validation checkpoint is not a no-op once it is implemented.
- `src/mcp_strava/application/metric_services.py`: add a compare-periods test that exercises both global and per-sport fanout without repeated report recomputation.

---

*Concerns audit: 2026-05-22*
