"""SQLite repository boundary for activities, streams, zones, kudos, and sync metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from mcp_strava.adapters.sqlite.connection import open_expected_mirror_db, open_fixture_db
from mcp_strava.types import (
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

    def trimp_history_observed(self, days: int) -> dict[str, float]:
        rows = self.conn.execute(
            """
            SELECT SUBSTR(a.date, 1, 10) AS day,
                   ROUND(SUM(
                     CASE WHEN s.heartrate > 0 THEN
                       (CASE
                          WHEN s.heartrate <= 100 THEN 1.0
                          WHEN s.heartrate <= 120 THEN 2.0
                          WHEN s.heartrate <= 140 THEN 3.0
                          WHEN s.heartrate <= 160 THEN 4.0
                          ELSE 5.0
                       END) * (1.0 / 60.0)
                     ELSE 0 END
                   ), 1) AS trimp
            FROM activities a
            JOIN streams s ON a.id = s.activity_id
            WHERE s.heartrate IS NOT NULL
              AND SUBSTR(a.date, 1, 10) >= DATE('now', ?)
            GROUP BY day
            """,
            (f"-{int(days)} days",),
        ).fetchall()
        return {r[0]: float(r[1] or 0.0) for r in rows}

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
