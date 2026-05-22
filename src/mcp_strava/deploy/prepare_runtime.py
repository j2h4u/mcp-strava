"""Prepare canonical live runtime state under /opt/docker/mcp-strava.

After live cutover, `/opt/docker/mcp-strava/data/strava.db` is canonical for
the MCP container and live refresh/admin CLI operations. Repository
`data/strava.db` is only a development snapshot unless commands point to it
explicitly.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from mcp_strava.adapters.sqlite.backup import create_timestamped_backup
from mcp_strava.deploy.preflight import validate_runtime_db

LIVE_TARGET_ROOT = Path("/opt/docker/mcp-strava")


def _write_live_env(target_root: Path) -> Path:
    live_env_path = target_root / "live.env"
    lines = [
        f"MCP_STRAVA_DB_PATH={target_root / 'data' / 'strava.db'}",
        f"MCP_STRAVA_TOKEN_PATH={target_root / '.env'}",
        "",
    ]
    live_env_path.write_text("\n".join(lines), encoding="utf-8")
    try:
        live_env_path.chmod(0o600)
    except OSError:
        pass
    return live_env_path


def prepare_runtime(
    source_db: Path,
    target_root: Path = LIVE_TARGET_ROOT,
    *,
    copy_env: bool = False,
    source_env: Path | None = None,
    replace_env: bool = False,
) -> dict[str, str]:
    source_db = source_db.resolve()
    target_root = target_root.resolve()
    data_dir = target_root / "data"
    target_db = (data_dir / "strava.db").resolve()

    if source_db == target_db:
        raise RuntimeError("Source DB and target DB must differ")
    validate_runtime_db(source_db, quick=False)

    data_dir.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if target_db.exists():
        backup_path = create_timestamped_backup(target_db, backups_dir=data_dir / "backups")

    shutil.copy2(source_db, target_db)
    try:
        target_db.chmod(0o600)
    except OSError:
        pass
    validate_runtime_db(target_db, quick=False)

    live_env_path = _write_live_env(target_root)

    copied_env_path: Path | None = None
    if copy_env:
        env_src = source_env.resolve() if source_env else Path(".env").resolve()
        if not env_src.exists():
            raise RuntimeError(f"Source env does not exist: {env_src}")
        env_dst = target_root / ".env"
        if env_dst.exists() and not replace_env:
            raise RuntimeError(f"Target env already exists; use replace flag: {env_dst}")
        shutil.copy2(env_src, env_dst)
        try:
            env_dst.chmod(0o600)
        except OSError:
            pass
        copied_env_path = env_dst

    result = {
        "source_db": str(source_db),
        "target_db": str(target_db),
        "live_env": str(live_env_path),
    }
    if backup_path is not None:
        result["backup_db"] = str(backup_path)
    if copied_env_path is not None:
        result["target_env"] = str(copied_env_path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare runtime DB/env state for Docker deployment.")
    parser.add_argument("--source-db", required=True, help="Source mirror DB path")
    parser.add_argument("--target-root", default=str(LIVE_TARGET_ROOT), help="Target runtime root")
    parser.add_argument("--copy-env", action="store_true", help="Copy env file to target root")
    parser.add_argument("--source-env", default=None, help="Source env path")
    parser.add_argument("--replace-env", action="store_true", help="Overwrite existing target .env")
    args = parser.parse_args(argv)

    try:
        result = prepare_runtime(
            source_db=Path(args.source_db),
            target_root=Path(args.target_root),
            copy_env=args.copy_env,
            source_env=Path(args.source_env) if args.source_env else None,
            replace_env=args.replace_env,
        )
    except Exception as exc:
        print(f"prepare-runtime failed: {exc}")
        return 1

    print(f"runtime prepared: target_db={result['target_db']} live_env={result['live_env']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

