"""Source ingest helpers for refresh.runtime."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

from mcp_strava.adapters.duckdb.activity_lookup_queries import activity_by_id
from mcp_strava.adapters.duckdb.activity_selectors import activities_missing_details
from mcp_strava.adapters.duckdb.repository_models import ActivitySourcePayload, AthleteProfilePayload
from mcp_strava.adapters.duckdb.source_hashing import raw_payload_hash, semantic_json_hash, summary_payload_changed
from mcp_strava.adapters.strava import StravaUnavailableError
from mcp_strava.constants import Config
from mcp_strava.refresh.schema_drift import journal_schema_drift
from mcp_strava.types import parse_strava_activity


def _emit(event: str, **fields: object) -> None:
    """Emit a structured JSON diagnostic event to stdout (house log style)."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


_OPTIONAL_ATHLETE_PROFILE_FAILURE_REASONS = frozenset(
    {
        "endpoint_unavailable",
        "forbidden",
        "strava_application_inactive",
    }
)


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


def _write_athlete_profile_payload(
    repo,
    *,
    profile_key: str,
    payload_kind: str,
    endpoint: str,
    fetched_at: str,
    payload_json: str,
) -> None:
    repo.write_athlete_profile_payload(
        AthleteProfilePayload(
            profile_key=profile_key,
            payload_kind=payload_kind,
            endpoint=endpoint,
            fetched_at=fetched_at,
            payload_json=payload_json,
            raw_hash=raw_payload_hash(payload_json),
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


def sync_athlete_zones(repo, transport, now_iso: str) -> int:
    """Capture ``/athlete/zones`` as bronze-only raw source data.

    This endpoint is deliberately retained only for future comparison/debugging.
    Current HR-zone/TRIMP metrics still derive from activity streams and local
    athlete settings, not from this profile payload.

    A direct 403/404 or a typed unavailable/inactive transport failure is
    treated as an optional endpoint miss: we log and skip without failing the
    refresh. Rate-limit, token, and network failures still fail closed.
    """
    endpoint = "/athlete/zones"
    try:
        response = transport.fetch(endpoint)
    except StravaUnavailableError as exc:
        if exc.reason in _OPTIONAL_ATHLETE_PROFILE_FAILURE_REASONS:
            payload: dict[str, object] = {
                "endpoint": endpoint,
                "reason": exc.reason,
            }
            if exc.status is not None:
                payload["status"] = exc.status
            _emit("athlete_zones_sync_skipped", **payload)
            return 0
        raise

    if response.status in (403, 404):
        _emit(
            "athlete_zones_sync_skipped",
            endpoint=endpoint,
            status=response.status,
            reason="endpoint_unavailable",
        )
        return 0
    if not isinstance(response.data, dict):
        return 0

    journal_schema_drift(response.data, "athlete_zones")
    _write_athlete_profile_payload(
        repo,
        profile_key="athlete_zones",
        payload_kind="profile",
        endpoint=endpoint,
        fetched_at=now_iso,
        payload_json=json.dumps(response.data),
    )
    return 1
