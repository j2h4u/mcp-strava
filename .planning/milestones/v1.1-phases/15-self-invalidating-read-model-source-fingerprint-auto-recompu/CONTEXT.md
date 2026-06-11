# Phase 15 — Context

Source: expert-panel design session (System Architect + Build/DevOps + QA + Researcher), Kaizen-trimmed. Driven by two findings while comparing the live Hermes Strava script against this MCP server, plus a developer-ergonomics requirement.

## Why this phase exists

1. **Zero-knob auto-recompute (the headline).** The read-model already auto-recomputes when *source data* changes (`source_hash` → `metric_dirty_activities` dirty queue → `materialize_read_model`, run every refresh cycle). But when a developer changes a *constant/formula/computed field*, nothing notices: `CURRENT_METRIC_VERSION` is a hand-maintained int (`adapters/duckdb/repository.py:31`) and the mass-recompute method `enqueue_metric_version_recompute` (`repository.py:534`) is written but **wired to nothing**. Developer requirement: change a constant/field/logic and have affected facts recompute automatically — no manual version bump, no manual recompute trigger.
2. **Walk TRIMP discount (forgotten Hermes edit).** The live Hermes script discounts Walk activities in the Banister load model (`WALK_TRIMP_DISCOUNT = 0.5`, hand-tuned). This MCP server has no such constant — walks count at **full** TRIMP (`read_model_materializer.py:248,280` set `effective_trimp = observed_trimp`), inflating fatigue/ACWR/form for an athlete who walks daily.
3. **Workout time granularity.** The daily-brief workout rows expose only `activity_date` (calendar date) — no time-of-day. Want `start_time_local` (HH:MM) + a read-time relative-time field.

## Verified current-state facts (file:line)

- `CURRENT_METRIC_VERSION = 1` — `adapters/duckdb/repository.py:31`; all reads filter facts by exact equality `f.metric_version = ?` (e.g. `repository.py:783-789`; identical in fetch_daily_load_facts / fetch_latest_training_model_day / rolling).
- Dirty-queue automation works for source data: `update_activity_source_state_and_enqueue_dirty` computes `source_hash` via `_semantic_json_hash` (`repository.py:400`, sort_keys=True → deterministic); `materialize_read_model` drains the queue inside one `begin()/commit()` (`read_model_materializer.py:404-460`); refresh runtime calls `materialize_read_model_stage` every cycle (`refresh/runtime.py:108/181/275`, also `refresh/_sync_ops.py:269`, `refresh/worker.py:60`).
- `enqueue_metric_version_recompute(metric_version, reason, queued_at)` — `repository.py:534` — **orphan, zero callers** (verified). It walks `activity_source_state` and enqueues all activities at the given version.
- `effective_trimp` lives at the **daily** grain; materializer sets `effective = observed` (`read_model_materializer.py:248,280`). `repository.observed_trimp_history` sums TRIMP per day with an *optional* sport filter and **no per-sport discount**.
- Aggregate read path does **not** filter by `metric_version` — it aggregates across all versions present and only reports `COUNT(DISTINCT metric_version) AS metric_version_count` as a diagnostic (`adapters/duckdb/aggregate_queries.py:704-723`, also ~790/873). Harmless today (one version) → becomes a blend risk once we bump versions. **(QA finding R11.)**
- Docker install: `deploy/Dockerfile:19` does `pip install /app` (normal source install) — `.py` source is present in site-packages, so `inspect.getsource` works in the container as in the editable dev venv. **(QA R9 resolved — not a blocker.)**
- Python 3.14 (uv). Suite green: 348 passed. ruff+pyright must stay green; CI runs `ruff format --check`.

## Chosen design (Variant 1 — auto-fingerprint)

### Logic fingerprint
- `COMPUTE_SOURCE_MODULES` — an explicit tuple in `metric_registry.py` naming the compute surface as **modules**: `metrics`, `cardiac_drift`, `training`, `hr_zones`, `constants`, `adapters.duckdb.read_model_materializer`, `adapters.duckdb.repository`. (Repository is included because TRIMP/zone/CC logic lives there as SQL strings — `build_trimp_sql`, `build_zones_sql`, zone/CC builders.)
- `compute_logic_fingerprint()` = `sha256` over the concatenated `inspect.getsource(import_module(m))` for each module, sorted. Text-based (NOT `co_code`, NOT builtin `hash()`) → stable across Python 3.14 point releases and across processes; no PYTHONHASHSEED concern.
- **Coverage is automatic by construction:** the unit is the *module*, not the symbol. Adding a constant/metric/SQL builder anywhere in those modules moves the fingerprint with zero edits to any list. This is the dbt `state:modified` / Python `.pyc` hash-invalidation pattern.

### Version storage (keep the int)
- `metric_version` stays a `BIGINT` (load-bearing in 4 composite PKs + every read filter + `v_metric_version_status`). Do NOT turn it into a hash string.
- New singleton table `read_model_logic_version(metric_version BIGINT, logic_fingerprint VARCHAR, changed_at VARCHAR)`. The int becomes a monotonic counter the system bumps itself.
- Delete the hand-maintained `CURRENT_METRIC_VERSION = 1`; reads/materializer source the current int from the table (`repo.current_metric_version()`).

### Trigger (single chokepoint)
At the top of `materialize_read_model_stage` (`refresh/_sync_ops.py:269`) — the one point all materialize paths funnel through (daily cycle, backfill, worker):
```
stored = repo.current_logic_version()
live   = compute_logic_fingerprint()
if stored.fingerprint != live:
    new = stored.metric_version + 1
    repo.bump_logic_version(new, live, now)
    repo.enqueue_metric_version_recompute(new, reason="logic_fingerprint_changed", queued_at=now)   # wire the orphan
materialize at repo.current_metric_version()
```
- **Migration seeds fingerprint = current** so the first run after deploy does NOT spuriously recompute (stored == live by construction); only a subsequent edit triggers the first real auto-recompute.
- **Empty/fresh DB** (no stored fingerprint / no facts) → adopt-current silently, no recompute.

### Atomic cutover & the R11 fix
- New facts land at the new int; reads pin the current int by exact equality → they see **either** zero-new (status stale/unavailable) **or** complete-new, never a blend. Atomic cutover is free for point reads.
- **R11 fix (required):** add `metric_version = current` to the aggregate query `WHERE` (`aggregate_queries.py`) so weekly/monthly digests also pin the current version and never blend old+new mid-recompute. Keep `metric_version_count` as a tripwire.

### Observability (self-explanatory output)
On auto-recompute, emit a log event with: `stored_fingerprint`, `current_fingerprint`, `reason`, `activities_enqueued` (count), `queued_at`; extend the materialize-ok event with `metric_version` + `duration_ms`; stamp `trigger_reason="logic_fingerprint_changed"` on the refresh-run record. (Fires only on mismatch — its presence explains why the next materialize is large.)

### Walk discount (rides on the fingerprint)
- `WALK_TRIMP_DISCOUNT = 0.5` — internal constant in `constants.py` alongside the Banister/Plan model params (NO env). Default 0.5 (the developer's last hand-tuned value).
- Pure domain function (in `metrics.py`, domain layer) computing discounted daily effective TRIMP; per-sport daily aggregation in `repository` (group by day+sport, multiply Walk by discount, sum); wired in the materializer so `effective_trimp != observed_trimp` for Walk.
- Because `constants.py` is in `COMPUTE_SOURCE_MODULES`, changing the discount changes the fingerprint → history auto-recomputes. This is the first real proof of the zero-knob outcome.

### Time fields
- `start_time_local` (HH:MM) — materialized fact column derived from `start_date_local`; surfaced in the workout payload (`_activity_payload` / list_workouts compact row in `application/metric_services.py`).
- `relative_time` — computed at **read** time in the service layer (depends on `now`, not materialized). Rule: `< 24h → "Hh Mm"`; `>= 1 day → "Nd Hh"` (minutes dropped).

## Kaizen gate — what was CUT (do NOT build)
- **Per-metric fingerprinting** → whole-model epoch instead. Metrics are entangled (trimp→effective_trimp→Banister→rolling) and recompute is sub-second. Deliberate exception to the project's fine-grained-default; flagged as such. (beads ticket if recompute ever stops being cheap.)
- **AST import-walk auto-discovery** of the module set → use the explicit tuple + a completeness test (poka-yoke).
- **Synchronous blocking recompute on read** → async dirty-queue path only.
- **Second entrypoint trigger** → single chokepoint at the materialize stage.
- **Old-version reaper** → deferred; over-retention is a non-concern on a single dev DB. (Not needed for R11 once the aggregate path filters by version.)
- **Manifest-of-constant-values fingerprint** (QA's proposal) → OVERRULED: it reintroduces the hand-maintained list (the knob). Whole-module source hashing covers constants by construction. QA dissent noted.
- **Accepted tradeoff:** a comment/format-only edit to a hashed module triggers a sub-second recompute. Fine — over-invalidation costs only sub-second compute; under-invalidation costs correctness.

## Required tests
- **Zero-knob proof:** change a constant (e.g. WALK_TRIMP_DISCOUNT) → next materialize cycle auto-bumps version + recomputes, no manual step.
- **Completeness guard:** every module transitively imported by `read_model_materializer`'s compute path is present in `COMPUTE_SOURCE_MODULES` → CI failure if a new compute module is added but not listed (closes the one residual knob).
- **Fingerprint determinism:** sha256 over source text is identical across processes / PYTHONHASHSEED-varied subprocesses.
- **Packaged-install smoke:** fingerprint computes without `OSError` under the `pip install /app` Docker image (getsource works on installed source).
- **No version blending:** seed old-version facts, bump fingerprint, assert point reads AND aggregate reads return only-current-or-empty, never blended (covers R10/R11).
- **Walk discount:** a day with a Walk yields discounted daily `effective_trimp`; non-walk days unaffected; Banister series consumes the discounted value.
- **relative_time formatting:** `<24h → "Hh Mm"`, `>=1 day → "Nd Hh"` (minutes dropped); boundary at 24h.

## Suggested wave structure (planner to refine)
- **Wave 1 — auto-invalidation infra:** sidecar table + migration (seed=current), `compute_logic_fingerprint()` + `COMPUTE_SOURCE_MODULES`, wire orphan + trigger in materialize stage, source the int from the table, aggregate version filter, logging. Tests: zero-knob, completeness, determinism, packaged-install, no-blend.
- **Wave 2 (depends on W1) — features riding on it:** walk discount (constant + domain fn + per-sport aggregation + materializer wiring); time fields (start_time_local materialized + relative_time at read). Tests: walk discount per-sport, relative_time formatting. These changes flip the fingerprint → exercise the auto-recompute end-to-end.

## Constraints
core/domain separation enforced (domain modules can't import storage/adapters — Phase 10/12); no env config (internal constants only); no backward-compat required; single dev instance, no prod; clean > fast; Python 3.14; `just test`/pytest + ruff (incl. `format --check`) + pyright must end green.
