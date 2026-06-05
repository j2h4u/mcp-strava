"""Read-only stream metric queries used by materialization and status facts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from mcp_strava.adapters.duckdb.repository_models import ActivityStreamScalars, ActivityZoneTrimp
from mcp_strava.adapters.duckdb.repository_utils import Row, as_float, as_int, as_int_opt
from mcp_strava.adapters.duckdb.repository_utils import placeholders as make_placeholders
from mcp_strava.adapters.duckdb.trimp_sql import build_trimp_sql
from mcp_strava.constants import Config


class StreamMetricRepository(Protocol):
    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> Row | None: ...

    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...


def stream_hr_velocity_simple_rows(
    repo: StreamMetricRepository, activity_id: int, min_velocity: float
) -> list[dict[str, Any]]:
    return repo._fetchall(
        """
        SELECT heartrate, velocity FROM streams
        WHERE activity_id = ? AND heartrate IS NOT NULL AND velocity > ?
        ORDER BY time_offset
        """,
        [activity_id, min_velocity],
    )


def stream_hr_velocity_simple_rows_for_activities(
    repo: StreamMetricRepository, activity_ids: Iterable[int], min_velocity: float
) -> dict[int, list[dict[str, Any]]]:
    ids = sorted({int(activity_id) for activity_id in activity_ids})
    if not ids:
        return {}
    rows = repo._fetchall(
        f"""
        SELECT activity_id, heartrate, velocity FROM streams
        WHERE activity_id IN ({make_placeholders(len(ids))})
          AND heartrate IS NOT NULL AND velocity > ?
        ORDER BY activity_id, time_offset
        """,
        [*ids, min_velocity],
    )
    grouped: dict[int, list[dict[str, Any]]] = {activity_id: [] for activity_id in ids}
    for row in rows:
        activity_id = as_int(row["activity_id"])
        grouped.setdefault(activity_id, []).append({"heartrate": row["heartrate"], "velocity": row["velocity"]})
    return grouped


def stream_hr_velocity_time_rows(repo: StreamMetricRepository, activity_id: int) -> list[dict[str, Any]]:
    return repo._fetchall(
        """
        SELECT time_offset, heartrate, velocity FROM streams
        WHERE activity_id=? AND heartrate IS NOT NULL
        ORDER BY time_offset
        """,
        [activity_id],
    )


def stream_hr_velocity_time_rows_for_activities(
    repo: StreamMetricRepository, activity_ids: Iterable[int]
) -> dict[int, list[dict[str, Any]]]:
    ids = sorted({int(activity_id) for activity_id in activity_ids})
    if not ids:
        return {}
    rows = repo._fetchall(
        f"""
        SELECT activity_id, time_offset, heartrate, velocity FROM streams
        WHERE activity_id IN ({make_placeholders(len(ids))}) AND heartrate IS NOT NULL
        ORDER BY activity_id, time_offset
        """,
        ids,
    )
    grouped: dict[int, list[dict[str, Any]]] = {activity_id: [] for activity_id in ids}
    for row in rows:
        activity_id = as_int(row["activity_id"])
        grouped.setdefault(activity_id, []).append(
            {"time_offset": row["time_offset"], "heartrate": row["heartrate"], "velocity": row["velocity"]}
        )
    return grouped


def stream_altitude_rows(repo: StreamMetricRepository, activity_id: int) -> list[dict[str, Any]]:
    return repo._fetchall(
        """
        SELECT time_offset, altitude FROM streams
        WHERE activity_id=? AND altitude IS NOT NULL
        ORDER BY time_offset
        """,
        [activity_id],
    )


def stream_altitude_rows_for_activities(
    repo: StreamMetricRepository, activity_ids: Iterable[int]
) -> dict[int, list[dict[str, Any]]]:
    ids = sorted({int(activity_id) for activity_id in activity_ids})
    if not ids:
        return {}
    rows = repo._fetchall(
        f"""
        SELECT activity_id, time_offset, altitude FROM streams
        WHERE activity_id IN ({make_placeholders(len(ids))}) AND altitude IS NOT NULL
        ORDER BY activity_id, time_offset
        """,
        ids,
    )
    grouped: dict[int, list[dict[str, Any]]] = {activity_id: [] for activity_id in ids}
    for row in rows:
        activity_id = as_int(row["activity_id"])
        grouped.setdefault(activity_id, []).append({"time_offset": row["time_offset"], "altitude": row["altitude"]})
    return grouped


def stream_counts_for_activity(repo: StreamMetricRepository, activity_id: int) -> tuple[int, int]:
    row = repo._fetchone(
        """
        SELECT COUNT(*) AS stream_count,
               SUM(CASE WHEN heartrate IS NOT NULL THEN 1 ELSE 0 END) AS hr_count
        FROM streams
        WHERE activity_id = ?
        """,
        [activity_id],
    )
    assert row is not None, "aggregate COUNT always returns a row"
    return as_int(row["stream_count"]), as_int(row["hr_count"])


def activity_stream_scalars_for_materialization(
    repo: StreamMetricRepository, activity_ids: Iterable[int], min_velocity: float
) -> dict[int, ActivityStreamScalars]:
    ids = sorted({int(activity_id) for activity_id in activity_ids})
    if not ids:
        return {}
    rows = repo._fetchall(
        f"""
        SELECT
          activity_id,
          COUNT(*) AS stream_count,
          SUM(CASE WHEN heartrate IS NOT NULL THEN 1 ELSE 0 END) AS hr_count,
          MIN(heartrate) AS min_hr,
          MAX(heartrate) AS max_hr,
          AVG(CASE WHEN heartrate IS NOT NULL AND velocity > ? THEN heartrate ELSE NULL END) AS avg_hr_for_cc,
          AVG(CASE WHEN heartrate IS NOT NULL AND velocity > ? THEN velocity ELSE NULL END) AS avg_vel_for_cc,
          median(heartrate) AS median_hr
        FROM streams
        WHERE activity_id IN ({make_placeholders(len(ids))})
        GROUP BY activity_id
        """,
        [min_velocity, min_velocity, *ids],
    )
    scalars: dict[int, ActivityStreamScalars] = {
        activity_id: ActivityStreamScalars(
            stream_count=0,
            hr_count=0,
            min_hr=None,
            max_hr=None,
            cardiac_cost=None,
            median_hr=None,
        )
        for activity_id in ids
    }
    for row in rows:
        avg_vel = as_float(row["avg_vel_for_cc"]) if row["avg_vel_for_cc"] is not None else None
        avg_hr = as_float(row["avg_hr_for_cc"]) if row["avg_hr_for_cc"] is not None else None
        cardiac_cost = round(avg_hr / avg_vel, 2) if avg_hr and avg_vel and avg_vel > 0 else None
        activity_id = as_int(row["activity_id"])
        scalars[activity_id] = ActivityStreamScalars(
            stream_count=as_int(row["stream_count"]),
            hr_count=as_int(row["hr_count"]),
            min_hr=as_int_opt(row["min_hr"]),
            max_hr=as_int_opt(row["max_hr"]),
            cardiac_cost=cardiac_cost,
            median_hr=as_float(row["median_hr"]) if row["median_hr"] is not None else None,
        )
    return scalars


def zone_seconds_for_activity(
    repo: StreamMetricRepository, activity_id: int, bounds: list[int]
) -> tuple[int, int, int, int, int]:
    b = bounds
    row = repo._fetchone(
        """
        SELECT
          SUM(CASE WHEN heartrate < ? THEN 1 ELSE 0 END) AS z1,
          SUM(CASE WHEN heartrate >= ? AND heartrate < ? THEN 1 ELSE 0 END) AS z2,
          SUM(CASE WHEN heartrate >= ? AND heartrate < ? THEN 1 ELSE 0 END) AS z3,
          SUM(CASE WHEN heartrate >= ? AND heartrate < ? THEN 1 ELSE 0 END) AS z4,
          SUM(CASE WHEN heartrate >= ? THEN 1 ELSE 0 END) AS z5
        FROM streams
        WHERE activity_id = ? AND heartrate IS NOT NULL
        """,
        [b[0], b[0], b[1], b[1], b[2], b[2], b[3], b[-2], activity_id],
    )
    assert row is not None, "SUM aggregate always returns a row"
    z = [as_int(row[f"z{idx}"]) for idx in range(1, 6)]
    return z[0], z[1], z[2], z[3], z[4]


def activity_trimp(repo: StreamMetricRepository, activity_id: int, *, bounds: list[int]) -> float:
    row = repo._fetchone(
        "SELECT " + build_trimp_sql(bounds) + " FROM streams WHERE activity_id = ?",
        [activity_id],
    )
    return round(as_float(row["trimp"]), 1) if row and row["trimp"] is not None else 0.0


def max_heartrate_to_date(repo: StreamMetricRepository, activity_day: str) -> int | None:
    row = repo._fetchone(
        """
        SELECT MAX(s.heartrate) AS hr_max
        FROM streams s
        JOIN activities a ON a.id = s.activity_id
        WHERE s.heartrate IS NOT NULL
          AND a.activity_day <= CAST(? AS DATE)
        """,
        [activity_day],
    )
    return as_int(row["hr_max"]) if row and row["hr_max"] is not None else None


def max_heartrate_to_dates(repo: StreamMetricRepository, activity_days: Iterable[str]) -> dict[str, int | None]:
    days = sorted({str(day) for day in activity_days})
    if not days:
        return {}
    rows = repo._fetchall(
        f"""
        WITH requested(day) AS (
          VALUES {", ".join("(CAST(? AS DATE))" for _ in days)}
        ),
        day_hr AS (
          SELECT a.activity_day AS day, MAX(s.heartrate) AS day_hr_max
          FROM activities a
          JOIN streams s ON s.activity_id = a.id
          WHERE s.heartrate IS NOT NULL
            AND a.activity_day <= (SELECT MAX(day) FROM requested)
          GROUP BY a.activity_day
        ),
        running_hr AS (
          SELECT day,
                 MAX(day_hr_max) OVER (
                   ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                 ) AS hr_max
          FROM day_hr
        )
        SELECT r.day AS day,
               (
                 SELECT hr_max
                 FROM running_hr h
                 WHERE h.day <= r.day
                 ORDER BY h.day DESC
                 LIMIT 1
               ) AS hr_max
        FROM requested r
        """,
        days,
    )
    return {str(row["day"]): as_int(row["hr_max"]) if row["hr_max"] is not None else None for row in rows}


def activity_hr_range(repo: StreamMetricRepository, activity_id: int) -> tuple[int | None, int | None]:
    row = repo._fetchone(
        """
        SELECT MIN(heartrate) AS min_hr, MAX(heartrate) AS max_hr
        FROM streams
        WHERE activity_id = ? AND heartrate IS NOT NULL
        """,
        [activity_id],
    )
    if row and row["min_hr"] is not None:
        return as_int(row["min_hr"]), as_int(row["max_hr"])
    return None, None


def activity_cc(repo: StreamMetricRepository, activity_id: int, min_velocity: float) -> float | None:
    row = repo._fetchone(
        """
        SELECT AVG(heartrate) AS avg_hr, AVG(velocity) AS avg_vel
        FROM streams WHERE activity_id = ? AND heartrate IS NOT NULL
          AND velocity > ?
        """,
        [activity_id, min_velocity],
    )
    if not row or not row["avg_hr"] or not row["avg_vel"] or as_float(row["avg_vel"]) <= 0:
        return None
    return round(as_float(row["avg_hr"]) / as_float(row["avg_vel"]), 2)


def activity_median_heartrate(repo: StreamMetricRepository, activity_id: int) -> float | None:
    row = repo._fetchone(
        """
        SELECT median(heartrate) AS median_hr
        FROM streams
        WHERE activity_id = ? AND heartrate IS NOT NULL
        """,
        [activity_id],
    )
    return as_float(row["median_hr"]) if row and row["median_hr"] is not None else None


def activity_zone_trimp_for_bounds(
    repo: StreamMetricRepository, bounds_by_activity_id: dict[int, list[int]]
) -> dict[int, ActivityZoneTrimp]:
    if not bounds_by_activity_id:
        return {}
    coeff = Config.Zones.COEFF
    values_sql: list[str] = []
    params: list[object] = []
    for activity_id, bounds in sorted(bounds_by_activity_id.items()):
        values_sql.append("(?, ?, ?, ?, ?, ?)")
        params.extend([activity_id, bounds[0], bounds[1], bounds[2], bounds[3], bounds[-2]])
    rows = repo._fetchall(
        f"""
        WITH bounds(activity_id, b0, b1, b2, b3, b_last_zone) AS (
          VALUES {", ".join(values_sql)}
        )
        SELECT
          b.activity_id,
          SUM(CASE WHEN s.heartrate < b.b0 THEN 1 ELSE 0 END) AS z1,
          SUM(CASE WHEN s.heartrate >= b.b0 AND s.heartrate < b.b1 THEN 1 ELSE 0 END) AS z2,
          SUM(CASE WHEN s.heartrate >= b.b1 AND s.heartrate < b.b2 THEN 1 ELSE 0 END) AS z3,
          SUM(CASE WHEN s.heartrate >= b.b2 AND s.heartrate < b.b3 THEN 1 ELSE 0 END) AS z4,
          SUM(CASE WHEN s.heartrate >= b.b_last_zone THEN 1 ELSE 0 END) AS z5,
          (
            SUM(CASE WHEN s.heartrate < b.b0 THEN 1 ELSE 0 END) * {coeff[0]} +
            SUM(CASE WHEN s.heartrate >= b.b0 AND s.heartrate < b.b1 THEN 1 ELSE 0 END) * {coeff[1]} +
            SUM(CASE WHEN s.heartrate >= b.b1 AND s.heartrate < b.b2 THEN 1 ELSE 0 END) * {coeff[2]} +
            SUM(CASE WHEN s.heartrate >= b.b2 AND s.heartrate < b.b3 THEN 1 ELSE 0 END) * {coeff[3]} +
            SUM(CASE WHEN s.heartrate >= b.b3 AND s.heartrate < b.b_last_zone THEN 1 ELSE 0 END) * {coeff[4]} +
            SUM(CASE WHEN s.heartrate >= b.b_last_zone THEN 1 ELSE 0 END) * {coeff[5]}
          ) / 60.0 AS trimp
        FROM bounds b
        LEFT JOIN streams s ON s.activity_id = b.activity_id AND s.heartrate IS NOT NULL
        GROUP BY b.activity_id
        """,
        params,
    )
    result: dict[int, ActivityZoneTrimp] = {}
    for row in rows:
        activity_id = as_int(row["activity_id"])
        result[activity_id] = ActivityZoneTrimp(
            zone1_seconds=as_int(row["z1"]),
            zone2_seconds=as_int(row["z2"]),
            zone3_seconds=as_int(row["z3"]),
            zone4_seconds=as_int(row["z4"]),
            zone5_seconds=as_int(row["z5"]),
            trimp=round(as_float(row["trimp"]), 1) if row["trimp"] is not None else 0.0,
        )
    return result


def max_heartrate(repo: StreamMetricRepository) -> float | None:
    row = repo._fetchone("SELECT MAX(heartrate) AS hr FROM streams WHERE heartrate IS NOT NULL")
    return as_float(row["hr"]) if row and row["hr"] is not None else None
