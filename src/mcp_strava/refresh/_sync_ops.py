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
from mcp_strava.adapters.duckdb.refresh_state_store import RefreshStateStore
from mcp_strava.adapters.duckdb.repository_models import ActivitySourcePayload
from mcp_strava.adapters.duckdb.source_hashing import raw_payload_hash, semantic_json_hash, summary_payload_changed
from mcp_strava.adapters.duckdb.stream_coverage_queries import activities_missing_stream_channels
from mcp_strava.constants import Config
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


def _channel_metadata_row(key: str, channel, fetched_at: str | None) -> dict:
    """Build a single channel-metadata dict; channel=None → unavailable."""
    if channel is None:
        return {
            "channel_key": key,
            "original_size": None,
            "resolution": None,
            "series_type": None,
            "fetched_at": fetched_at,
            "batch_id": None,
            "status": "unavailable",
            "error": None,
        }
    return {
        "channel_key": key,
        "original_size": channel.original_size,
        "resolution": channel.resolution,
        "series_type": channel.series_type,
        "fetched_at": fetched_at,
        "batch_id": None,
        "status": "available",
        "error": None,
    }


def _build_stream_metadata(channels: dict, fetched_at: str | None) -> list[dict]:
    """Build the full channel-metadata list: requested keys first, then extras."""
    requested = [_channel_metadata_row(key, channels.get(key), fetched_at) for key in STREAM_KEYS]
    extras = [
        _channel_metadata_row(key, channel, fetched_at) for key, channel in channels.items() if key not in STREAM_KEYS
    ]
    return requested + extras


def _build_stream_row(channels: dict, idx: int, time_offset: object) -> dict:
    """Assemble one stream data row at position idx."""
    row: dict[str, Any] = {
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
    extra_values: dict[str, Any] = {
        channel_key: channel.data[idx]
        for channel_key, channel in channels.items()
        if idx < len(channel.data) and channel_key != "latlng" and channel_key not in STREAM_CHANNEL_TO_COLUMN
    }
    row["values_json"] = json.dumps(extra_values, ensure_ascii=True) if extra_values else None
    return row


def _stream_payload(
    data: dict, fetched_at: str | None = None, activity_id: int | None = None
) -> tuple[list[dict], list[dict]]:
    channels = parse_strava_stream_channels(data)
    time_channel = channels.get("time")
    if time_channel is None:
        return [], []

    metadata = _build_stream_metadata(channels, fetched_at)

    seen_offsets: dict[object, int] = {}
    rows: list[dict] = []
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
        rows.append(_build_stream_row(channels, idx, time_offset))

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


def _write_activity_payload(
    repo,
    *,
    activity_id: int,
    activity_day: str | None,
    payload_kind: str,
    endpoint: str,
    fetched_at: str,
    payload_json: str,
) -> None:
    repo.write_activity_payload(
        ActivitySourcePayload(
            activity_id=activity_id,
            activity_day=activity_day,
            payload_kind=payload_kind,
            endpoint=endpoint,
            fetched_at=fetched_at,
            payload_json=payload_json,
            raw_hash=raw_payload_hash(payload_json),
            modeled_projection_hash=semantic_json_hash(payload_json),
            schema_status="clean",
        )
    )


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
            _write_activity_payload(
                repo,
                activity_id=act.id,
                activity_day=act.start_date_local[:10],
                payload_kind="summary",
                endpoint="/athlete/activities",
                fetched_at=now_iso,
                payload_json=summary_json,
            )
            # Skip the write when an existing activity is semantically unchanged:
            # the daily refresh re-sees every activity each cycle, and rewriting
            # an unchanged PRIMARY-KEY-indexed row churns the DuckDB ART index
            # (unbounded file bloat + re-triggers ART corruption). Freshness does
            # not depend on activities.synced_at, so leaving it untouched is safe.
            if existing is None:
                new += 1
            elif not summary_payload_changed(existing.summary_json, summary_json):
                continue
            else:
                _emit(
                    "summary_silver_update_deferred",
                    activity_id=act.id,
                    reason="bronze_pipeline_boundary",
                )
        if len(data) < Config.Api.STRAVA_PAGE_SIZE:
            break
        page += 1
    return seen, new


def sync_streams(
    repo,
    transport,
    since: str | None = None,
    on_activity: Callable[[int], None] | None = None,
) -> int:
    fetched = 0
    for activity in activities_missing_streams(repo, since):
        if on_activity is not None:
            on_activity(activity.id)
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
    on_activity: Callable[[int], None] | None = None,
) -> int:
    fetched = 0
    for activity in activities_missing_details(repo, since):
        if on_activity is not None:
            on_activity(activity.id)
        response = transport.fetch(f"/activities/{activity.id}")
        if isinstance(response.data, dict):
            journal_schema_drift(response.data, "detailed_activity")
            detail_json = json.dumps(response.data)
            _write_activity_payload(
                repo,
                activity_id=activity.id,
                activity_day=activity.activity_day,
                payload_kind="detail",
                endpoint=f"/activities/{activity.id}",
                fetched_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
                payload_json=detail_json,
            )
            fetched += 1
    return fetched


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
