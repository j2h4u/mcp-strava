
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

## Still open after 2026-06-04 session

- **⏳ Deploy preflight vs self-heal seed ordering** (above) — the one genuinely
  unclosed item. Deploy-layer fix: run the additive sidecar/provenance migration
  before/within preflight, or make preflight tolerant of the repository's idempotent
  self-heal seed, so a pre-Phase-15 live DB self-migrates instead of crash-looping.
  Low urgency (only bites a DB created before Phase 15; the live dev instance was
  already migrated by hand).
