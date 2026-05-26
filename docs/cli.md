# CLI

Product commands read the local mirror through application services. They print human-readable output by default and support `--json` for the full service envelope with `data`, `freshness`, `completeness`, `warnings`, and `rationale`.

Admin/debug commands are local operator workflows and are not part of the MCP surface.

## Replacement Mapping

| Old command | New command/status | Notes |
| --- | --- | --- |
| `activities` | `workouts recent` | Compact read-model workout list from the local mirror, with `--limit`, `--start-date`, `--end-date`, and `--sport` filters. |
| `gear` | available via workout detail | Supported mirrored gear facts appear in `workout analyze <id> --json` and daily product bundles when present; live Strava gear lookup is not retained. |
| `stats` | folded into product bundle | Athlete/load/status facts are available through `report daily --json`, `weekly --json`, and MCP product bundles. |
| `sql` | `admin sql` | Local operator SQL only. |
| `refresh` | `admin token-refresh` | OAuth token refresh. Separate from mirror refresh. |
| `sync` | `admin mirror-refresh` | Local mirror refresh via refresh runtime. |
| `backfill` | `admin backfill` | Local mirror backfill workflow. |
| `backtest` | removed | Historical planner replay is not a current product/admin runtime capability. |
| `trend` | folded into `weekly --json` | Weekly digest exposes aggregate-backed period trend facts instead of the old standalone trend command. |
| `report` | `report daily` | Daily report product command. |
| `weekly` | `weekly` | Weekly summary product command. |
| `raw` | `admin raw` | Raw Strava API/debug command, admin only. |
| `log` | `admin log` | Local sync log inspection, admin only. |
| `kudos` | available via workout detail | Likes are retained as `kudos_count` in workout lists/details and `kudos_names` in workout detail, not as a separate CLI command. |
| `db-preflight` | `admin db-preflight` | Local DB safety check. |
| `db-check` | `admin db-check` | Local DB safety check alias. |
| `db-migrate` | `admin db-migrate` | Local DB migration with backup. |
| `db-refresh` | `admin mirror-refresh` | Local mirror refresh. Separate from `admin token-refresh`. |

## Product Commands

```bash
python -m mcp_strava report daily [--json]
python -m mcp_strava weekly [--json]
python -m mcp_strava workouts recent [--limit N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] [--sport SPORT] [--json]
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
python -m mcp_strava admin duckdb-cutover --source-sqlite <path> --target-duckdb <path> --backup-dir <path> [--apply --confirm-live-cutover] [--json]
```
