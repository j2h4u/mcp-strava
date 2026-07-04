"""Private sync helpers used only by refresh.runtime."""

from __future__ import annotations

import json
from calendar import monthrange
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from mcp_strava.adapters.duckdb.activity_selectors import activities_missing_streams
from mcp_strava.adapters.duckdb.stream_coverage_queries import activities_missing_stream_channels
from mcp_strava.refresh.schema_drift import journal_schema_drift
from mcp_strava.refresh.stream_payload import STREAM_KEYS, STREAM_KEYS_QUERY, _stream_payload

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


def _write_streams(repo, act_id: int, data: dict, fetched_at: str | None = None) -> int:
    rows, metadata = _stream_payload(data, fetched_at=fetched_at, activity_id=act_id)
    if not rows:
        return 0
    return repo.replace_stream_rows_and_channel_metadata(act_id, rows=rows, metadata=metadata, chunk_size=5000)


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
            _write_streams(
                repo, activity.id, response.data, fetched_at=datetime.now(UTC).replace(tzinfo=None).isoformat()
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
    on_activity: Callable[[int], None] | None = None,
    on_progress: Callable[[], None] | None = None,
) -> dict:
    estimate = estimate_stream_channel_backfill(repo, since=since, limit=limit)
    completed = 0
    for item in estimate["candidates"]:
        activity_id = int(item["activity_id"])
        if on_activity is not None:
            on_activity(activity_id)
        if on_progress is not None:
            on_progress()
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
