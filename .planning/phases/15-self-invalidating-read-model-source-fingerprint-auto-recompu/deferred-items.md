
## 15-05 execution discoveries (out of scope — logged, not fixed)

- **Refresh worker kudos-sync TypeError (pre-existing, out of 15-05 scope):** the
  in-process refresh worker crashes its periodic cycle at
  `src/mcp_strava/refresh/_sync_ops.py:454` in `_sync_kudos`:
  `transport.fetch(f"/activities/{row['id']}/kudos...")` raises
  `TypeError: tuple indices must be integers or slices, not str` — `row` is a
  tuple-shaped row, not a mapping, so `row['id']` fails. This makes the container
  report `unhealthy`, but the MCP **product** surface is unaffected (smoke
  `status: ok`; `list_workouts` returns `relative_time`/`start_time_local`).
  Not introduced by 15-05 (no kudos-sync changes here). Needs a fix to index the
  row by position or convert it to a mapping in `_sync_kudos`. Suggest a quick task.

- **Deploy preflight vs self-heal seed ordering (see 15-05-SUMMARY Deferred Issues):**
  preflight enforces `read_model_logic_version` before the repository's idempotent
  seed can create it, so a pre-Phase-15 live DB crash-loops. Worked around for the
  dev instance by applying the in-code seed once; durable fix deferred to the deploy
  layer.
