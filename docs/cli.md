# CLI

Product commands read the local mirror through application services. They print human-readable output by default and support `--json` for the full service envelope with `data`, `freshness`, `completeness`, `warnings`, and `rationale`.

Admin/debug commands are local operator workflows and are not part of the MCP surface.

## Replacement Mapping

| Old command | New command/status | Notes |
| --- | --- | --- |
| `activities` | `workouts recent` | Compact recent workout list from the local mirror. |
| `gear` | removed | Live Strava gear lookup is not retained in the product surface. |
| `stats` | removed | Live Strava stats lookup is not retained in the product surface. |
| `sql` | `admin sql` | Local operator SQL only. |
| `refresh` | `admin token-refresh` | OAuth token refresh. Separate from mirror refresh. |
| `sync` | `admin mirror-refresh` | Local mirror refresh via refresh runtime. |
| `backfill` | `admin backfill` | Local mirror backfill workflow. |
| `backtest` | deferred | Planner backtest is not part of Phase 4 product CLI. |
| `trend` | deferred | Trend output is deferred until it has an application service wrapper. |
| `report` | `report daily` | Daily report product command. |
| `weekly` | `weekly` | Weekly summary product command. |
| `raw` | `admin raw` | Raw Strava API/debug command, admin only. |
| `log` | `admin log` | Local sync log inspection, admin only. |
| `kudos` | folded into workout metrics | Likes are retained as `kudos_count` in workout lists/details and `kudos_names` in workout detail, not as a separate CLI command. |
| `db-preflight` | `admin db-preflight` | Local DB safety check. |
| `db-check` | `admin db-check` | Local DB safety check alias. |
| `db-migrate` | `admin db-migrate` | Local DB migration with backup. |
| `db-refresh` | `admin mirror-refresh` | Local mirror refresh. Separate from `admin token-refresh`. |

## Product Commands

```bash
python -m mcp_strava report daily [--json]
python -m mcp_strava weekly [--json]
python -m mcp_strava workouts recent [--limit N] [--json]
python -m mcp_strava workout analyze <id|latest> [--json]
python -m mcp_strava freshness [--json]
```

## Admin Commands

```bash
python -m mcp_strava admin mirror-refresh [--force]
python -m mcp_strava admin token-refresh
python -m mcp_strava admin backfill [since-day]
python -m mcp_strava admin sql "SELECT ..."
python -m mcp_strava admin raw /athlete
python -m mcp_strava admin log [limit]
python -m mcp_strava admin db-preflight
python -m mcp_strava admin db-check
python -m mcp_strava admin db-migrate
```
