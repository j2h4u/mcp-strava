"""Read-model stage helpers for refresh orchestration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from mcp_strava.adapters.duckdb.read_model_materializer import (
    MaterializationOptions,
)
from mcp_strava.adapters.duckdb.read_model_materializer import (
    materialize_read_model as materialize_duckdb_read_model,
)
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.repository_models import ActivitySummaryRecord
from mcp_strava.metric_registry import cached_logic_fingerprint
from mcp_strava.types import parse_strava_activity


def _emit(event: str, **fields: object) -> None:
    """Emit a structured JSON diagnostic event to stdout (house log style)."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def _latest_summary_record(repo, activity_id: int) -> ActivitySummaryRecord | None:
    payload = repo.latest_activity_payload(activity_id, "summary")
    if payload is None:
        return None
    payload_json = str(payload["payload_json"])
    raw = cast("object", json.loads(payload_json))
    if not isinstance(raw, dict):
        raise RuntimeError(f"Bronze summary payload for activity {activity_id} is not a JSON object")
    act = parse_strava_activity(cast("dict[str, object]", raw))
    return ActivitySummaryRecord(
        activity_id=act.id,
        date=act.start_date_local[:10],
        name=act.name,
        sport_type=act.sport_type,
        distance=act.distance,
        moving_time=act.moving_time,
        elapsed_time=act.elapsed_time,
        total_elevation_gain=act.total_elevation_gain,
        summary_json=payload_json,
        synced_at=str(payload["fetched_at"]),
    )


def process_bronze_payloads(repo) -> None:
    """Process committed bronze payloads into source-state invalidation."""
    if not isinstance(repo, DuckDBRepository):
        raise TypeError(f"DuckDBRepository required, got {type(repo).__name__}")
    changed = 0
    metric_version = repo.current_metric_version()
    activity_ids = repo.activity_ids_with_source_bronze_payloads()
    for activity_id in activity_ids:
        summary = _latest_summary_record(repo, activity_id)
        if summary is not None:
            repo.insert_activity_summary_if_missing(summary)
        if repo.update_activity_source_state_and_enqueue_dirty(
            activity_id,
            reason="bronze_payload_changed",
            metric_version=metric_version,
        ):
            changed += 1
    _emit(
        "bronze_payloads_processed",
        activities_considered=len(activity_ids),
        activities_changed=changed,
    )


def materialize_read_model_stage(
    repo,
    now_iso: str,
    renew_lease,
    limit: int | None = None,
) -> dict[str, Any]:
    """Materialize the read model, self-invalidating on a logic-fingerprint change."""
    if not isinstance(repo, DuckDBRepository):
        raise TypeError(f"DuckDBRepository required, got {type(repo).__name__}")

    stored = repo.current_logic_version()
    live = cached_logic_fingerprint()
    trigger_reason = "materialize_read_model"

    if stored is None:
        raise RuntimeError("read_model_logic_version sidecar is unseeded at materialize")
    if stored["logic_fingerprint"] != live:
        new_version = int(stored["metric_version"]) + 1
        repo.begin()
        try:
            repo.bump_logic_version(new_version, live, now_iso)
            enqueued = repo.enqueue_metric_version_recompute(
                new_version, reason="logic_fingerprint_changed", queued_at=now_iso
            )
        except Exception:
            repo.rollback()
            raise
        repo.commit()
        trigger_reason = "logic_fingerprint_changed"
        _emit(
            "read_model_logic_recompute",
            stored_fingerprint=stored["logic_fingerprint"],
            current_fingerprint=live,
            reason="logic_fingerprint_changed",
            activities_enqueued=enqueued,
            queued_at=now_iso,
        )

    current_version = repo.current_metric_version()
    materialize_limit = None if trigger_reason == "logic_fingerprint_changed" else limit
    started = datetime.now(UTC)
    result = materialize_duckdb_read_model(
        repo,
        current_version,
        MaterializationOptions(
            now=now_iso,
            renew_lease=renew_lease,
            limit=materialize_limit,
            trigger_reason=trigger_reason,
        ),
    )
    duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    _emit(
        "read_model_materialize_done",
        metric_version=current_version,
        trigger_reason=trigger_reason,
        duration_ms=duration_ms,
        status=result.get("status"),
    )
    return result
