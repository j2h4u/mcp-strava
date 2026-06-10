"""DuckDB-backed refresh runtime state store."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import cast

from mcp_strava.adapters.duckdb.connection import DuckDBConn, duckdb_process_lock
from mcp_strava.adapters.duckdb.repository_utils import (
    Row,
)
from mcp_strava.adapters.duckdb.repository_utils import (
    as_int as _as_int,
)
from mcp_strava.adapters.duckdb.repository_utils import (
    as_str_opt as _as_str_opt,
)
from mcp_strava.adapters.duckdb.repository_utils import (
    normalize_cell as _normalize_cell,
)
from mcp_strava.types import ALLOWED_REASON_CODES, RefreshRequestRow, RefreshStateRow


@dataclass
class RefreshStateStore:
    conn: DuckDBConn
    _transaction_depth: int = field(default=0, init=False, repr=False)

    @classmethod
    def from_connection(cls, conn: DuckDBConn) -> RefreshStateStore:
        store = cls(conn)
        store._ensure_column_last_full_summary_sync_at()
        return store

    def _ensure_column_last_full_summary_sync_at(self) -> None:
        with duckdb_process_lock():
            self.conn.execute(
                "ALTER TABLE refresh_state ADD COLUMN IF NOT EXISTS last_full_summary_sync_at VARCHAR"
            )

    def _execute(self, sql: str, params: Iterable[object] | None = None):
        with duckdb_process_lock():
            return self.conn.execute(sql, list(params or []))

    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> Row | None:
        result = self._execute(sql, params)
        row = result.fetchone()
        if row is None:
            return None
        columns: list[str] = [item[0] for item in result.description]
        return {
            column: _normalize_cell(value)
            for column, value in zip(columns, cast("tuple[object, ...]", row), strict=False)
        }

    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]:
        result = self._execute(sql, params)
        columns: list[str] = [item[0] for item in result.description]
        return [
            {
                column: _normalize_cell(value)
                for column, value in zip(columns, cast("tuple[object, ...]", row), strict=False)
            }
            for row in result.fetchall()
        ]

    def _commit_if_standalone(self) -> None:
        if self._transaction_depth == 0:
            with duckdb_process_lock():
                self.conn.commit()

    def _next_id(self, table: str) -> int:
        if table != "refresh_requests":
            raise ValueError(f"unsupported refresh-state table: {table}")
        row = self._fetchone(f"SELECT COALESCE(MAX(id), 0) + 1 AS id FROM {table}")
        if row is None:
            raise RuntimeError(f"could not allocate next id for {table}")
        value = row["id"]
        return _as_int(value, default=1)

    def get_refresh_state(self) -> RefreshStateRow:
        row = self._fetchone("SELECT * FROM refresh_state WHERE id = 1")
        if row is None:
            self._execute("INSERT INTO refresh_state (id) VALUES (1)")
            self._commit_if_standalone()
            row = self._fetchone("SELECT * FROM refresh_state WHERE id = 1")
        assert row is not None, "refresh_state row must exist after INSERT"
        return RefreshStateRow(
            id=_as_int(row["id"]),
            last_success_at=_as_str_opt(row["last_success_at"]),
            last_attempt_at=_as_str_opt(row["last_attempt_at"]),
            last_status=_as_str_opt(row["last_status"]),
            last_error_code=_as_str_opt(row["last_error_code"]),
            lease_owner=_as_str_opt(row["lease_owner"]),
            lease_expires_at=_as_str_opt(row["lease_expires_at"]),
            backoff_until=_as_str_opt(row["backoff_until"]),
            checkpoint_stage=_as_str_opt(row["checkpoint_stage"]),
            checkpoint_cursor=_as_str_opt(row["checkpoint_cursor"]),
        )

    def acquire_refresh_lease(self, owner: str, expires_at: str, now: str) -> bool:
        self.get_refresh_state()
        existing = self._fetchone(
            """
            SELECT lease_owner, lease_expires_at
            FROM refresh_state
            WHERE id = 1
            """
        )
        if (
            existing is not None
            and existing["lease_owner"] is not None
            and existing["lease_expires_at"] is not None
            and str(existing["lease_expires_at"]) >= now
        ):
            return False
        self._execute(
            """
            UPDATE refresh_state
            SET lease_owner = ?, lease_expires_at = ?
            WHERE id = 1
            """,
            [owner, expires_at],
        )
        self._commit_if_standalone()
        return True

    def release_refresh_lease(self, owner: str) -> None:
        self._execute(
            """
            UPDATE refresh_state
            SET lease_owner = NULL, lease_expires_at = NULL
            WHERE id = 1 AND lease_owner = ?
            """,
            [owner],
        )
        self._commit_if_standalone()

    def renew_refresh_lease(self, owner: str, expires_at: str) -> bool:
        existing = self._fetchone("SELECT lease_owner FROM refresh_state WHERE id = 1")
        if existing is None or existing["lease_owner"] != owner:
            return False
        self._execute(
            """
            UPDATE refresh_state
            SET lease_expires_at = ?
            WHERE id = 1 AND lease_owner = ?
            """,
            [expires_at, owner],
        )
        self._commit_if_standalone()
        return True

    def set_checkpoint(self, stage: str, cursor: str | None) -> None:
        self.get_refresh_state()
        self._execute(
            """
            UPDATE refresh_state
            SET checkpoint_stage = ?, checkpoint_cursor = ?
            WHERE id = 1
            """,
            [stage, cursor],
        )
        self._commit_if_standalone()

    def record_refresh_attempt(self, at: str) -> None:
        self.get_refresh_state()
        self._execute("UPDATE refresh_state SET last_attempt_at = ? WHERE id = 1", [at])
        self._commit_if_standalone()

    def record_refresh_success(self, at: str) -> None:
        self.get_refresh_state()
        self._execute(
            """
            UPDATE refresh_state
            SET last_success_at = ?, last_attempt_at = ?, last_status = 'ok',
                last_error_code = NULL, backoff_until = NULL
            WHERE id = 1
            """,
            [at, at],
        )
        self._commit_if_standalone()

    def record_refresh_failure(self, at: str, reason_code: str, backoff_until: str | None) -> None:
        if reason_code not in ALLOWED_REASON_CODES:
            raise ValueError(f"Unknown refresh failure reason: {reason_code}")
        self.get_refresh_state()
        self._execute(
            """
            UPDATE refresh_state
            SET last_attempt_at = ?, last_status = 'failed',
                last_error_code = ?, backoff_until = ?
            WHERE id = 1
            """,
            [at, reason_code, backoff_until],
        )
        self._commit_if_standalone()

    def enqueue_refresh_request(self, reason: str, requested_for_day: str, requested_at: str | None = None) -> bool:
        timestamp = requested_at or requested_for_day
        existing = self._fetchone(
            """
            SELECT id
            FROM refresh_requests
            WHERE reason = ? AND requested_for_day = ? AND consumed_at IS NULL
            LIMIT 1
            """,
            [reason, requested_for_day],
        )
        if existing is not None:
            return False
        self._execute(
            """
            INSERT INTO refresh_requests (id, reason, requested_for_day, requested_at)
            VALUES (?, ?, ?, ?)
            """,
            [self._next_id("refresh_requests"), reason, requested_for_day, timestamp],
        )
        self._commit_if_standalone()
        return True

    def pending_refresh_requests(self) -> list[RefreshRequestRow]:
        rows = self._fetchall(
            """
            SELECT id, reason, requested_for_day, requested_at, consumed_at
            FROM refresh_requests
            WHERE consumed_at IS NULL
            ORDER BY id
            """
        )
        return [
            RefreshRequestRow(
                id=_as_int(row["id"]),
                reason=str(row["reason"]),
                requested_for_day=str(row["requested_for_day"]),
                requested_at=str(row["requested_at"]),
                consumed_at=_as_str_opt(row["consumed_at"]),
            )
            for row in rows
        ]

    def mark_refresh_requests_consumed(self, consumed_at: str) -> int:
        pending = self.pending_refresh_requests()
        self._execute(
            "UPDATE refresh_requests SET consumed_at = ? WHERE consumed_at IS NULL",
            [consumed_at],
        )
        self._commit_if_standalone()
        return len(pending)

    def get_last_full_summary_sync_at(self) -> str | None:
        self.get_refresh_state()  # ensure row exists
        row = self._fetchone(
            "SELECT last_full_summary_sync_at FROM refresh_state WHERE id = 1"
        )
        if row is None:
            return None
        return _as_str_opt(row["last_full_summary_sync_at"])

    def set_last_full_summary_sync_at(self, at: str) -> None:
        self.get_refresh_state()  # ensure row exists
        self._execute(
            "UPDATE refresh_state SET last_full_summary_sync_at = ? WHERE id = 1",
            [at],
        )
        self._commit_if_standalone()
