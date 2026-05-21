"""Private sync helpers used only by refresh.runtime."""

from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime, timedelta

from mcp_strava.refresh.checkpoints import Stage
from mcp_strava.types import parse_strava_activity, parse_strava_streams


STREAM_KEYS = "time,heartrate,velocity_smooth,altitude,cadence,latlng,grade_smooth,grade_adjusted_speed,grade_adjusted_distance,moving"


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


def _stream_payload(data: dict) -> list[dict]:
    streams = parse_strava_streams(data)
    n = len(streams.time.data)
    rows = []
    for idx in range(n):
        rows.append(
            {
                "time_offset": streams.time.data[idx],
                "heartrate": streams.heartrate.data[idx] if streams.heartrate and idx < len(streams.heartrate.data) else None,
                "velocity": streams.velocity_smooth.data[idx] if streams.velocity_smooth and idx < len(streams.velocity_smooth.data) else None,
                "altitude": streams.altitude.data[idx] if streams.altitude and idx < len(streams.altitude.data) else None,
                "cadence": streams.cadence.data[idx] if streams.cadence and idx < len(streams.cadence.data) else None,
                "latlng": json.dumps(streams.latlng.data[idx]) if streams.latlng and idx < len(streams.latlng.data) else None,
                "grade": streams.grade_smooth.data[idx] if streams.grade_smooth and idx < len(streams.grade_smooth.data) else None,
                "gap_speed": streams.grade_adjusted_speed.data[idx] if streams.grade_adjusted_speed and idx < len(streams.grade_adjusted_speed.data) else None,
                "gap_distance": streams.grade_adjusted_distance.data[idx] if streams.grade_adjusted_distance and idx < len(streams.grade_adjusted_distance.data) else None,
                "is_moving": streams.moving.data[idx] if streams.moving and idx < len(streams.moving.data) else None,
            }
        )
    return rows


def _insert_streams(repo, act_id: int, data: dict) -> int:
    rows = _stream_payload(data)
    if not rows:
        return 0
    return repo.insert_stream_rows_chunked(act_id, rows, chunk_size=5000)


def _replace_streams(repo, act_id: int, data: dict) -> int:
    rows = _stream_payload(data)
    if not rows:
        return 0
    return repo.replace_stream_rows_chunked(act_id, rows, chunk_size=5000)


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
        response = transport.fetch(f"/activities/{activity.id}/streams?keys={STREAM_KEYS}&key_by_type=true")
        if isinstance(response.data, dict):
            _insert_streams(repo, activity.id, response.data)
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
