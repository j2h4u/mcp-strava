"""SQLite repository boundary for activities, streams, zones, kudos, and sync metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from mcp_strava.adapters.sqlite.connection import open_expected_mirror_db, open_fixture_db
from mcp_strava.constants import Config, TRAINING_SPORTS
from mcp_strava.types import (
    DailyLoadPoint,
    RepositoryActivityRow,
    RepositoryDailyLoadStatus,
    RepositorySyncLogEntry,
)


@dataclass
class SQLiteRepository:
    """Focused SQLite repository with explicit unit-of-work lifetime."""

    conn: object

    @classmethod
    def from_path(cls, db_path: str | Path, expected_mirror: bool = False) -> "SQLiteRepository":
        path = Path(db_path)
        conn = open_expected_mirror_db(path) if expected_mirror else open_fixture_db(path)
        return cls(conn=conn)

    @classmethod
    def from_connection(cls, conn: object) -> "SQLiteRepository":
        return cls(conn=conn)

    def __enter__(self) -> "SQLiteRepository":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.conn.close()

    def close(self) -> None:
        self.conn.close()

    # Activities
    def recent_activities(self, limit: int = 15) -> list[RepositoryActivityRow]:
        rows = self.conn.execute(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json, synced_at
            FROM activities
            ORDER BY date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._to_activity_row(r) for r in rows]

    def activity_by_id(self, activity_id: int) -> RepositoryActivityRow | None:
        row = self.conn.execute(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json, synced_at
            FROM activities
            WHERE id = ?
            """,
            (activity_id,),
        ).fetchone()
        return self._to_activity_row(row) if row else None

    def activity_rows_between(self, start_day: str, end_day: str) -> list[RepositoryActivityRow]:
        rows = self.conn.execute(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json, synced_at
            FROM activities
            WHERE SUBSTR(date, 1, 10) BETWEEN ? AND ?
            ORDER BY date ASC
            """,
            (start_day, end_day),
        ).fetchall()
        return [self._to_activity_row(r) for r in rows]

    def daily_activity_presence(self, day: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM activities WHERE SUBSTR(date, 1, 10) = ? LIMIT 1",
            (day,),
        ).fetchone()
        return row is not None

    def first_activity_day(self, sport_filter: str | None = None) -> str | None:
        sport_sql, sport_params = self._sport_where_clause(sport_filter)
        row = self.conn.execute(
            """
            SELECT MIN(SUBSTR(date,1,10)) as day
            FROM activities a
            WHERE 1=1
            """
            + sport_sql,
            sport_params,
        ).fetchone()
        return row["day"] if row and row["day"] else None

    def upsert_activity_summary(
        self,
        *,
        activity_id: int,
        date: str,
        name: str,
        sport_type: str,
        distance: float,
        moving_time: int,
        elapsed_time: int,
        total_elevation_gain: float,
        summary_json: str,
        synced_at: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO activities (
                id, date, name, sport_type, distance, moving_time,
                elapsed_time, total_elevation_gain, summary_json, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                date=excluded.date,
                name=excluded.name,
                sport_type=excluded.sport_type,
                distance=excluded.distance,
                moving_time=excluded.moving_time,
                elapsed_time=excluded.elapsed_time,
                total_elevation_gain=excluded.total_elevation_gain,
                summary_json=excluded.summary_json,
                synced_at=excluded.synced_at
            """,
            (
                activity_id,
                date,
                name,
                sport_type,
                distance,
                moving_time,
                elapsed_time,
                total_elevation_gain,
                summary_json,
                synced_at,
            ),
        )
        self.conn.commit()

    def update_activity_detail(self, activity_id: int, detail_json: str) -> None:
        self.conn.execute(
            "UPDATE activities SET detail_json = ? WHERE id = ?",
            (detail_json, activity_id),
        )
        self.conn.commit()

    # Streams and load
    def activity_stream_rows(self, activity_id: int) -> list[tuple]:
        return self.conn.execute(
            """
            SELECT activity_id, time_offset, heartrate, velocity, altitude,
                   cadence, latlng, grade, gap_speed, gap_distance, is_moving
            FROM streams
            WHERE activity_id = ?
            ORDER BY time_offset ASC
            """,
            (activity_id,),
        ).fetchall()

    def _sport_where_clause(self, sport_filter: str | None) -> tuple[str, list[object]]:
        params: list[object] = []
        if sport_filter == "training":
            placeholders = ",".join("?" * len(TRAINING_SPORTS))
            params.extend(TRAINING_SPORTS)
            return f" AND a.sport_type IN ({placeholders})", params
        return "", params

    def observed_trimp_history(
        self,
        *,
        since_day: str | None = None,
        until_day: str | None = None,
        sport_filter: str | None = None,
    ) -> dict[str, float]:
        where = ["s.heartrate IS NOT NULL"]
        params: list[object] = []
        if since_day is not None:
            where.append("SUBSTR(a.date,1,10) >= ?")
            params.append(since_day)
        if until_day is not None:
            where.append("SUBSTR(a.date,1,10) <= ?")
            params.append(until_day)
        sport_sql, sport_params = self._sport_where_clause(sport_filter)
        params.extend(sport_params)

        rows = self.conn.execute(
            """
            SELECT SUBSTR(a.date,1,10) as day,
                   """
            + Config.SQL.TRIMP_S
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
        ).fetchall()
        return {r["day"]: round(r["trimp"], 1) for r in rows}

    def daily_load_status(self, day: str) -> RepositoryDailyLoadStatus:
        activity_row = self.conn.execute(
            "SELECT COUNT(*) FROM activities WHERE SUBSTR(date, 1, 10) = ?",
            (day,),
        ).fetchone()
        stream_row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM streams s
            JOIN activities a ON a.id = s.activity_id
            WHERE SUBSTR(a.date, 1, 10) = ?
            """,
            (day,),
        ).fetchone()
        hr_row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM streams s
            JOIN activities a ON a.id = s.activity_id
            WHERE SUBSTR(a.date, 1, 10) = ?
              AND s.heartrate IS NOT NULL
            """,
            (day,),
        ).fetchone()

        activity_count = int(activity_row[0] if activity_row else 0)
        stream_count = int(stream_row[0] if stream_row else 0)
        hr_count = int(hr_row[0] if hr_row else 0)

        if activity_count == 0:
            status = "REST"
        elif stream_count == 0:
            status = "UNKNOWN"
        elif hr_count == 0:
            status = "PARTIAL"
        else:
            status = "OBSERVED"

        return RepositoryDailyLoadStatus(
            day=day,
            status=status,
            observed_trimp=0.0,
            effective_trimp=0.0,
            activity_count=activity_count,
            stream_points=stream_count,
            heartrate_points=hr_count,
        )

    def daily_load_points_between(
        self,
        start_day: str,
        end_day: str,
        *,
        sport_filter: str | None = None,
    ) -> list[DailyLoadPoint]:
        daily_activity_counts: dict[str, int] = {}
        daily_stream_counts: dict[str, int] = {}
        daily_hr_counts: dict[str, int] = {}

        sport_sql, sport_params = self._sport_where_clause(sport_filter)

        act_rows = self.conn.execute(
            """
            SELECT SUBSTR(date,1,10) as day, COUNT(*) as c
            FROM activities
            WHERE SUBSTR(date,1,10) BETWEEN ? AND ?
            """
            + (sport_sql.replace("a.", "") if sport_sql else "")
            + """
            GROUP BY day
            """,
            [start_day, end_day, *sport_params],
        ).fetchall()
        for row in act_rows:
            daily_activity_counts[row["day"]] = int(row["c"])

        stream_rows = self.conn.execute(
            """
            SELECT SUBSTR(a.date,1,10) as day, COUNT(*) as c
            FROM activities a
            JOIN streams s ON s.activity_id = a.id
            WHERE SUBSTR(a.date,1,10) BETWEEN ? AND ?
            """
            + sport_sql
            + """
            GROUP BY day
            """,
            [start_day, end_day, *sport_params],
        ).fetchall()
        for row in stream_rows:
            daily_stream_counts[row["day"]] = int(row["c"])

        hr_rows = self.conn.execute(
            """
            SELECT SUBSTR(a.date,1,10) as day, COUNT(*) as c
            FROM activities a
            JOIN streams s ON s.activity_id = a.id
            WHERE SUBSTR(a.date,1,10) BETWEEN ? AND ?
              AND s.heartrate IS NOT NULL
            """
            + sport_sql
            + """
            GROUP BY day
            """,
            [start_day, end_day, *sport_params],
        ).fetchall()
        for row in hr_rows:
            daily_hr_counts[row["day"]] = int(row["c"])

        observed_trimp = self.observed_trimp_history(
            since_day=start_day,
            until_day=end_day,
            sport_filter=sport_filter,
        )
        points: list[DailyLoadPoint] = []
        current = start_day
        while current <= end_day:
            activity_count = daily_activity_counts.get(current, 0)
            stream_count = daily_stream_counts.get(current, 0)
            hr_count = daily_hr_counts.get(current, 0)
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
                observed = round(observed_trimp.get(current, 0.0), 1)
                effective = observed
            points.append(
                DailyLoadPoint(
                    date=current,
                    status=status,
                    observed_trimp=observed,
                    effective_trimp=effective,
                    activity_count=activity_count,
                    stream_points=stream_count,
                    heartrate_points=hr_count,
                )
            )
            y, m, d = map(int, current.split("-"))
            from datetime import date, timedelta
            current = (date(y, m, d) + timedelta(days=1)).isoformat()
        return points

    def effective_trimp_history(
        self,
        start_day: str,
        end_day: str,
        *,
        sport_filter: str | None = None,
    ) -> dict[str, float]:
        return {
            point.date: point.effective_trimp
            for point in self.daily_load_points_between(start_day, end_day, sport_filter=sport_filter)
        }

    def activity_moving_time(self, activity_id: int) -> int | None:
        row = self.conn.execute("SELECT moving_time FROM activities WHERE id=?", (activity_id,)).fetchone()
        return int(row["moving_time"]) if row and row["moving_time"] is not None else None

    def stream_hr_velocity_rows(self, activity_id: int, min_velocity: float) -> list[object]:
        return self.conn.execute(
            """
            SELECT time_offset, heartrate, velocity, grade FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL AND velocity IS NOT NULL
              AND velocity > ?
            ORDER BY time_offset
            """,
            (activity_id, min_velocity),
        ).fetchall()

    def stream_hr_velocity_simple_rows(self, activity_id: int, min_velocity: float) -> list[object]:
        return self.conn.execute(
            """
            SELECT heartrate, velocity FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL AND velocity > ?
            ORDER BY time_offset
            """,
            (activity_id, min_velocity),
        ).fetchall()

    def stream_hr_velocity_time_rows(self, activity_id: int) -> list[object]:
        return self.conn.execute(
            """
            SELECT time_offset, heartrate, velocity FROM streams
            WHERE activity_id=? AND heartrate IS NOT NULL
            ORDER BY time_offset
            """,
            (activity_id,),
        ).fetchall()

    def activity_hr_summary(self, activity_id: int) -> tuple[float | None, int]:
        row = self.conn.execute(
            """
            SELECT AVG(heartrate) as avg_hr, COUNT(*) as n
            FROM streams WHERE activity_id=? AND heartrate IS NOT NULL
            """,
            (activity_id,),
        ).fetchone()
        return (row["avg_hr"], int(row["n"] or 0)) if row else (None, 0)

    def activity_avg_velocity(self, activity_id: int) -> float | None:
        row = self.conn.execute(
            "SELECT AVG(velocity) as avg_vel FROM streams WHERE activity_id=? AND velocity IS NOT NULL",
            (activity_id,),
        ).fetchone()
        return row["avg_vel"] if row else None

    def stream_hr_time_rows(self, activity_id: int) -> list[object]:
        return self.conn.execute(
            """
            SELECT time_offset, heartrate FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL
            ORDER BY time_offset
            """,
            (activity_id,),
        ).fetchall()

    def stream_altitude_rows(self, activity_id: int) -> list[object]:
        return self.conn.execute(
            """
            SELECT time_offset, altitude FROM streams
            WHERE activity_id=? AND altitude IS NOT NULL
            ORDER BY time_offset
            """,
            (activity_id,),
        ).fetchall()

    def activity_trimp(self, activity_id: int) -> float:
        row = self.conn.execute(
            "SELECT " + Config.SQL.TRIMP + " FROM streams WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()
        return round(row["trimp"], 1) if row and row["trimp"] is not None else 0.0

    def activity_cc(self, activity_id: int, min_velocity: float) -> float | None:
        row = self.conn.execute(
            """
            SELECT AVG(heartrate) as avg_hr, AVG(velocity) as avg_vel
            FROM streams WHERE activity_id = ? AND heartrate IS NOT NULL
              AND velocity > ?
            """,
            (activity_id, min_velocity),
        ).fetchone()
        if not row or not row["avg_hr"] or not row["avg_vel"] or row["avg_vel"] <= 0:
            return None
        return round(row["avg_hr"] / row["avg_vel"], 2)

    def activity_median_heartrate(self, activity_id: int) -> float | None:
        row = self.conn.execute(
            """
            SELECT heartrate FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL
            ORDER BY heartrate
            LIMIT 1 OFFSET (
                SELECT COUNT(*) FROM streams
                WHERE activity_id = ? AND heartrate IS NOT NULL
            ) / 2
            """,
            (activity_id, activity_id),
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def max_heartrate(self) -> float | None:
        row = self.conn.execute("SELECT MAX(heartrate) as hr FROM streams WHERE heartrate IS NOT NULL").fetchone()
        return float(row["hr"]) if row and row["hr"] is not None else None

    def activity_z5_seconds(self, activity_id: int, z5_threshold: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as sec FROM streams WHERE activity_id = ? AND heartrate >= ?",
            (activity_id, z5_threshold),
        ).fetchone()
        return int(row["sec"] or 0) if row else 0

    def activity_efficiency_rows(self) -> list[object]:
        return self.conn.execute(
            """
            SELECT SUBSTR(a.date, 1, 10) as day, a.sport_type,
                   a.distance / 1000 as dist_km, a.moving_time / 60.0 as time_min,
                   a.total_elevation_gain as elev,
                   AVG(s.heartrate) as avg_hr, AVG(s.velocity) as avg_vel
            FROM activities a
            JOIN streams s ON a.id = s.activity_id
            WHERE s.heartrate IS NOT NULL AND s.velocity > 0
            GROUP BY a.id
            HAVING avg_hr > 0 AND avg_vel > 0
            """
        ).fetchall()

    def total_distance_km_between(self, start_day: str, end_day: str, sports: tuple[str, ...] | list[str]) -> float:
        if not sports:
            return 0.0
        placeholders = ",".join("?" * len(sports))
        row = self.conn.execute(
            f"""
            SELECT SUM(distance)/1000 as km FROM activities
            WHERE sport_type IN ({placeholders})
              AND SUBSTR(date,1,10) >= ?
              AND SUBSTR(date,1,10) <= ?
            """,
            [*sports, start_day, end_day],
        ).fetchone()
        return float(row["km"] or 0.0) if row else 0.0

    def insert_stream_rows_chunked(
        self,
        activity_id: int,
        rows: Iterable[dict],
        chunk_size: int = 5000,
    ) -> int:
        payload = list(rows)
        total = len(payload)
        if total == 0:
            return 0

        for start in range(0, total, chunk_size):
            chunk = payload[start : start + chunk_size]
            bound = [
                (
                    activity_id,
                    row["time_offset"],
                    row.get("heartrate"),
                    row.get("velocity"),
                    row.get("altitude"),
                    row.get("cadence"),
                    row.get("latlng"),
                    row.get("grade"),
                    row.get("gap_speed"),
                    row.get("gap_distance"),
                    row.get("is_moving"),
                )
                for row in chunk
            ]
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO streams
                (activity_id, time_offset, heartrate, velocity, altitude, cadence,
                 latlng, grade, gap_speed, gap_distance, is_moving)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                bound,
            )
            self.conn.commit()

        return total

    def delete_stream_rows_for_activity(self, activity_id: int) -> None:
        self.conn.execute("DELETE FROM streams WHERE activity_id = ?", (activity_id,))
        self.conn.commit()

    # Zones
    def latest_athlete_zones(self) -> str | None:
        row = self.conn.execute(
            "SELECT zones_json FROM athlete_zones ORDER BY fetched_at DESC LIMIT 1"
        ).fetchone()
        return str(row[0]) if row else None

    def insert_athlete_zones(self, fetched_at: str, zones_json: str) -> None:
        self.conn.execute(
            "INSERT INTO athlete_zones (fetched_at, zones_json) VALUES (?, ?)",
            (fetched_at, zones_json),
        )
        self.conn.commit()

    # Kudos
    def list_kudos(self, limit: int = 100) -> list[tuple]:
        return self.conn.execute(
            """
            SELECT activity_id, firstname, lastname, fetched_at
            FROM kudos
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def upsert_kudos(self, activity_id: int, firstname: str, lastname: str, fetched_at: str) -> None:
        self.conn.execute(
            """
            INSERT INTO kudos (activity_id, firstname, lastname, fetched_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(activity_id, firstname, lastname) DO UPDATE SET
              fetched_at = excluded.fetched_at
            """,
            (activity_id, firstname, lastname, fetched_at),
        )
        self.conn.commit()

    # Sync metadata
    def append_sync_log(
        self,
        *,
        timestamp: str,
        status: str,
        activities_seen: int | None,
        activities_new: int | None,
        streams_fetched: int | None,
        details_fetched: int | None,
        api_calls: int | None,
        error: str | None,
        kudos_fetched: int | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO sync_log (
                timestamp, status, activities_seen, activities_new,
                streams_fetched, details_fetched, api_calls, error, kudos_fetched
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                status,
                activities_seen,
                activities_new,
                streams_fetched,
                details_fetched,
                api_calls,
                error,
                kudos_fetched,
            ),
        )
        self.conn.commit()

    def read_sync_log(self, limit: int = 20) -> list[RepositorySyncLogEntry]:
        rows = self.conn.execute(
            """
            SELECT timestamp, status, activities_seen, activities_new,
                   streams_fetched, details_fetched, api_calls, error, kudos_fetched
            FROM sync_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            RepositorySyncLogEntry(
                timestamp=r[0],
                status=r[1],
                activities_seen=r[2],
                activities_new=r[3],
                streams_fetched=r[4],
                details_fetched=r[5],
                api_calls=r[6],
                error=r[7],
                kudos_fetched=r[8],
            )
            for r in rows
        ]

    def _to_activity_row(self, row) -> RepositoryActivityRow:
        return RepositoryActivityRow(
            id=row["id"],
            date=row["date"],
            name=row["name"],
            sport_type=row["sport_type"],
            distance=row["distance"],
            moving_time=row["moving_time"],
            elapsed_time=row["elapsed_time"],
            total_elevation_gain=row["total_elevation_gain"],
            summary_json=row["summary_json"],
            detail_json=row["detail_json"],
            synced_at=row["synced_at"],
        )
