"""Private sync helpers used only by refresh.runtime."""

from __future__ import annotations

import importlib
import json
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable

from mcp_strava.adapters.duckdb.read_model_materializer import (
    materialize_read_model as materialize_duckdb_read_model,
)
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.refresh.checkpoints import Stage
from mcp_strava.types import parse_strava_activity, parse_strava_stream_channels


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


def _sqlite_materialize_read_model():
    sqlite_materializer = importlib.import_module("mcp_strava.adapters.sqlite.read_model_materializer")
    return sqlite_materializer.materialize_read_model


def _is_iso_day(value: str) -> bool:
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        return False
    year_text = value[:4]
    month_text = value[5:7]
    day_text = value[8:10]
    if not (year_text.isdigit() and month_text.isdigit() and day_text.isdigit()):
        return False
    year = int(year_text)
    month = int(month_text)
    day = int(day_text)
    if month < 1 or month > 12:
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


def _channel_value(channels: dict[str, Any], channel_key: str, idx: int) -> Any:
    channel = channels.get(channel_key)
    if channel is None or idx >= len(channel.data):
        return None
    return channel.data[idx]


def _stream_payload(data: dict, fetched_at: str | None = None) -> tuple[list[dict], list[dict]]:
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

    for idx, time_offset in enumerate(time_channel.data):
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
        if isinstance(latlng, list) and len(latlng) >= 2:
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
    rows, metadata = _stream_payload(data, fetched_at=fetched_at)
    if not rows:
        return 0
    return repo.replace_stream_rows_and_channel_metadata(act_id, rows=rows, metadata=metadata, chunk_size=5000)


def _replace_streams(repo, act_id: int, data: dict, fetched_at: str | None = None) -> int:
    rows, metadata = _stream_payload(data, fetched_at=fetched_at)
    if not rows:
        return 0
    return repo.replace_stream_rows_and_channel_metadata(act_id, rows=rows, metadata=metadata, chunk_size=5000)


def sync_summaries(repo, transport, now_iso: str) -> tuple[int, int]:
    page = 1
    seen = 0
    new = 0
    while True:
        response = transport.fetch(f"/athlete/activities?per_page=100&page={page}")
        data = response.data
        if not data:
            break
        if not isinstance(data, list):
            break
        seen += len(data)
        for raw in data:
            act = parse_strava_activity(raw)
            existing = repo.activity_by_id(act.id)
            repo.upsert_activity_summary(
                activity_id=act.id,
                date=act.start_date_local[:10],
                name=act.name,
                sport_type=act.sport_type,
                distance=act.distance,
                moving_time=act.moving_time,
                elapsed_time=act.elapsed_time,
                total_elevation_gain=act.total_elevation_gain,
                summary_json=json.dumps(raw),
                synced_at=now_iso,
            )
            if not existing:
                new += 1
        if len(data) < 100:
            break
        page += 1
    return seen, new


def sync_streams(
    repo,
    transport,
    since: str | None = None,
    checkpoint_stage: Stage = Stage.STREAMS,
) -> int:
    fetched = 0
    for activity in repo.activities_missing_streams(since):
        repo.set_checkpoint(checkpoint_stage.value, str(activity.id))
        response = transport.fetch(f"/activities/{activity.id}/streams?keys={STREAM_KEYS_QUERY}&key_by_type=true")
        if isinstance(response.data, dict):
            _insert_streams(repo, activity.id, response.data, fetched_at=datetime.now(UTC).replace(tzinfo=None).isoformat())
            fetched += 1
    return fetched


def sync_details(
    repo,
    transport,
    since: str | None = None,
    checkpoint_stage: Stage = Stage.DETAILS,
) -> int:
    fetched = 0
    for activity in repo.activities_missing_details(since):
        repo.set_checkpoint(checkpoint_stage.value, str(activity.id))
        response = transport.fetch(f"/activities/{activity.id}")
        if isinstance(response.data, dict):
            repo.update_activity_detail(activity.id, json.dumps(response.data))
            fetched += 1
    return fetched


def schema_validate(repo) -> None:
    return None


def materialize_read_model_stage(
    repo,
    metric_version: int,
    now_iso: str,
    renew_lease: Callable[[], None] | None,
) -> dict[str, object]:
    materializer = materialize_duckdb_read_model
    if not isinstance(repo, DuckDBRepository):
        materializer = _sqlite_materialize_read_model()
    return materializer(
        repo,
        metric_version=metric_version,
        now=now_iso,
        renew_lease=renew_lease,
    )


def estimate_stream_channel_backfill(
    repo,
    *,
    since: str | None = None,
    limit: int | None = None,
) -> dict:
    candidates = repo.activities_missing_stream_channels(
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
    estimate = estimate_stream_channel_backfill(repo, since=since, limit=limit)
    completed = 0
    for item in estimate["candidates"]:
        activity_id = int(item["activity_id"])
        if on_progress is not None:
            on_progress()
        repo.set_checkpoint(checkpoint_stage.value, str(activity_id))
        response = transport.fetch(f"/activities/{activity_id}/streams?keys={STREAM_KEYS_QUERY}&key_by_type=true")
        if not isinstance(response.data, dict):
            continue
        rows, metadata = _stream_payload(response.data, fetched_at=datetime.now(UTC).replace(tzinfo=None).isoformat())
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
    query = """
        SELECT a.id, a.name FROM activities a
        WHERE CAST(json_extract(a.summary_json, '$.kudos_count') AS INTEGER) > 0
          AND NOT EXISTS (SELECT 1 FROM kudos k WHERE k.activity_id = a.id)
    """
    params: list[object] = []
    if window_days is not None:
        query += " AND a.date >= date('now', ?)"
        params.append(f"-{window_days} days")
    query += " ORDER BY a.date DESC"

    rows = repo.conn.execute(query, params).fetchall()
    fetched = 0
    for row in rows:
        response = transport.fetch(f"/activities/{row['id']}/kudos?per_page=100")
        if not isinstance(response.data, list):
            continue
        for athlete in response.data:
            repo.upsert_kudos(
                row["id"],
                athlete.get("firstname", ""),
                athlete.get("lastname", ""),
                now_iso,
            )
        fetched += 1
    return fetched
