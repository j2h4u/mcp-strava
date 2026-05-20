# Codebase Structure

**Analysis Date:** 2026-05-20

## Directory Layout

```text
.
├── .env                    # Local Strava auth/config file; exists, contents not documented
├── .gitignore
├── .planning/
│   └── codebase/           # Generated mapping docs for this repo
├── Justfile                # `just test` wrapper around the smoke runner
├── SKILL.md                # Repo-specific usage notes
├── data/                   # Generated SQLite runtime storage
├── references/             # Design notes, reviews, research, and dependency context
├── scripts/                # Runtime entrypoints and source modules
└── tests/                  # Smoke tests
```

## Directory Purposes

**`scripts/`:**
- Purpose: runtime source root for the CLI and the `strava_lib` package.
- Contains: command dispatcher, test runner, domain modules, Strava integration code
- Key files: `scripts/cli.py`, `scripts/run_tests.py`, `scripts/strava_lib/`

**`scripts/strava_lib/`:**
- Purpose: all application logic, API adapters, data models, and analytics.
- Contains: SQLite/auth, sync pipeline, metrics, training model, reporting, sports registry, drift algorithm, schema docs
- Key files: `scripts/strava_lib/db.py`, `scripts/strava_lib/sync.py`, `scripts/strava_lib/metrics.py`, `scripts/strava_lib/training.py`, `scripts/strava_lib/analytics.py`, `scripts/strava_lib/report.py`, `scripts/strava_lib/trends.py`, `scripts/strava_lib/cardiac_drift.py`, `scripts/strava_lib/types.py`, `scripts/strava_lib/constants.py`, `scripts/strava_lib/sports.py`, `scripts/strava_lib/api_schema.py`, `scripts/strava_lib/strava_api_reference.py`

**`tests/`:**
- Purpose: smoke coverage for imports, pure functions, and the daily report path.
- Contains: a single lightweight test module
- Key files: `tests/test_smoke.py`

**`references/`:**
- Purpose: non-executable context for architecture, reviews, research, and API observations.
- Contains: review summaries and design notes
- Key files: `references/architecture-review-2026-05.md`, `references/dependency-graph-2026-05.md`, `references/sync-review-2026-05.md`, `references/coach-review-2026-05.md`, `references/kudos-api.md`

**`data/`:**
- Purpose: local persistence for activity history and derived state.
- Contains: SQLite database and WAL sidecars
- Key files: `data/strava.db`, `data/strava.db-wal`, `data/strava.db-shm`
- Generated: yes
- Committed: no

**`.planning/codebase/`:**
- Purpose: generated architecture/structure notes consumed by the GSD workflow.
- Contains: mapping documents
- Key files: `ARCHITECTURE.md`, `STRUCTURE.md`
- Generated: yes
- Committed: yes

## Key File Locations

**Entry Points:**
- `scripts/cli.py`: primary command-line entrypoint and command registry
- `scripts/run_tests.py`: smoke-test runner
- `Justfile`: `just test` alias to the smoke runner

**Configuration:**
- `scripts/strava_lib/constants.py`: athlete profile, thresholds, model constants, SQL fragments
- `scripts/strava_lib/db.py`: `.env` loading, token refresh, DB path resolution
- `.env`: local auth configuration for Strava access and refresh tokens

**Core Logic:**
- `scripts/strava_lib/sync.py`: API ingestion, backfill, kudos sync, rate limiting
- `scripts/strava_lib/metrics.py`: per-activity enrichment and signal extraction
- `scripts/strava_lib/training.py`: Banister model, progressive signal, weekly plan
- `scripts/strava_lib/analytics.py`: rolling efficiency and weekly digest
- `scripts/strava_lib/report.py`: daily report orchestration
- `scripts/strava_lib/trends.py`: week-level trend output
- `scripts/strava_lib/cardiac_drift.py`: Jenks-based drift clustering algorithm

**Contracts and Helpers:**
- `scripts/strava_lib/types.py`: dataclasses and serializer
- `scripts/strava_lib/sports.py`: sport registry and classification helpers
- `scripts/strava_lib/api_schema.py`: machine-readable API validation schema
- `scripts/strava_lib/strava_api_reference.py`: human-readable API catalog

**Testing:**
- `tests/test_smoke.py`: repo smoke coverage

## Naming Conventions

**Files:**
- Python modules use `snake_case.py`, for example `scripts/strava_lib/daily_report.py` does not exist; the current module is `report.py`.
- Reference and review docs use descriptive `kebab-case` with dates, for example `references/sync-review-2026-05.md`.
- Generated mapping docs use all-caps names, for example `ARCHITECTURE.md` and `STRUCTURE.md`.

**Functions:**
- CLI handlers use the `cmd_` prefix, for example `cmd_sync`, `cmd_report`, `cmd_weekly`.
- Public library functions use plain verbs, for example `sync_activities`, `daily_report`, `weekly_digest`, `calc_weekly_plan`.
- Private helpers use a leading underscore, for example `_fetch_with_retry`, `_generate_recommendation`, `_build_trimp_cases`.

**Variables:**
- Module-level constants are uppercase, for example `DB_PATH`, `ENV_PATH`, `STREAM_KEYS`.
- Dataclass fields use `snake_case`, for example `current_form`, `load_bonus`, `activity_templates`.

**Types:**
- Dataclasses use `PascalCase`, for example `DailyReport`, `WeeklyPlan`, `EnrichedActivity`, `StravaActivity`.
- Nested config namespaces also use `PascalCase`, for example `Config.Model.Banister`, `Config.Plan.Score`.

## Where to Add New Code

**New Feature:**
- Primary code: `scripts/strava_lib/` in the module that owns the behavior
- Tests: `tests/test_smoke.py` for a quick regression check, or a new focused test module under `tests/`

**New CLI Command:**
- Implementation: `scripts/cli.py`
- Supporting logic: add the real behavior in `scripts/strava_lib/` and keep `cli.py` as a dispatcher

**New Sync/API Behavior:**
- Implementation: `scripts/strava_lib/sync.py` for orchestration, `scripts/strava_lib/db.py` for HTTP/auth/SQLite helpers

**New Metrics or Model Logic:**
- Implementation: `scripts/strava_lib/metrics.py` for stream-derived metrics, `scripts/strava_lib/training.py` for model math, `scripts/strava_lib/analytics.py` for rolling summaries, `scripts/strava_lib/cardiac_drift.py` for the pure drift algorithm used by metrics

**New Data Contract:**
- Implementation: `scripts/strava_lib/types.py`
- Serialization edge: use `dc_to_dict()` at the CLI or API boundary

**New Sport Semantics:**
- Implementation: `scripts/strava_lib/sports.py`
- Config linkage: expose derived sets or windows through `scripts/strava_lib/constants.py`

**New Schema Validation:**
- Implementation: `scripts/strava_lib/api_schema.py`
- Human reference update: `scripts/strava_lib/strava_api_reference.py`

## Special Directories

**`data/`:**
- Purpose: local SQLite storage for historical activity, streams, zones, kudos, and sync logs
- Generated: yes
- Committed: no
- Safe modification: treat as runtime state only; do not hand-edit the database files

**`references/`:**
- Purpose: archived design and review context that explains current decisions
- Generated: no
- Committed: yes
- Safe modification: update only when the project’s current behavior changes in a way that should be recorded

**`.planning/codebase/`:**
- Purpose: generated architecture maps for downstream GSD planning/execution
- Generated: yes
- Committed: yes
- Safe modification: overwrite through the mapping workflow only

---

*Structure analysis: 2026-05-20*
