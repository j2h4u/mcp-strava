"""Reclaim disk space in the DuckDB mirror by rewriting it into a fresh file.

DuckDB never shrinks its single storage file in place: ``CHECKPOINT`` only
merges heavily-deleted row groups and the file keeps its high-water mark. The
supported way to reclaim space is to copy the whole database into a new file
(``COPY FROM DATABASE``) and swap it in. See
https://duckdb.org/docs/current/operations_manual/footprint_of_duckdb/reclaiming_space

This is a local admin operation that requires exclusive access to the mirror
file, so it must run against a stopped owner — the ``just admin`` wrapper
provides that. If the owner still holds the lock, ``MirrorDbLockedError`` is raised.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from mcp_strava.adapters.duckdb.connection import MirrorDbLockedError

_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")
_BYTES_PER_KIB = 1024  # IEC binary unit step for human-readable byte scaling


def humanize_bytes(num: int) -> str:
    """Render a byte count with a unit scaled to its magnitude (1024-based).

    Matches what ``du -h`` / ``ls -lh`` show, e.g. 0 -> "0 B", 102_400 ->
    "100.0 KB", 765_000_000 -> "729.6 MB". Negative inputs keep their sign.
    """
    sign = "-" if num < 0 else ""
    value = float(abs(num))
    for unit in _SIZE_UNITS:
        if value < _BYTES_PER_KIB or unit == _SIZE_UNITS[-1]:
            if unit == "B":
                return f"{sign}{int(value)} {unit}"
            return f"{sign}{value:.1f} {unit}"
        value /= _BYTES_PER_KIB
    raise AssertionError("unreachable")  # pragma: no cover


COMPACT_RECOMMEND_PCT = 25.0
"""Reclaimable share at or above which compaction is worth running. Mirrors
DuckDB's own ~25% row-group merge heuristic."""


def storage_stats(conn) -> dict:
    """Report how much of the mirror file is reclaimable dead space.

    DuckDB keeps freed blocks inside the file (it never shrinks in place), so the
    gap between allocated and used blocks is what `admin compact` would reclaim.
    Reads `PRAGMA database_size` on an open connection — only the owner process
    can read this while the file is served, so it is emitted from there.

    Returns plainly-named fields plus a human-readable ``message``.
    """
    row = conn.execute("PRAGMA database_size").fetchone()
    columns = [d[0] for d in conn.description]
    raw = dict(zip(columns, row, strict=False))
    block_size = int(raw["block_size"])
    total_blocks = int(raw["total_blocks"])
    free_blocks = int(raw["free_blocks"])

    file_size = total_blocks * block_size
    reclaimable = free_blocks * block_size
    reclaimable_pct = round(free_blocks / total_blocks * 100, 1) if total_blocks else 0.0
    recommended = reclaimable_pct >= COMPACT_RECOMMEND_PCT

    advice = "consider running `just admin compact`" if recommended else "compaction not needed"
    message = (
        f"Mirror file {humanize_bytes(file_size)}, "
        f"{reclaimable_pct}% reclaimable ({humanize_bytes(reclaimable)}) — {advice}."
    )
    return {
        "file_size": humanize_bytes(file_size),
        "reclaimable": humanize_bytes(reclaimable),
        "reclaimable_pct": reclaimable_pct,
        "compaction_recommended": recommended,
        # Raw block counts for diagnosis/charting (free_blocks = reclaimable dead space).
        "free_blocks": free_blocks,
        "total_blocks": total_blocks,
        "message": message,
    }


def _sql_path(path: Path) -> str:
    """Render a path as a single-quoted SQL string literal."""
    return str(path).replace("'", "''")


def _wal_sidecar(db_path: Path) -> Path:
    return db_path.with_name(db_path.name + ".wal")


def compact_database(db_path: str | Path, *, backup: bool = True) -> dict:
    """Compact the DuckDB mirror at ``db_path`` and swap it in atomically.

    Copies the live database into a fresh file via ``COPY FROM DATABASE``, then
    replaces the original with ``os.replace`` (atomic on the same filesystem).
    When ``backup`` is true, a timestamped pre-compact copy is kept alongside.

    Returns a dict with byte sizes, reclaimed bytes, and the backup path.
    Raises ``MirrorDbLockedError`` if another process holds the writer lock.
    """
    source = Path(db_path)
    if not source.exists():
        raise RuntimeError(f"Expected DuckDB mirror does not exist: {source}")

    size_before = source.stat().st_size
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = source.with_name(f"{source.stem}.compact-{timestamp}.duckdb")

    coordinator = duckdb.connect()  # in-memory; just drives the copy
    try:
        try:
            coordinator.execute(f"ATTACH '{_sql_path(source)}' AS source_db (READ_ONLY)")
            coordinator.execute(f"ATTACH '{_sql_path(target)}' AS target_db")
            coordinator.execute("COPY FROM DATABASE source_db TO target_db")
            coordinator.execute("DETACH target_db")
            coordinator.execute("DETACH source_db")
        except duckdb.IOException as exc:
            target.unlink(missing_ok=True)
            _wal_sidecar(target).unlink(missing_ok=True)
            if "Conflicting lock" in str(exc):
                raise MirrorDbLockedError(f"DuckDB mirror is locked by another process: {source}") from exc
            raise
    finally:
        coordinator.close()

    backup_path: Path | None = None
    if backup:
        backup_path = source.with_name(f"{source.stem}.pre-compact-{timestamp}.duckdb")
        shutil.copy2(source, backup_path)

    # Atomic swap. A stale WAL beside the old file would be replayed against the
    # new content on next open, so drop it after the replace.
    target.replace(source)
    _wal_sidecar(source).unlink(missing_ok=True)

    size_after = source.stat().st_size
    reclaimed = size_before - size_after
    return {
        "status": "ok",
        "db_path": str(source),
        "size_before": humanize_bytes(size_before),
        "size_after": humanize_bytes(size_after),
        "reclaimed": humanize_bytes(reclaimed),
        "backup_path": str(backup_path) if backup_path is not None else None,
    }
