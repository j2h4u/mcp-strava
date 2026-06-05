"""Daily load and TRIMP history queries over DuckDB streams."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol

from mcp_strava.adapters.duckdb.repository_utils import Row, as_float, as_int
from mcp_strava.adapters.duckdb.trimp_sql import build_trimp_sql
from mcp_strava.metrics import discounted_effective_trimp
from mcp_strava.sports import SPORT_TRAINING as TRAINING_SPORTS
from mcp_strava.types import DailyLoadPoint


class DailyLoadRepository(Protocol):
    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...


def _sport_where_clause(sport_filter: str | None) -> tuple[str, list[object]]:
    params: list[object] = []
    if sport_filter == "training":
        placeholders = ",".join("?" * len(TRAINING_SPORTS))
        params.extend(TRAINING_SPORTS)
        return f" AND a.sport_type IN ({placeholders})", params
    return "", params


def observed_trimp_history(
    repo: DailyLoadRepository,
    *,
    bounds: list[int],
    since_day: str | None = None,
    until_day: str | None = None,
    sport_filter: str | None = None,
) -> dict[str, float]:
    """Return daily TRIMP history keyed by ISO date string."""
    where = ["s.heartrate IS NOT NULL"]
    params: list[object] = []
    if since_day is not None:
        where.append("a.activity_day >= CAST(? AS DATE)")
        params.append(since_day)
    if until_day is not None:
        where.append("a.activity_day <= CAST(? AS DATE)")
        params.append(until_day)
    sport_sql, sport_params = _sport_where_clause(sport_filter)
    params.extend(sport_params)
    rows = repo._fetchall(
        """
        SELECT a.activity_day AS day,
               """
        + build_trimp_sql(bounds, alias="s.")
        + """
        FROM activities a
        JOIN streams s ON a.id = s.activity_id
        WHERE """
        + " AND ".join(where)
        + sport_sql
        + """
        GROUP BY day
        """,
        params,
    )
    return {str(row["day"]): round(as_float(row["trimp"]), 1) for row in rows}


def observed_trimp_history_by_sport(
    repo: DailyLoadRepository,
    *,
    bounds: list[int],
    since_day: str | None = None,
    until_day: str | None = None,
    sport_filter: str | None = None,
) -> dict[str, dict[str, float]]:
    """Return daily raw TRIMP broken down per sport: {day -> {sport -> trimp}}."""
    where = ["s.heartrate IS NOT NULL"]
    params: list[object] = []
    if since_day is not None:
        where.append("a.activity_day >= CAST(? AS DATE)")
        params.append(since_day)
    if until_day is not None:
        where.append("a.activity_day <= CAST(? AS DATE)")
        params.append(until_day)
    sport_sql, sport_params = _sport_where_clause(sport_filter)
    params.extend(sport_params)
    rows = repo._fetchall(
        """
        SELECT a.activity_day AS day,
               a.sport_type AS sport,
               """
        + build_trimp_sql(bounds, alias="s.")
        + """
        FROM activities a
        JOIN streams s ON a.id = s.activity_id
        WHERE """
        + " AND ".join(where)
        + sport_sql
        + """
        GROUP BY day, sport
        """,
        params,
    )
    by_sport: dict[str, dict[str, float]] = {}
    for row in rows:
        day = str(row["day"])
        by_sport.setdefault(day, {})[str(row["sport"])] = round(as_float(row["trimp"]), 1)
    return by_sport


def daily_load_points_between(
    repo: DailyLoadRepository,
    start_day: str,
    end_day: str,
    *,
    bounds: list[int],
    sport_filter: str | None = None,
) -> list[DailyLoadPoint]:
    daily_activity_counts: dict[str, int] = {}
    daily_stream_counts: dict[str, int] = {}
    daily_hr_counts: dict[str, int] = {}
    sport_sql, sport_params = _sport_where_clause(sport_filter)

    act_rows = repo._fetchall(
        """
        SELECT activity_day AS day, COUNT(*) AS c
        FROM activities a
        WHERE activity_day BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
        """
        + sport_sql
        + """
        GROUP BY day
        """,
        [start_day, end_day, *sport_params],
    )
    for row in act_rows:
        daily_activity_counts[str(row["day"])] = as_int(row["c"])

    stream_rows = repo._fetchall(
        """
        SELECT a.activity_day AS day, COUNT(*) AS c
        FROM activities a
        JOIN streams s ON s.activity_id = a.id
        WHERE a.activity_day BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
        """
        + sport_sql
        + """
        GROUP BY day
        """,
        [start_day, end_day, *sport_params],
    )
    for row in stream_rows:
        daily_stream_counts[str(row["day"])] = as_int(row["c"])

    hr_rows = repo._fetchall(
        """
        SELECT a.activity_day AS day, COUNT(*) AS c
        FROM activities a
        JOIN streams s ON s.activity_id = a.id
        WHERE a.activity_day BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
          AND s.heartrate IS NOT NULL
        """
        + sport_sql
        + """
        GROUP BY day
        """,
        [start_day, end_day, *sport_params],
    )
    for row in hr_rows:
        daily_hr_counts[str(row["day"])] = as_int(row["c"])

    observed_trimp = observed_trimp_history(
        repo,
        bounds=bounds,
        since_day=start_day,
        until_day=end_day,
        sport_filter=sport_filter,
    )
    observed_trimp_by_sport = observed_trimp_history_by_sport(
        repo,
        bounds=bounds,
        since_day=start_day,
        until_day=end_day,
        sport_filter=sport_filter,
    )
    points: list[DailyLoadPoint] = []
    current = date.fromisoformat(start_day)
    end = date.fromisoformat(end_day)
    while current <= end:
        current_text = current.isoformat()
        activity_count = daily_activity_counts.get(current_text, 0)
        stream_count = daily_stream_counts.get(current_text, 0)
        hr_count = daily_hr_counts.get(current_text, 0)
        if activity_count == 0:
            status = "REST"
            observed = None
            effective = 0.0
        elif stream_count == 0:
            status = "UNKNOWN"
            observed = None
            effective = 0.0
        elif hr_count == 0:
            status = "PARTIAL"
            observed = None
            effective = 0.0
        else:
            status = "OBSERVED"
            observed = round(observed_trimp.get(current_text, 0.0), 1)
            effective = discounted_effective_trimp(observed_trimp_by_sport.get(current_text, {}))
        points.append(
            DailyLoadPoint(
                date=current_text,
                status=status,
                observed_trimp=observed,
                effective_trimp=effective,
                activity_count=activity_count,
                stream_points=stream_count,
                heartrate_points=hr_count,
            )
        )
        current = current.fromordinal(current.toordinal() + 1)
    return points


def effective_trimp_history(
    repo: DailyLoadRepository,
    start_day: str,
    end_day: str,
    *,
    bounds: list[int],
    sport_filter: str | None = None,
) -> dict[str, float]:
    return {
        point.date: point.effective_trimp
        for point in daily_load_points_between(repo, start_day, end_day, bounds=bounds, sport_filter=sport_filter)
    }
