# mcp-strava Deployment Runbook

## Canonical Live Paths

After live cutover, use `/opt/docker/mcp-strava` as canonical runtime state:

- DuckDB DB after Phase 8: `/opt/docker/mcp-strava/data/strava.duckdb` (container path `/runtime/data/strava.duckdb`)
- SQLite DB before Phase 8 and rollback input: `/opt/docker/mcp-strava/data/strava.db`
- Tokens/env: `/opt/docker/mcp-strava/.env`
- Live CLI env overlay: `/opt/docker/mcp-strava/live.env`

Do not run refresh/admin flows against repo `data/strava.db` after cutover unless you intentionally target a development snapshot.

## Bootstrap Live Runtime (One-Time)

Use this once to copy current local runtime into live root. This command must not print secrets.

```bash
python3 -m mcp_strava.deploy.prepare_runtime \
  --source-db data/strava.db \
  --target-root /opt/docker/mcp-strava \
  --copy-env \
  --source-env .env
```

For live refresh/admin commands, either source `/opt/docker/mcp-strava/live.env` or set:

- `MCP_STRAVA_DB_PATH=/opt/docker/mcp-strava/data/strava.duckdb`
- `MCP_STRAVA_TOKEN_PATH=/opt/docker/mcp-strava/.env`

## Backend Build/Run Checks (Autonomous-Safe)

```bash
docker compose -f deploy/docker-compose.yml config
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

Optional direct backend smoke when an explicit loopback port is enabled:

```bash
python3 -m mcp_strava.deploy.smoke \
  --url http://127.0.0.1:${MCP_STRAVA_HTTP_PORT:-8000}/mcp \
  --expect-tool get_fitness_state
```

## Phase 7 Read-Model Validation

Before accepting the materialized read-model runtime, validate against the live Docker state or a copied live database. Keep the pinned pre-Phase-7 backup until migration, materialization, parity, Docker smoke, and the p95 gate have all passed.

1. Confirm the live database backup exists and is pinned outside ordinary cleanup:

```bash
ls -lh /opt/docker/mcp-strava/data/backups/
```

2. Run preflight against the live database without printing secrets:

```bash
MCP_STRAVA_DB_PATH=/opt/docker/mcp-strava/data/strava.db \
MCP_STRAVA_TOKEN_PATH=/opt/docker/mcp-strava/.env \
python -m mcp_strava admin db-preflight --json
```

3. Migrate the live database to `user_version=7`:

```bash
MCP_STRAVA_DB_PATH=/opt/docker/mcp-strava/data/strava.db \
MCP_STRAVA_TOKEN_PATH=/opt/docker/mcp-strava/.env \
python -m mcp_strava admin db-migrate --apply
```

4. Run the runtime-owned refresh/materialization path. There is no MCP or manual read-model recompute tool; read-model facts are materialized below the refresh runtime:

```bash
MCP_STRAVA_DB_PATH=/opt/docker/mcp-strava/data/strava.db \
MCP_STRAVA_TOKEN_PATH=/opt/docker/mcp-strava/.env \
python -m mcp_strava admin mirror-refresh --force
```

5. Run post-check/parity and confirm read-model facts exist:

```bash
MCP_STRAVA_DB_PATH=/opt/docker/mcp-strava/data/strava.db \
python -m mcp_strava admin db-check --json

sqlite3 /opt/docker/mcp-strava/data/strava.db \
  "SELECT 'activity_metric_facts', COUNT(*) FROM activity_metric_facts
   UNION ALL SELECT 'daily_load_facts', COUNT(*) FROM daily_load_facts
   UNION ALL SELECT 'training_model_daily', COUNT(*) FROM training_model_daily
   UNION ALL SELECT 'rolling_period_facts', COUNT(*) FROM rolling_period_facts;"
```

6. Start the Docker MCP runtime and run transport smoke:

```bash
docker compose -f deploy/docker-compose.yml up -d --force-recreate --wait
just test
```

7. Run the explicit warm p95 gate. This measures tool calls after startup and fails if any MCP tool exceeds the 500 ms p95 target:

```bash
just mcp-read-model-perf 20 2 500
```

The p95 gate covers all product MCP tools: `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, and `project_fitness_state`.

Do not remove the pinned pre-Phase-7 backup until the commands above pass and the key MCP outputs still match the expected live mirror shape.

## Phase 8 DuckDB Cutover Validation

This is the live storage cutover from pinned SQLite input to DuckDB primary runtime. It must not run a full Strava resync. Keep the pinned pre-Phase-8 SQLite backup until DuckDB parity, Docker smoke, MCP smoke, the 100 ms p95 gate, and the first accepted post-cutover refresh pass have all been recorded.

1. Stop or quiesce runtime writers before touching live storage:

```bash
docker compose -f deploy/docker-compose.yml stop mcp-strava
```

2. Confirm there is no active refresh lease on the SQLite source. An active lease blocks cutover; wait for it to finish or resolve the refresh checkpoint before continuing.

```bash
MCP_STRAVA_DB_PATH=/opt/docker/mcp-strava/data/strava.db \
MCP_STRAVA_TOKEN_PATH=/opt/docker/mcp-strava/.env \
python -m mcp_strava admin db-preflight --json
```

3. Tag the currently accepted image before rebuilding, so rollback has an immutable pre-cutover runtime image:

```bash
docker image tag mcp-strava:latest mcp-strava:pre-phase-8
```

4. Run the local admin DuckDB cutover from the stable SQLite source. The command creates a pinned pre-Phase-8 SQLite backup, migrates from that backup/copy, writes the DuckDB target, and reports row-count parity plus rollback metadata.

```bash
python -m mcp_strava admin duckdb-cutover \
  --source-sqlite /opt/docker/mcp-strava/data/strava.db \
  --target-duckdb /opt/docker/mcp-strava/data/strava.duckdb \
  --backup-dir /opt/docker/mcp-strava/data/backups \
  --apply \
  --confirm-live-cutover \
  --json
```

The target above is the host-mounted form of the canonical runtime DB. The container must see the same file as `/runtime/data/strava.duckdb`.

5. Run DuckDB post-checks and record the pinned backup path, DuckDB target path, parity result, and rollback image tag:

```bash
MCP_STRAVA_DB_PATH=/opt/docker/mcp-strava/data/strava.duckdb \
python -m mcp_strava.deploy.preflight --db /opt/docker/mcp-strava/data/strava.duckdb
```

6. Rebuild and recreate the Docker runtime with `MCP_STRAVA_DB_PATH=/runtime/data/strava.duckdb`:

```bash
docker compose -f deploy/docker-compose.yml config
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d --force-recreate --wait
```

7. Validate the container runtime uses Python 3.14 and imports DuckDB:

```bash
docker compose -f deploy/docker-compose.yml exec -T mcp-strava python -c "import sys, duckdb; assert sys.version_info[:2] == (3, 14); print(sys.version.split()[0], duckdb.__version__)"
```

8. Run Docker and MCP acceptance gates. These use owner-process/HTTP validation for live DuckDB; health, smoke, and perf must not independently open the live DuckDB file read-write.

```bash
just test
just mcp-smoke-full
just mcp-read-model-perf 20 2 100
```

The smoke and p95 gates cover exactly six product MCP tools: `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, `project_fitness_state`, and `get_training_aggregates`. The MCP surface must not include sync, backfill, raw, SQL, token, admin, debug, gear, migration, or recompute tools.

9. Record the first accepted post-cutover refresh pass from the owner process before releasing the pinned backup:

```bash
docker compose -f deploy/docker-compose.yml logs --since 2h mcp-strava
```

Accept only a runtime-owned `refresh_ok` pass, or an explicitly recorded refresh request consumption that leaves read-model facts current. Do not run a standalone live DuckDB refresh worker while the owner process is up.

Full Strava resync is not a rollback or validation mechanism for Phase 8.

## Phase 9 Product Bundle Verification

Phase 9 validation proves factual product bundles and the consolidated CLI read paths without using gateway or infrastructure wrapper smoke. Every MCP smoke command below talks directly to this server at `http://127.0.0.1:8080/mcp`.

1. Run targeted bundle and direct-client tests:

```bash
uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py
```

2. Run CLI/product boundary tests:

```bash
uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py
```

3. Run the dedicated direct MCP bundle smoke recipe. This starts the local Docker service and calls the six-tool MCP server directly; it does not call the MCP gateway.

```bash
just phase9-bundle-smoke
```

4. Run the ordinary Docker smoke and full direct MCP smoke:

```bash
just test
just mcp-smoke-full
```

5. Run the Docker warm p95 gate at the Phase 9 target. The gate must cover all six product tools and keep each warm p95 under 500 ms:

```bash
just mcp-read-model-perf 20 2 500
```

6. If Docker is unavailable, use the non-Docker fallback against fixture-backed bundle service calls. This measures `get_training_aggregates_service` for `daily_brief`, `weekly_digest`, and `historical_facts` under the same 500 ms warm p95 target:

```bash
uv run python - <<'PY'
import statistics
import tempfile
import time
from datetime import datetime
from pathlib import Path

from mcp_strava.adapters.duckdb.connection import open_fixture_db
from mcp_strava.application.aggregate_services import AggregateServiceRequest, get_training_aggregates_service
from tests.test_training_aggregates import _aggregate_fixture

bundles = ("daily_brief", "weekly_digest", "historical_facts")
samples = 20
warmup = 2
threshold_ms = 500.0

with tempfile.TemporaryDirectory() as tmp:
    db_path = _aggregate_fixture(Path(tmp) / "phase9-bundle-perf.duckdb")
    conn = open_fixture_db(db_path)
    try:
        for bundle_id in bundles:
            request = AggregateServiceRequest(
                metric_ids=(),
                bundle_id=bundle_id,
                bucket="all_time",
                start_day="2026-05-01",
                end_day_exclusive="2026-05-25",
                scope="both",
            )
            for _ in range(warmup):
                get_training_aggregates_service(request, now=datetime(2026, 5, 24, 9, 0, 0), signal_first_use=False, connection=conn)
            timings = []
            for _ in range(samples):
                started = time.perf_counter()
                get_training_aggregates_service(request, now=datetime(2026, 5, 24, 9, 0, 0), signal_first_use=False, connection=conn)
                timings.append((time.perf_counter() - started) * 1000)
            p95 = statistics.quantiles(timings, n=20)[18]
            print(f"{bundle_id}: p95={p95:.3f}ms")
            if p95 > threshold_ms:
                raise SystemExit(f"{bundle_id} p95 exceeded {threshold_ms}ms")
    finally:
        conn.close()
PY
```

Do not run gateway registration, gateway catalog mutation, raw SQL, sync, backfill, token, log, or recompute commands as Phase 9 product verification. Those remain local admin or deployment operations below the MCP/product surface.

## Phase 8 DuckDB Rollback

Rollback means stopping the DuckDB runtime and returning to the pinned SQLite backup plus the pre-cutover image/config. Do not delete the pinned pre-Phase-8 SQLite backup as part of rollback or validation.

1. Stop the DuckDB runtime:

```bash
docker compose -f deploy/docker-compose.yml stop mcp-strava
```

2. Restore or repoint runtime config to the pinned SQLite backup and previous DB path, then use the pre-cutover image tag:

```bash
docker image tag mcp-strava:pre-phase-8 mcp-strava:latest
```

3. Run SQLite preflight, recreate Docker, and rerun owner-process/HTTP smoke and p95 validation:

```bash
MCP_STRAVA_DB_PATH=/opt/docker/mcp-strava/data/strava.db \
MCP_STRAVA_TOKEN_PATH=/opt/docker/mcp-strava/.env \
python -m mcp_strava admin db-preflight --json

docker compose -f deploy/docker-compose.yml up -d --force-recreate --wait
just test
just mcp-smoke-full
just mcp-read-model-perf 20 2 100
```

Full Strava resync is not a rollback path. The local pinned SQLite backup and `mcp-strava:pre-phase-8` image tag are the rollback source of truth.

## Gateway Registration Dry-Run (Default)

Dry-run only. No writes, no restart.

```bash
python3 deploy/gateway_register.py \
  --catalog /opt/docker/mcp-gateway/catalog.yaml \
  --compose /opt/docker/mcp-gateway/compose.yaml \
  --service strava \
  --url http://mcp-strava:8080/mcp
```

## Live Apply (Operator-Approved Only)

Before any command that writes `/opt/docker/mcp-gateway/catalog.yaml`, writes `/opt/docker/mcp-gateway/compose.yaml`, or restarts `mcp-gateway`, stop and get explicit operator approval.

The approved live command must include both flags:

```bash
python3 deploy/gateway_register.py \
  --apply \
  --confirm-live-gateway \
  --catalog /opt/docker/mcp-gateway/catalog.yaml \
  --compose /opt/docker/mcp-gateway/compose.yaml \
  --service strava \
  --url http://mcp-strava:8080/mcp
```

Without `--apply --confirm-live-gateway`, the helper must not mutate live files.

## Backup/Rollback Semantics

On apply mode, helper order is:

1. Prevalidate compose.
2. Backup both live files.
3. Write both files atomically.
4. Validate new compose.
5. Restart gateway.

If a post-backup step fails, helper restores both files from latest backups and runs:

```bash
docker compose --env-file /opt/docker/mcp-gateway/.env -f /opt/docker/mcp-gateway/compose.yaml up -d --force-recreate mcp-gateway
```

Manual rollback must do the same restore-both + restart-old-config sequence.

## Rollback Restart Failure Contingency

If rollback restart fails:

1. Stop automation. Do not rerun mutation.
2. Verify restored backup paths used by helper.
3. Run:

```bash
docker compose --env-file /opt/docker/mcp-gateway/.env -f /opt/docker/mcp-gateway/compose.yaml config
docker compose --env-file /opt/docker/mcp-gateway/.env -f /opt/docker/mcp-gateway/compose.yaml ps
docker compose --env-file /opt/docker/mcp-gateway/.env -f /opt/docker/mcp-gateway/compose.yaml logs --tail=200 mcp-gateway
```

4. Restore previous timestamped backup or escalate manual recovery before any further writes.

Never print `.env` contents in logs, tests, or summaries.
