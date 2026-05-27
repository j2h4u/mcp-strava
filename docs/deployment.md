# mcp-strava Deployment Runbook

## Canonical Live Paths

Use `/opt/docker/mcp-strava` as canonical runtime state:

- DuckDB DB: `/opt/docker/mcp-strava/data/strava.duckdb` (container path `/runtime/data/strava.duckdb`)
- Tokens/env: `/opt/docker/mcp-strava/.env`
- Live CLI env overlay: `/opt/docker/mcp-strava/live.env`

Do not run refresh/admin flows against a repo-local development database unless you intentionally target a development snapshot.

## Bootstrap Live Runtime (One-Time)

Use this once to copy current local runtime into live root. This command must not print secrets.

```bash
python3 -m mcp_strava.deploy.prepare_runtime \
  --source-db data/strava.duckdb \
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
