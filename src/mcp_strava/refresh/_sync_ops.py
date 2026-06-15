"""Private sync helpers used only by refresh.runtime."""

from __future__ import annotations

import json
from calendar import monthrange
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from mcp_strava.adapters.duckdb.activity_lookup_queries import activity_by_id
from mcp_strava.adapters.duckdb.activity_selectors import (
    activities_missing_details,
    activities_missing_streams,
)
from mcp_strava.adapters.duckdb.kudos_store import activities_missing_kudos, upsert_kudos
from mcp_strava.adapters.duckdb.read_model_materializer import (
    materialize_read_model as materialize_duckdb_read_model,
)
from mcp_strava.adapters.duckdb.refresh_state_store import RefreshStateStore
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.source_hashing import summary_payload_changed
from mcp_strava.adapters.duckdb.stream_coverage_queries import activities_missing_stream_channels
from mcp_strava.constants import Config
from mcp_strava.metric_registry import cached_logic_fingerprint
from mcp_strava.refresh.checkpoints import Stage
from mcp_strava.refresh.schema_drift import journal_schema_drift
from mcp_strava.types import StravaStreamChannel, parse_strava_activity, parse_strava_stream_channels


def _emit(event: str, **fields: object) -> None:
    """Emit a structured JSON diagnostic event to stdout (house log style)."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


STREAM_KEYS = (
    "time",
    "distance",
    "heartrate",
    "velocity_smooth",
    "altitude",
    "cadence",
    "latlng",
    "grade_smooth",
    "grade_adjusted_speed",
    "grade_adjusted_distance",
    "moving",
    "watts",
    "temp",
)
STREAM_KEYS_QUERY = ",".join(STREAM_KEYS)
STREAM_CHANNEL_TO_COLUMN = {
    "time": "time_offset",
    "heartrate": "heartrate",
    "velocity_smooth": "velocity",
    "altitude": "altitude",
    "cadence": "cadence",
    "grade_smooth": "grade",
    "grade_adjusted_speed": "gap_speed",
    "grade_adjusted_distance": "gap_distance",
    "moving": "is_moving",
}

_ISO_DATE_LENGTH = 10  # "YYYY-MM-DD" length


def _is_iso_day(value: str) -> bool:
    if len(value) != _ISO_DATE_LENGTH or value[4] != "-" or value[7] != "-":
        return False
    year_text = value[:4]
    month_text = value[5:7]
    day_text = value[8:10]
    if not (year_text.isdigit() and month_text.isdigit() and day_text.isdigit()):
        return False
    year = int(year_text)
    month = int(month_text)
    day = int(day_text)
    if month < 1 or month > 12:  # noqa: PLR2004
        return False
    max_day = monthrange(year, month)[1]
    return 1 <= day <= max_day


def _safe_quick_sync_start_day(latest_raw: object | None) -> str:
    candidate = str(latest_raw or "2000-01-01")[:10]
    latest_day = candidate if _is_iso_day(candidate) else "2000-01-01"
    year = int(latest_day[:4])
    month = int(latest_day[5:7])
    day = int(latest_day[8:10])
    return (date(year, month, day) - timedelta(days=7)).isoformat()


def _channel_value(channels: dict[str, StravaStreamChannel], channel_key: str, idx: int) -> object:
    channel = channels.get(channel_key)
    if channel is None or idx >= len(channel.data):
        return None
    return channel.data[idx]


def _stream_payload(
    data: dict, fetched_at: str | None = None, activity_id: int | None = None
) -> tuple[list[dict], list[dict]]:
    channels = parse_strava_stream_channels(data)
    time_channel = channels.get("time")
    if time_channel is None:
        return [], []

    requested_keys = list(STREAM_KEYS)
    rows: list[dict] = []
    metadata: list[dict] = []

    for key in requested_keys:
        channel = channels.get(key)
        if channel is None:
            metadata.append(
                {
                    "channel_key": key,
                    "original_size": None,
                    "resolution": None,
                    "series_type": None,
                    "fetched_at": fetched_at,
                    "batch_id": None,
                    "status": "unavailable",
                    "error": None,
                }
            )
            continue
        metadata.append(
            {
                "channel_key": key,
                "original_size": channel.original_size,
                "resolution": channel.resolution,
                "series_type": channel.series_type,
                "fetched_at": fetched_at,
                "batch_id": None,
                "status": "available",
                "error": None,
            }
        )

    for key, channel in channels.items():
        if key in STREAM_KEYS:
            continue
        metadata.append(
            {
                "channel_key": key,
                "original_size": channel.original_size,
                "resolution": channel.resolution,
                "series_type": channel.series_type,
                "fetched_at": fetched_at,
                "batch_id": None,
                "status": "available",
                "error": None,
            }
        )

    seen_offsets: dict[object, int] = {}
    for idx, time_offset in enumerate(time_channel.data):
        if time_offset in seen_offsets:
            _emit(
                "strava_stream_duplicate_time_offset",
                activity_id=activity_id,
                time_offset=time_offset,
                kept_index=seen_offsets[time_offset],
                dropped_index=idx,
            )
            continue
        seen_offsets[time_offset] = idx
        extra_values: dict[str, Any] = {}
        row = {
            "time_offset": time_offset,
            "heartrate": _channel_value(channels, "heartrate", idx),
            "velocity": _channel_value(channels, "velocity_smooth", idx),
            "altitude": _channel_value(channels, "altitude", idx),
            "cadence": _channel_value(channels, "cadence", idx),
            "grade": _channel_value(channels, "grade_smooth", idx),
            "gap_speed": _channel_value(channels, "grade_adjusted_speed", idx),
            "gap_distance": _channel_value(channels, "grade_adjusted_distance", idx),
            "is_moving": _channel_value(channels, "moving", idx),
        }
        latlng = _channel_value(channels, "latlng", idx)
        if isinstance(latlng, list) and len(latlng) >= 2:  # noqa: PLR2004
            row["lat"] = latlng[0]
            row["lng"] = latlng[1]
        else:
            row["lat"] = None
            row["lng"] = None

        for channel_key, channel in channels.items():
            if idx >= len(channel.data):
                continue
            if channel_key == "latlng":
                continue
            if channel_key in STREAM_CHANNEL_TO_COLUMN:
                continue
            extra_values[channel_key] = channel.data[idx]
        row["values_json"] = json.dumps(extra_values, ensure_ascii=True) if extra_values else None
        rows.append(row)

    return rows, metadata


def _insert_streams(repo, act_id: int, data: dict, fetched_at: str | None = None) -> int:
    rows, metadata = _stream_payload(data, fetched_at=fetched_at, activity_id=act_id)
    if not rows:
        return 0
    return repo.replace_stream_rows_and_channel_metadata(act_id, rows=rows, metadata=metadata, chunk_size=5000)


def _replace_streams(repo, act_id: int, data: dict, fetched_at: str | None = None) -> int:
    rows, metadata = _stream_payload(data, fetched_at=fetched_at, activity_id=act_id)
    if not rows:
        return 0
    return repo.replace_stream_rows_and_channel_metadata(act_id, rows=rows, metadata=metadata, chunk_size=5000)


def sync_summaries(repo, transport, now_iso: str, *, after_epoch: int | None = None) -> tuple[int, int]:
    page = 1
    seen = 0
    new = 0
    while True:
        response = transport.fetch(
            f"/athlete/activities?per_page=100&page={page}"
            + (f"&after={after_epoch}" if after_epoch is not None else "")
        )
        data = response.data
        if not data:
            break
        if not isinstance(data, list):
            break
        seen += len(data)
        journal_schema_drift(data, "summary_activity", is_batch=True)
        for raw in data:
            act = parse_strava_activity(raw)
            existing = activity_by_id(repo, act.id)
            summary_json = json.dumps(raw)
            # Skip the write when an existing activity is semantically unchanged:
            # the daily refresh re-sees every activity each cycle, and rewriting
            # an unchanged PRIMARY-KEY-indexed row churns the DuckDB ART index
            # (unbounded file bloat + re-triggers ART corruption). Freshness does
            # not depend on activities.synced_at, so leaving it untouched is safe.
            if existing is None:
                new += 1
            elif not summary_payload_changed(existing.summary_json, summary_json):
                continue
            repo.upsert_activity_summary(
                activity_id=act.id,
                date=act.start_date_local[:10],
                name=act.name,
                sport_type=act.sport_type,
                distance=act.distance,
                moving_time=act.moving_time,
                elapsed_time=act.elapsed_time,
                total_elevation_gain=act.total_elevation_gain,
                summary_json=summary_json,
                synced_at=now_iso,
            )
        if len(data) < Config.Api.STRAVA_PAGE_SIZE:
            break
        page += 1
    return seen, new


def sync_streams(
    repo,
    transport,
    since: str | None = None,
    checkpoint_stage: Stage = Stage.STREAMS,
) -> int:
    refresh_store = RefreshStateStore.from_connection(repo.conn)
    fetched = 0
    for activity in activities_missing_streams(repo, since):
        refresh_store.set_checkpoint(checkpoint_stage.value, str(activity.id))
        response = transport.fetch(f"/activities/{activity.id}/streams?keys={STREAM_KEYS_QUERY}&key_by_type=true")
        if isinstance(response.data, dict):
            journal_schema_drift(response.data, "streams")
            _insert_streams(
                repo, activity.id, response.data, fetched_at=datetime.now(UTC).replace(tzinfo=None).isoformat()
            )
            fetched += 1
    return fetched


def sync_details(
    repo,
    transport,
    since: str | None = None,
    checkpoint_stage: Stage = Stage.DETAILS,
) -> int:
    refresh_store = RefreshStateStore.from_connection(repo.conn)
    fetched = 0
    for activity in activities_missing_details(repo, since):
        refresh_store.set_checkpoint(checkpoint_stage.value, str(activity.id))
        response = transport.fetch(f"/activities/{activity.id}")
        if isinstance(response.data, dict):
            journal_schema_drift(response.data, "detailed_activity")
            repo.update_activity_detail(activity.id, json.dumps(response.data))
            fetched += 1
    return fetched


def schema_validate(repo) -> None:
    return None


def materialize_read_model_stage(
    repo,
    now_iso: str,
    renew_lease: Callable[[], None] | None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Materialize the read model, self-invalidating on a logic-fingerprint change.

    This is the single chokepoint that turns "edit a metric constant/formula"
    into "the affected facts recompute". Before materializing, it compares the
    fingerprint stored in the sidecar (read_model_logic_version) against the LIVE
    fingerprint of the current compute-path source:

    - stored != live  -> a compute module changed since the sidecar was last
      written. Bump metric_version to N+1, record the new fingerprint, and enqueue
      EVERY activity for recompute (wiring the orphan enqueue_metric_version_recompute).
    - stored is None  -> invariant violation: the constructor seed populates the
      sidecar whenever the schema exists. Fail loud — never silently adopt.
    - stored == live  -> no-op; just materialize at the current version.

    The version materialized at is re-resolved INTERNALLY from
    repo.current_metric_version() AFTER the bump/adopt (the bump invalidated the
    sidecar memo), NOT from a caller-passed value. On a recompute cycle this
    guarantees the materialize version (N+1) equals the just-enqueued version
    (N+1) — a stale caller value can never leave dirty rows queued at N+1 while
    materialization runs at N (cycle-2 stale-version guard).
    """
    if not isinstance(repo, DuckDBRepository):
        raise TypeError(f"DuckDBRepository required, got {type(repo).__name__}")

    stored = repo.current_logic_version()
    live = cached_logic_fingerprint()
    trigger_reason = "materialize_read_model"

    if stored is None:
        # Invariant: the constructor seed populates the sidecar whenever the
        # schema exists (and fails loud otherwise), so it is never None here.
        # Reaching this is a real bug, not a recoverable state — fail loud.
        raise RuntimeError("read_model_logic_version sidecar is unseeded at materialize")
    if stored["logic_fingerprint"] != live:
        # A compute module's source changed -> bump + mass-enqueue recompute.
        # WR-01: the version advance and the mass-enqueue MUST land atomically.
        # bump_logic_version + enqueue_metric_version_recompute each
        # _commit_if_standalone, which no-ops inside a transaction, so wrapping
        # them in one repo.begin()/commit() makes the pair all-or-nothing. Without
        # this, a crash AFTER the bump commit but BEFORE the enqueue commit would
        # durably advance the stored fingerprint to live while leaving the dirty
        # queue empty — the next cycle then sees stored == live and silently never
        # recomputes (the under-invalidation this phase exists to prevent).
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

    # Re-resolve POST-bump: bump_logic_version() invalidated the memo, so this
    # returns N+1 on a recompute cycle and the stored version otherwise.
    current_version = repo.current_metric_version()
    # Drain-on-recompute: a logic-fingerprint change enqueues EVERY activity, and a
    # logic edit must recompute promptly. Drain the whole backlog in THIS call instead
    # of bleeding it out at the caller's per-cycle `limit` (the steady-state batch of
    # READ_MODEL_BATCH_SIZE would otherwise need ~N/batch refresh cycles to materialize
    # N activities — e.g. 625 activities at 25/hour ≈ 25 hours). Steady-state
    # incremental materialization (no fingerprint change) stays bounded by `limit` so a
    # normal refresh cycle never runs unbounded.
    materialize_limit = None if trigger_reason == "logic_fingerprint_changed" else limit
    started = datetime.now(UTC)
    result = materialize_duckdb_read_model(
        repo,
        metric_version=current_version,
        now=now_iso,
        renew_lease=renew_lease,
        limit=materialize_limit,
        trigger_reason=trigger_reason,
    )
    duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    # Self-explanatory materialize-ok signal: the version materialized at and how
    # long the compute took, so an operator can correlate a recompute event with
    # the version it landed and its cost.
    _emit(
        "read_model_materialize_done",
        metric_version=current_version,
        trigger_reason=trigger_reason,
        duration_ms=duration_ms,
        status=result.get("status"),
    )
    return result


def estimate_stream_channel_backfill(
    repo,
    *,
    since: str | None = None,
    limit: int | None = None,
) -> dict:
    candidates = activities_missing_stream_channels(
        repo,
        since=since,
        limit=limit,
        requested_channels=STREAM_KEYS,
    )
    missing_channels: dict[str, int] = {}
    metadata_missing = 0
    for item in candidates:
        if item.get("metadata_missing"):
            metadata_missing += 1
        for channel in item.get("missing_channels", []):
            missing_channels[channel] = missing_channels.get(channel, 0) + 1
    return {
        "activities_considered": len(candidates),
        "activities_to_backfill": len(candidates),
        "missing_channels": missing_channels,
        "metadata_missing": metadata_missing,
        "estimated_api_calls": len(candidates),
        "candidates": candidates,
    }


def sync_stream_channels_backfill(
    repo,
    transport,
    *,
    since: str | None = None,
    limit: int | None = None,
    checkpoint_stage: Stage = Stage.STREAM_CHANNELS_BACKFILL,
    on_progress: Callable[[], None] | None = None,
) -> dict:
    refresh_store = RefreshStateStore.from_connection(repo.conn)
    estimate = estimate_stream_channel_backfill(repo, since=since, limit=limit)
    completed = 0
    for item in estimate["candidates"]:
        activity_id = int(item["activity_id"])
        if on_progress is not None:
            on_progress()
        refresh_store.set_checkpoint(checkpoint_stage.value, str(activity_id))
        response = transport.fetch(f"/activities/{activity_id}/streams?keys={STREAM_KEYS_QUERY}&key_by_type=true")
        if not isinstance(response.data, dict):
            continue
        rows, metadata = _stream_payload(
            response.data,
            fetched_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
            activity_id=activity_id,
        )
        if not rows:
            continue
        missing = set(item.get("missing_channels", []))
        merge_rows: list[dict[str, Any]] = []
        for row in rows:
            values_json = row.get("values_json")
            row_values = json.loads(values_json) if values_json else {}
            filtered = {k: v for k, v in row_values.items() if k in missing}
            if filtered:
                merge_rows.append({"time_offset": row["time_offset"], "values": filtered})
        filtered_metadata = [m for m in metadata if m.get("channel_key") in missing]
        repo.merge_stream_channel_values(
            activity_id=activity_id,
            rows=merge_rows,
            metadata=filtered_metadata,
            missing_channel_keys=[k for k in missing if not any(m.get("channel_key") == k for m in filtered_metadata)],
        )
        completed += 1
        if on_progress is not None:
            on_progress()
    estimate["completed"] = completed
    return estimate


def _sync_kudos(repo, transport, now_iso: str, window_days: int | None = None) -> int:
    # Read through the typed repository boundary (returns list[int]) rather than
    # touching repo.conn — keeps raw DB-API tuples inside the data layer.
    fetched = 0
    for activity_id in activities_missing_kudos(repo, window_days):
        response = transport.fetch(f"/activities/{activity_id}/kudos?per_page=100")
        if not isinstance(response.data, list):
            continue
        for athlete in response.data:
            upsert_kudos(
                repo,
                activity_id,
                athlete.get("firstname", ""),
                athlete.get("lastname", ""),
                now_iso,
            )
        fetched += 1
    return fetched
