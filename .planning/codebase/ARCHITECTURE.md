<!-- refreshed: 2026-05-20 -->
# Architecture

**Analysis Date:** 2026-05-20

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                      CLI and Test Harness                   │
│   `scripts/cli.py`  ·  `scripts/run_tests.py`  ·  `Justfile`│
├──────────────────┬──────────────────┬───────────────────────┤
│  Command dispatch│   Smoke tests     │   Manual verification │
│  `cmd_*` funcs   │ `tests/test_smoke.py`                    │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Domain / Orchestration                   │
│ `sync.py` · `metrics.py` · `training.py` · `analytics.py`   │
│ `report.py` · `trends.py` · `sports.py` · `types.py`        │
│ `cardiac_drift.py`                                           │
└────────┬───────────────────────────────┬─────────────────────┘
         │                               │
         ▼                               ▼
┌──────────────────────────────┐   ┌──────────────────────────┐
│     Integration / Storage    │   │  Validation / Reference  │
│ `db.py` · `api_schema.py`    │   │ `strava_api_reference.py`│
│ `data/strava.db`             │   │                          │
└────────┬─────────────────────┘   └──────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ External Services                                            │
│ Strava REST API (`www.strava.com`)                           │
│ Local `.env` token store                                     │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| CLI dispatcher | Parse subcommands and print JSON or tabular output | `scripts/cli.py` |
| Sync pipeline | Incremental Strava ingest, backfill, kudos sync, rate limiting | `scripts/strava_lib/sync.py` |
| Database/auth layer | SQLite lifecycle, `.env` token refresh, API requests, TRIMP history queries | `scripts/strava_lib/db.py` |
| Typed contracts | Dataclasses for API payloads, metrics, plans, reports, and serialization | `scripts/strava_lib/types.py` |
| Sports registry | Sport semantics for training/running/HR-based filtering | `scripts/strava_lib/sports.py` |
| Metrics layer | Activity enrichment, decoupling, cardiac drift, HR recovery, vertical speed | `scripts/strava_lib/metrics.py` |
| Drift algorithm | Pure Jenks-based cardiac drift implementation used by metrics | `scripts/strava_lib/cardiac_drift.py` |
| Training layer | Banister model, progressive signal, weekly plan, forward simulation | `scripts/strava_lib/training.py` |
| Weekly analytics | Rolling window load/efficiency summaries and trend output | `scripts/strava_lib/analytics.py` |
| Daily report | 14-day panorama, ACWR, recommendation, safety warnings | `scripts/strava_lib/report.py` |
| Trend analysis | Weekly form/TiZ/crash-rate output | `scripts/strava_lib/trends.py` |
| Schema validation | Machine-readable Strava payload contract checks | `scripts/strava_lib/api_schema.py` |
| Human API reference | Field map and endpoint notes for Strava payloads | `scripts/strava_lib/strava_api_reference.py` |
| Smoke runner | Import and behavior smoke checks without pytest dependency | `scripts/run_tests.py` |

## Pattern Overview

**Overall:** thin CLI over a modular, SQLite-backed analytics core.

**Key Characteristics:**
- `scripts/cli.py` stays as a dispatcher; domain work lives in `scripts/strava_lib/*.py`.
- `types.py` is the contract boundary between modules and JSON output.
- `db.py` owns all Strava HTTP access, auth refresh, and SQLite connection details.
- `report.py`, `analytics.py`, and `training.py` orchestrate computed outputs from shared primitives instead of reimplementing formulas.
- `cardiac_drift.py` keeps the expensive Jenks-based drift algorithm isolated from the rest of the data model code.
- `api_schema.py` and `strava_api_reference.py` are adjacent validation/reference layers, not part of the hot path.

## Layers

**Command Layer:**
- Purpose: expose user-facing commands and format results.
- Location: `scripts/cli.py`
- Contains: `cmd_activities`, `cmd_sync`, `cmd_report`, `cmd_weekly`, `cmd_trend`, `cmd_stats`, `cmd_gear`, `cmd_sql`, `cmd_log`, `cmd_kudos`
- Depends on: `db.py`, `sync.py`, `training.py`, `analytics.py`, `report.py`, `trends.py`, `types.py`
- Used by: direct CLI invocation

**Domain / Computation Layer:**
- Purpose: compute derived training and analytics signals.
- Location: `scripts/strava_lib/metrics.py`, `scripts/strava_lib/training.py`, `scripts/strava_lib/analytics.py`, `scripts/strava_lib/report.py`, `scripts/strava_lib/trends.py`, `scripts/strava_lib/cardiac_drift.py`
- Contains: enrichment, Banister EWMA, progressive signal, weekly plan, rolling windows, recommendation logic, Jenks-based drift clustering
- Depends on: `types.py`, `constants.py`, `sports.py`, `db.py`
- Used by: `cli.py`, smoke tests, and neighboring modules

**Integration / Persistence Layer:**
- Purpose: fetch Strava data, refresh tokens, and persist/query SQLite.
- Location: `scripts/strava_lib/db.py`, `scripts/strava_lib/sync.py`
- Contains: `DbConn`, `init_db`, `refresh_token`, `api_request`, `sync_activities`, `backfill_activities`
- Depends on: standard library `sqlite3`, `urllib`, `json`, `os`
- Used by: all higher-level modules that need activity history or live API calls

**Contracts / Registry Layer:**
- Purpose: centralize schemas, dataclasses, and sport semantics.
- Location: `scripts/strava_lib/types.py`, `scripts/strava_lib/constants.py`, `scripts/strava_lib/sports.py`
- Contains: dataclass models, SQL fragments, sport-type registry, serializer helper
- Depends on: each other in a one-way order (`constants.py` imports `sports.py`)
- Used by: every computation module and CLI output path

**Validation / Reference Layer:**
- Purpose: describe Strava response shape and detect schema drift.
- Location: `scripts/strava_lib/api_schema.py`, `scripts/strava_lib/strava_api_reference.py`
- Contains: endpoint schemas, unknown-key detection, Summit-field checks, human-readable field catalog
- Depends on: `strava_api_reference.py` as the human source and `api_schema.py` as the machine-readable representation
- Used by: review tooling and future validation work; not wired into the current runtime path

## Data Flow

### Primary Request Path: Daily Report

1. `scripts/cli.py:227` dispatches `cmd_report()` and calls `daily_report()`.
2. `scripts/strava_lib/report.py:15` opens `DbConn`, loads 14 days of activities, and enriches each row through `metrics.enrich_activity()`.
3. `scripts/strava_lib/metrics.py:356` computes TRIMP, HR recovery, vertical speed, cardiac cost, HRR%, and cardiac drift from SQLite streams.
4. `scripts/strava_lib/training.py:43` and `scripts/strava_lib/training.py:443` compute Banister form and the weekly plan, including progressive signal input from `calc_progressive_signal()`.
5. `scripts/strava_lib/report.py:239` turns the raw signals into a recommendation and safety warnings.
6. `scripts/strava_lib/types.py:542` serializes the dataclass tree to JSON-safe output for the CLI.

### Ingest Path: Sync

1. `scripts/cli.py:105` dispatches `cmd_sync()` and calls `sync_activities()`.
2. `scripts/strava_lib/sync.py:132` initializes the schema, creates a `RateLimiter`, and decides quick vs full sync.
3. `scripts/strava_lib/db.py:166` performs HTTP requests; 401 triggers `refresh_token()` in `scripts/strava_lib/db.py:112`.
4. `scripts/strava_lib/sync.py:56` and `scripts/strava_lib/sync.py:318` parse activity summaries, streams, details, and kudos into SQLite tables.
5. `scripts/strava_lib/sync.py:132` writes the run summary into `sync_log`, which `cmd_log()` reads back.

### Analytics Paths

1. `scripts/cli.py:233` calls `weekly_digest()` for the weekly summary output.
2. `scripts/strava_lib/analytics.py:171` computes daily TRIMP history, rolling efficiency windows, and sport-level trends.
3. `scripts/cli.py:222` calls `compute_trends()` for the week-by-week form/velocity output.
4. `scripts/strava_lib/trends.py:12` reuses `calc_banister_series()` instead of recomputing Banister state locally.

**State Management:**
- Local persistence lives in `data/strava.db` with WAL sidecars `data/strava.db-wal` and `data/strava.db-shm`.
- `scripts/strava_lib/metrics.py` keeps a module-level `_hr_max_cache`.
- `scripts/strava_lib/sync.py` keeps per-run `RateLimiter` state in memory.
- `scripts/strava_lib/constants.py` attaches SQL fragments to `Config.SQL` at import time.

## Key Abstractions

**`Config`:**
- Purpose: single configuration tree for athlete profile, thresholds, model constants, and SQL fragments.
- Examples: `scripts/strava_lib/constants.py:17`
- Pattern: nested classes with eager, import-time values

**Dataclass contracts:**
- Purpose: stable schema for downstream modules and JSON output.
- Examples: `scripts/strava_lib/types.py:293`, `scripts/strava_lib/types.py:498`
- Pattern: parse raw API payloads into typed objects, then serialize via `dc_to_dict()`

**`SportMeta` registry:**
- Purpose: encode sport semantics once and reuse them across analytics, planning, and filtering.
- Examples: `scripts/strava_lib/sports.py:23`
- Pattern: central registry plus helper predicates like `is_training()` and `is_running()`

**`DbConn`:**
- Purpose: create short-lived SQLite connections with WAL mode and row access by column name.
- Examples: `scripts/strava_lib/db.py:21`
- Pattern: context manager around `sqlite3.connect(..., check_same_thread=False)`

**`RateLimiter`:**
- Purpose: prevent Strava API quota overruns and honor server-reported rate headers.
- Examples: `scripts/strava_lib/sync.py:21`
- Pattern: local token bucket plus header-driven override

## Entry Points

**Primary CLI entry point:**
- Location: `scripts/cli.py:325`
- Triggers: `python3 scripts/cli.py <command> [args]`
- Responsibilities: command dispatch, output formatting, process exit codes

**Test entry point:**
- Location: `scripts/run_tests.py:25`
- Triggers: `python3 scripts/run_tests.py`
- Responsibilities: load `tests/test_smoke.py`, execute all `test_*` functions, report pass/fail

**Smoke suite:**
- Location: `tests/test_smoke.py:29`
- Triggers: `scripts/run_tests.py` or manual import
- Responsibilities: verify imports, pure functions, daily report path, and registry behavior

**Justfile entry point:**
- Location: `Justfile`
- Triggers: `just test`
- Responsibilities: forward to the smoke runner

## Architectural Constraints

- **Threading:** synchronous single-process CLI. No async runtime, queue worker, or background service is present.
- **SQLite access:** `DbConn` uses WAL and `check_same_thread=False`, but the commands run as short-lived one-shot processes.
- **Global state:** module-level `_hr_max_cache` in `metrics.py`, `Config.SQL` late binding in `constants.py`, and `RateLimiter` counters in `sync.py`.
- **Circular imports:** no active cycle is required for runtime flow. `constants.py` imports `sports.py` after `Config` is defined, then attaches SQL fragments.
- **Token storage:** `refresh_token()` writes new credentials back to `.env`; the file is local configuration, not a secretless cache.
- **Validation boundary:** `api_schema.py` exists as a validation layer, but current runtime commands do not call it.

## Anti-Patterns

### Fat CLI

**What happens:** new logic is added directly to `scripts/cli.py`, turning the dispatcher into a second domain layer.
**Why it's wrong:** it hides behavior from the shared modules, makes testing harder, and duplicates logic already present in `sync.py`, `training.py`, or `report.py`.
**Do this instead:** add ingest logic in `scripts/strava_lib/sync.py`, computed metrics in `scripts/strava_lib/metrics.py`, and training math in `scripts/strava_lib/training.py`.

### Raw Dict Leakage

**What happens:** new outputs are built as ad hoc nested dicts and passed across modules.
**Why it's wrong:** the codebase already uses `scripts/strava_lib/types.py` as the cross-module contract, and raw dicts make the data flow fragile.
**Do this instead:** add a dataclass in `scripts/strava_lib/types.py` and serialize it at the edge with `dc_to_dict()`.

## Error Handling

**Strategy:** fail closed at the command boundary, return `None` for insufficient data inside pure analytics functions, and retry transient Strava failures in `sync.py`.

**Patterns:**
- `sync.py` retries network and HTTP failures with backoff and 429 handling.
- `db.py` refreshes OAuth tokens on 401 and converts token-refresh problems into actionable `RuntimeError`s.
- `report.py` and `analytics.py` return `None` when there is not enough data rather than inventing defaults.
- `cli.py` wraps sync commands with traceback printing and a last-chance sync_log write.

## Cross-Cutting Concerns

**Logging:** `sync.py` writes progress and failures to stderr; `cli.py` prints user-facing JSON or plain text; `sync_log` persists audit history in SQLite.

**Validation:** schema drift is represented in `scripts/strava_lib/api_schema.py`; runtime smoke coverage lives in `tests/test_smoke.py`.

**Authentication:** OAuth refresh is centralized in `scripts/strava_lib/db.py:112`; credentials are loaded from and written back to `.env`.

---

*Architecture analysis: 2026-05-20*
