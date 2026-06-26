"""Offline materialization for DuckDB read-model facts."""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from mcp_strava.adapters.duckdb.read_model_activity_facts import _activity_facts_batched
from mcp_strava.adapters.duckdb.read_model_materializer_utils import (
    _HR_REST_MISSING_MSG,
)
from mcp_strava.adapters.duckdb.read_model_period_facts import (
    ROLLING_WINDOWS,
    _materialize_daily_facts,
    _materialize_model_facts,
    _materialize_rolling_facts,
)
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.stream_metric_queries import max_heartrate_to_date
from mcp_strava.hr_zones import get_zone_model
from mcp_strava.settings import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterializationOptions:
    now: str | datetime | None = None
    limit: int | None = None
    run_id: int | None = None  # accepted for API surface; unused internally
    renew_lease: object = field(default=None)
    settings: Settings | None = None
    trigger_reason: str = "materialize_read_model"


def _now_parts(now: str | datetime | None) -> tuple[str, str]:
    if now is None:
        # Instant + calendar source: UTC-naive, matching the WR-02 freshness basis.
        dt = datetime.now(UTC).replace(tzinfo=None)
    elif isinstance(now, str):
        dt = datetime.fromisoformat(now)
    else:
        dt = now
    return dt.isoformat(timespec="seconds"), dt.date().isoformat()


def _record_failed_run(repo: DuckDBRepository, started_at: str, metric_version: int, error: Exception) -> None:
    try:
        repo.record_read_model_refresh_run(
            {
                "started_at": started_at,
                "finished_at": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
                "status": "failed",
                "metric_version": metric_version,
                "trigger_reason": "materialize_read_model",
                "activities_considered": 0,
                "activities_materialized": 0,
                "dirty_rows_claimed": 0,
                "dirty_rows_cleared": 0,
                "attempt_count": 1,
                "last_error": str(error),
            }
        )
        # WR-03: commit through the lock-aware repository helper, not a raw
        # repo.conn.commit(). record_read_model_refresh_run already writes via
        # _execute (which takes duckdb_process_lock()); _commit_if_standalone
        # finalizes that write under the same single-writer lock the rest of the
        # repository honors, so the failed-run bookkeeping cannot interleave with
        # another writer's transaction.
        repo._commit_if_standalone()
    except Exception as exc:  # noqa: BLE001 - best-effort failure bookkeeping must not mask materialization failure.
        logger.warning("read-model failed-run recording failed: %s", exc)
        repo.rollback()


def materialize_read_model(
    repo: DuckDBRepository,
    metric_version: int,
    opts: MaterializationOptions | None = None,
) -> dict[str, Any]:
    _opts = opts or MaterializationOptions()
    _settings = _opts.settings or get_settings()
    athlete = _settings.athlete
    if athlete.hr_rest is None:
        raise RuntimeError(_HR_REST_MISSING_MSG)
    computed_at, today = _now_parts(_opts.now)
    dirty_rows = repo.dirty_activity_rows_for_materialization(metric_version, limit=_opts.limit)
    if not dirty_rows:
        return {"status": "noop", "activities_materialized": 0, "dirty_rows_cleared": 0}

    started = time.perf_counter()
    start_day = min(str(row["activity_day"]) for row in dirty_rows)
    end_day = max(today, max(str(row["activity_day"]) for row in dirty_rows))

    # Compute a session-level bounds for daily-fact aggregation (global max at end_day).
    # Per-activity facts use per-activity running max; this bounds is only used to
    # aggregate already-computed TRIMP via observed_trimp_history (cross-activity daily sum).
    global_hr_max = max_heartrate_to_date(repo, end_day)
    if global_hr_max is None:
        # No HR data at all — use a sentinel bounds that returns 0 TRIMP for all rows.
        session_bounds = get_zone_model(athlete.hr_zone_model).zone_bounds(
            hr_max=athlete.hr_rest + 1, hr_rest=athlete.hr_rest
        )
    else:
        session_bounds = get_zone_model(athlete.hr_zone_model).zone_bounds(
            hr_max=int(global_hr_max), hr_rest=athlete.hr_rest
        )

    try:
        activity_facts: list[dict[str, object]] = _activity_facts_batched(
            repo, dirty_rows, metric_version, computed_at, _settings, renew_lease=_opts.renew_lease
        )
    except Exception as exc:
        _record_failed_run(repo, computed_at, metric_version, exc)
        raise

    repo.begin()
    try:
        activity_count = len(activity_facts)
        repo.upsert_activity_metric_facts(activity_facts)

        daily_trimp = _materialize_daily_facts(
            repo,
            start_day=start_day,
            end_day=end_day,
            metric_version=metric_version,
            computed_at=computed_at,
            bounds=session_bounds,
        )
        _materialize_model_facts(
            repo,
            start_day=start_day,
            end_day=end_day,
            metric_version=metric_version,
            computed_at=computed_at,
            daily_trimp=daily_trimp,
        )
        _materialize_rolling_facts(
            repo,
            as_of_day=end_day,
            metric_version=metric_version,
            computed_at=computed_at,
        )
        repo.record_read_model_refresh_run(
            {
                "started_at": computed_at,
                "finished_at": computed_at,
                "status": "ok",
                "metric_version": metric_version,
                "trigger_reason": _opts.trigger_reason,
                "activities_considered": len(dirty_rows),
                "activities_materialized": activity_count,
                "daily_facts_materialized": len(daily_trimp),
                "model_facts_materialized": len(daily_trimp),
                "rolling_facts_materialized": len(ROLLING_WINDOWS),
                "dirty_rows_claimed": len(dirty_rows),
                "dirty_rows_cleared": len(dirty_rows),
                "attempt_count": 1,
                "last_error": None,
            }
        )
        cleared = repo.clear_dirty_activity_rows(dirty_rows)
        remaining_dirty = len(repo.dirty_activity_rows(metric_version=metric_version))
        pruned_counts = repo.prune_old_read_model_metric_versions(metric_version) if remaining_dirty == 0 else {}
    except Exception as exc:
        repo.rollback()
        _record_failed_run(repo, computed_at, metric_version, exc)
        raise

    repo.commit()
    # Operational counter for a domain that has regressed before: surfaces materialize
    # cost so the next slowdown is visible without a profiler.
    logger.info(
        "read-model materialize: activities=%d daily=%d rolling=%d cleared=%d remaining_dirty=%d pruned=%d elapsed_ms=%d",
        activity_count,
        len(daily_trimp),
        len(ROLLING_WINDOWS),
        cleared,
        remaining_dirty,
        sum(pruned_counts.values()),
        int((time.perf_counter() - started) * 1000),
    )
    return {
        "status": "ok",
        "activities_materialized": activity_count,
        "dirty_rows_cleared": cleared,
        "dirty_rows_remaining": remaining_dirty,
        "old_metric_version_rows_pruned": pruned_counts,
        "daily_facts_materialized": len(daily_trimp),
        "rolling_facts_materialized": len(ROLLING_WINDOWS),
    }
