# mcp-strava Deployment Runbook

## Canonical Live Paths

After live cutover, use `/opt/docker/mcp-strava` as canonical runtime state:

- DB: `/opt/docker/mcp-strava/data/strava.db`
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

- `MCP_STRAVA_DB_PATH=/opt/docker/mcp-strava/data/strava.db`
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

## Gateway Registration Dry-Run (Default)

Dry-run only. No writes, no restart.

```bash
python3 deploy/gateway_register.py \
  --catalog /opt/docker/mcp-gateway/catalog.yaml \
  --compose /opt/docker/mcp-gateway/compose.yaml \
  --service strava \
  --url http://mcp-strava:8080/mcp \
  --smoke-cmd "docker compose -f deploy/docker-compose.yml exec -T mcp-strava python -m mcp_strava.deploy.smoke --url http://mcp-gateway:8811/mcp --expect-tool get_fitness_state --forbid-tool sync --forbid-tool sql"
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
  --url http://mcp-strava:8080/mcp \
  --smoke-cmd "docker compose -f deploy/docker-compose.yml exec -T mcp-strava python -m mcp_strava.deploy.smoke --url http://mcp-gateway:8811/mcp --expect-tool get_fitness_state --forbid-tool sync --forbid-tool sql"
```

Without `--apply --confirm-live-gateway`, the helper must not mutate live files.

## Backup/Rollback Semantics

On apply mode, helper order is:

1. Prevalidate compose.
2. Backup both live files.
3. Write both files atomically.
4. Validate new compose.
5. Restart gateway.
6. Run smoke.

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
