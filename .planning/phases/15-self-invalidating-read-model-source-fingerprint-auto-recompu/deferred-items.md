
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

## 15-06 execution discoveries (out of scope — logged, not fixed)

- **`deploy/gateway_register.py` pre-existing lint + format drift:** `uv run ruff
  check` flags `UP035` at `deploy/gateway_register.py:9` (`from typing import
  Callable` should be `from collections.abc import Callable`), and `ruff format
  --check` would reformat the same file. Both are pre-existing (no diff from HEAD;
  not touched by 15-06) and outside the WR-01..04 change set, so per the scope
  boundary they were logged here rather than fixed. The file is deploy tooling, not
  on the product/runtime import path. Suggest a quick `style`/`chore` task to run
  `ruff check --fix` + `ruff format` over `deploy/`.
