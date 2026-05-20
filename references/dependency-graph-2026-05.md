# Module Dependency Graph — Final State (May 9, 2026)

## Post-Decoupling Architecture

```
cli.py (263 lines) — pure CLI dispatcher, imports from 6 library modules
  ├── strava_lib.sync        ← sync_activities, backfill_activities
  ├── strava_lib.trends      ← compute_trends
  ├── strava_lib.training    ← calc_banister, calc_weekly_plan, forward_simulate
  ├── strava_lib.analytics   ← weekly_digest
  ├── strava_lib.report      ← daily_report
  ├── strava_lib.db          ← DbConn, get_db, refresh_token, api_request, get_daily_trimp_history
  ├── strava_lib.types       ← parse_strava_activity, parse_strava_athlete, dc_to_dict
  └── strava_lib.constants   ← Config, ZONES_SQL, TRIMP_SQL

strava_lib/sync.py (210 lines)
  └── strava_lib.db, types, constants, sports

strava_lib/trends.py (126 lines)
  └── strava_lib.db, constants

strava_lib/training.py (523 lines) — Banister, ACWR, weekly plan, forward_simulate
  └── strava_lib.db, metrics, types, constants

strava_lib/analytics.py (339 lines)
  └── strava_lib.db, types, constants

strava_lib/report.py (250 lines)
  └── strava_lib.db, metrics, training, types, constants

strava_lib/metrics.py (313 lines)
  └── strava_lib.types, constants

strava_lib/db.py (171 lines)
  └── strava_lib.constants

strava_lib/constants.py (114 lines)
  └── strava_lib.sports

strava_lib/types.py (470 lines) — zero dependencies, used by 6 modules
strava_lib/sports.py (262 lines) — zero dependencies, used by 2 modules
```

## Coupling Metrics (Final)

| Module | Dependencies | Used By | Issues |
|--------|-------------|---------|--------|
| cli.py | 6 | 0 | Pure dispatch, no domain logic leaked |
| types.py | 0 | 6 | ✅ Clean |
| constants.py | 1 | 6 | ✅ Clean |
| sports.py | 0 | 2 | ✅ Clean |
| sync.py | 4 | 1 | ✅ Single responsibility |
| trends.py | 2 | 1 | ✅ Single responsibility |
| metrics.py | 2 | 3 | ✅ Clean |
| db.py | 1 | 5 | ✅ Clean |
| training.py | 4 | 2 | ✅ Acceptable |
| report.py | 5 | 1 | Acceptable orchestrator |
| analytics.py | 3 | 1 | ✅ Clean |

## What Was Fixed

1. **Zero cross-module private imports** — `_enrich_activity`, `_ewma`, `_trend` made public
2. **Zero duplicated Banister logic** — `forward_simulate()` extracted to training.py
3. **cli.py reduced 54%** — 574 → 263 lines
4. **New modules**: `sync.py` (API operations), `trends.py` (training quality trends)
5. **Dead imports removed**: `_enrich_activity` from cli, `_form_zone` from report, `iproduct`/`ddate` from backtest
6. **Cron jobs updated** to use `cli.py`
