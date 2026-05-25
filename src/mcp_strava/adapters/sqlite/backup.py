"""SQLite backup and retention helpers."""

from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3


BACKUP_RETENTION_DEFAULT = 5


def _backup_filename(label: str | None = None) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if label:
        return f"strava-{label}-{stamp}.db"
    return f"strava-{stamp}.db"


def _unique_backup_path(target_dir: Path, label: str | None = None) -> Path:
    target = target_dir / _backup_filename(label)
    if not target.exists():
        return target
    stem = target.stem
    for suffix in range(1, 1000):
        candidate = target.with_name(f"{stem}-{suffix}.db")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate unique backup filename in {target_dir}")


def _is_pinned_backup(path: Path) -> bool:
    return path.name.startswith("strava-pre-phase-")


def create_timestamped_backup(
    source_db: str | Path,
    backups_dir: str | Path | None = None,
) -> Path:
    return _create_backup(source_db, backups_dir=backups_dir)


def create_pre_phase_7_backup(
    source_db: str | Path,
    backups_dir: str | Path | None = None,
) -> Path:
    """Create the pinned backup that protects the pre-Phase-7 mirror state."""
    return _create_backup(source_db, backups_dir=backups_dir, label="pre-phase-7")


def create_pre_phase_8_backup(
    source_db: str | Path,
    backups_dir: str | Path | None = None,
) -> Path:
    """Create the pinned backup that protects the pre-Phase-8 SQLite mirror."""
    return _create_backup(source_db, backups_dir=backups_dir, label="pre-phase-8")


def _create_backup(
    source_db: str | Path,
    backups_dir: str | Path | None = None,
    *,
    label: str | None = None,
) -> Path:
    src = Path(source_db)
    target_dir = Path(backups_dir) if backups_dir else (src.parent / "backups")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_backup_path(target_dir, label)

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
    regular = [path for path in files if not _is_pinned_backup(path)]
    if len(regular) > keep:
        for stale in regular[: len(regular) - keep]:
            stale.unlink(missing_ok=True)
    return sorted(root.glob("strava-*.db"), key=lambda p: p.name)
