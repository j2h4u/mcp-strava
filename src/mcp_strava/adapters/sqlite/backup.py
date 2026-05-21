"""SQLite backup and retention helpers."""

from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3


BACKUP_RETENTION_DEFAULT = 5


def _backup_filename() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"strava-{stamp}.db"


def create_timestamped_backup(
    source_db: str | Path,
    backups_dir: str | Path | None = None,
) -> Path:
    src = Path(source_db)
    target_dir = Path(backups_dir) if backups_dir else (src.parent / "backups")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _backup_filename()

    src_conn = sqlite3.connect(str(src), check_same_thread=False)
    dst_conn = sqlite3.connect(str(target), check_same_thread=False)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    if not target.exists() or target.stat().st_size <= 0:
        raise RuntimeError(f"Backup failed or empty: {target}")

    with sqlite3.connect(str(target)) as verify_conn:
        row = verify_conn.execute("PRAGMA integrity_check").fetchone()
    if not row or str(row[0]).lower() != "ok":
        detail = row[0] if row else "unknown"
        raise RuntimeError(f"Backup integrity check failed for {target}: {detail}")

    try:
        os.chmod(target, 0o600)
    except OSError:
        pass

    enforce_backup_retention(target_dir, keep=BACKUP_RETENTION_DEFAULT)
    return target


def enforce_backup_retention(backups_dir: str | Path, keep: int = BACKUP_RETENTION_DEFAULT) -> list[Path]:
    if keep <= 0:
        raise ValueError("keep must be > 0")
    root = Path(backups_dir)
    files = sorted(root.glob("strava-*.db"), key=lambda p: p.name)
    if len(files) > keep:
        for stale in files[: len(files) - keep]:
            stale.unlink(missing_ok=True)
    return sorted(root.glob("strava-*.db"), key=lambda p: p.name)
