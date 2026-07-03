"""Kudos refresh helpers."""

from __future__ import annotations

from mcp_strava.adapters.duckdb.kudos_store import activities_missing_kudos, upsert_kudos


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
