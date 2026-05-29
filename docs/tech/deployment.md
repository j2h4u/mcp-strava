# mcp-strava Deployment Runbook

Operational decisions and incident-response procedures that cannot be expressed
as a `just` recipe. For runnable steps (build, smoke, perf gate, etc.), the
`Justfile` is the source of truth — run `just --list`.

## Gateway Registration: Live Apply Requires Operator Approval

`deploy/gateway_register.py` writes to `/opt/docker/mcp-gateway/catalog.yaml`
and `compose.yaml`, then restarts `mcp-gateway`. **A dry-run is the default;
the live apply must be explicitly approved by the operator.**

Live apply requires both flags together. Without them, the helper refuses to
mutate live files:

```bash
python3 deploy/gateway_register.py \
  --apply \
  --confirm-live-gateway \
  --catalog /opt/docker/mcp-gateway/catalog.yaml \
  --compose /opt/docker/mcp-gateway/compose.yaml \
  --service strava \
  --url http://mcp-strava:8080/mcp
```

## Apply-Mode Behaviour (Helper-Owned)

On apply, the helper:

1. Prevalidates the new compose.
2. Backs up both live files (timestamped).
3. Writes both files atomically.
4. Validates the new compose.
5. Restarts the gateway.

If any post-backup step fails, the helper restores both files from the latest
backups and restarts the gateway against the previous configuration.

A manual rollback follows the same shape: restore both files from the latest
backup, then restart `mcp-gateway` against the previous configuration.

## Rollback-Restart Contingency (Human Decision)

If the rollback restart itself fails:

1. **Stop automation.** Do not rerun any mutating command.
2. Verify which backup paths the helper restored from.
3. Inspect the live gateway state without mutating:

   ```bash
   docker compose --env-file /opt/docker/mcp-gateway/.env \
     -f /opt/docker/mcp-gateway/compose.yaml config
   docker compose --env-file /opt/docker/mcp-gateway/.env \
     -f /opt/docker/mcp-gateway/compose.yaml ps
   docker compose --env-file /opt/docker/mcp-gateway/.env \
     -f /opt/docker/mcp-gateway/compose.yaml logs --tail=200 mcp-gateway
   ```

4. Restore a previous timestamped backup, or escalate to manual recovery.
   No further writes until the operator decides.

## Periodic Maintenance: DuckDB Compaction

DuckDB never shrinks its storage file in place. Deletes and row replacements
(read-model re-materialization, migrations, backfills that supersede rows) leave
dead space the file keeps at its high-water mark; `CHECKPOINT` only merges
heavily-deleted row groups. So the mirror file drifts larger than the live data
warrants and never recovers on its own.

**Run compaction occasionally** — there is no schedule and no automation. Do it
when the file is noticeably larger than the data justifies (check
`ls -lh /opt/docker/mcp-strava/data/strava.duckdb`), or after a large one-off
rewrite. For reference, the one-time Phase-8 SQLite→DuckDB migration left the
file at ~764 MB; a single compaction brought it to ~84 MB.

```bash
just admin compact            # keeps a timestamped pre-compact backup
just admin compact --no-backup  # skip the backup (disk-constrained)
```

`admin compact` rewrites the whole database into a fresh file via
`COPY FROM DATABASE`, then swaps it in atomically (`os.replace`) and reports how
much was reclaimed. The `just admin` wrapper stops the owner first (DuckDB holds
an exclusive writer lock) and restarts it afterwards, even on failure.

Unless `--no-backup` is given, a `strava.pre-compact-<timestamp>.duckdb` copy is
left in the data directory. **Verify the service is healthy and serving (e.g.
`just mcp-smoke-full`) before deleting the backup.**

## Invariant: Never Leak Secrets

`/opt/docker/mcp-strava/.env` and related token files must never be printed in
logs, tests, summaries, commit messages, or chat output.
