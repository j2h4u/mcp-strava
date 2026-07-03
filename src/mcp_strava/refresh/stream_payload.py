"""Stream payload shaping helpers used by refresh sync operations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from mcp_strava.types import StravaStreamChannel, parse_strava_stream_channels

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


def _emit(event: str, **fields: object) -> None:
    """Emit a structured JSON diagnostic event to stdout (house log style)."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def _channel_value(channels: Mapping[str, StravaStreamChannel], channel_key: str, idx: int) -> object:
    channel = channels.get(channel_key)
    if channel is None or idx >= len(channel.data):
        return None
    return channel.data[idx]


def _channel_metadata_row(key: str, channel: StravaStreamChannel | None, fetched_at: str | None) -> dict[str, object]:
    """Build a single channel-metadata dict; channel=None -> unavailable."""
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


def _build_stream_metadata(
    channels: Mapping[str, StravaStreamChannel], fetched_at: str | None
) -> list[dict[str, object]]:
    """Build the full channel-metadata list: requested keys first, then extras."""
    requested = [_channel_metadata_row(key, channels.get(key), fetched_at) for key in STREAM_KEYS]
    extras = [
        _channel_metadata_row(key, channel, fetched_at) for key, channel in channels.items() if key not in STREAM_KEYS
    ]
    return requested + extras


def _build_stream_row(channels: Mapping[str, StravaStreamChannel], idx: int, time_offset: object) -> dict:
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
