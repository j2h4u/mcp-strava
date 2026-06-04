
## 15-05 execution discoveries (out of scope — logged, not fixed)

- **✅ RESOLVED (2026-06-04) — Refresh worker kudos-sync TypeError:** `_sync_kudos`
  read raw `repo.conn.execute().fetchall()` tuples with `row['id']`, crashing the
  worker every cycle (`TypeError: tuple indices must be integers or slices, not str`;
  container `unhealthy`, 257+ consecutive failures). Fixed in `f6d70ee` (positional
  index + regression test) and hardened in `393e6d4` (durable: moved the query behind
  a typed `DuckDBRepository.activities_missing_kudos() -> list[int]`; no raw DB-API in
  the refresh layer). Container rebuilt → healthy. This whole class is now caught by
  the basedpyright `reportAny` gate.

- **⏳ OPEN — Deploy preflight vs self-heal seed ordering (see 15-05-SUMMARY Deferred Issues):**
  preflight enforces `read_model_logic_version` before the repository's idempotent
  seed can create it, so a pre-Phase-15 live DB crash-loops. Worked around for the
  dev instance by applying the in-code seed once; durable fix deferred to the deploy
  layer.

## 15-06 execution discoveries (out of scope — logged, not fixed)

- **✅ RESOLVED (2026-06-04) — `deploy/gateway_register.py` lint + format drift:**
  ran `ruff check --fix` + `ruff format` (`UP035` Callable import + formatting),
  committed in the `chore` that also widened CI to lint the whole repo (`.` instead
  of `src tests`), so this class of drift can no longer accumulate outside `src/`
  unnoticed.

---

## Resolved / obsolete after 2026-06-04 session

- **✅ OBSOLETE (2026-06-04) — Deploy preflight vs self-heal seed ordering:** the
  premise was a database created before Phase 15 (missing `read_model_logic_version`).
  There is exactly ONE dev DB on this host, already migrated by hand, and no backups —
  so no such old DB exists or can be restored. The dead provenance-migration code was
  removed entirely (`6be9004`): the registry-driven base DDL creates every column and
  the sidecar table on a fresh DB, so a new DB is complete from `create_schema` with no
  migration step. Preflight asserts tables that the base schema always creates → no
  ordering problem remains. (A briefly-added preflight self-heal that defended this
  non-scenario was reverted unpushed.) Nothing open here.

## Nothing open

All items from the 2026-06-04 session are resolved or obsolete.
