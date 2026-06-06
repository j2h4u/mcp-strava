from __future__ import annotations

import argparse
import datetime as dt
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import yaml

DEFAULT_CATALOG = Path("/opt/docker/mcp-gateway/catalog.yaml")
DEFAULT_COMPOSE = Path("/opt/docker/mcp-gateway/compose.yaml")
DEFAULT_SERVICE_NAME = "strava"
DEFAULT_SERVICE_URL = "http://mcp-strava:8080/mcp"
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_ROLLBACK_RESTART_FAILED = 42


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected mapping YAML at {path}")
    return data


def dump_yaml(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False)


def _timestamp() -> str:
    return dt.datetime.now(tz=dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def backup_files(catalog_path: Path, compose_path: Path, backup_dir: Path) -> tuple[Path, Path]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    catalog_backup = backup_dir / f"{catalog_path.name}.{stamp}.bak"
    compose_backup = backup_dir / f"{compose_path.name}.{stamp}.bak"
    catalog_backup.write_bytes(catalog_path.read_bytes())
    compose_backup.write_bytes(compose_path.read_bytes())
    return catalog_backup, compose_backup


def atomic_write_text(path: Path, content: str) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp.{_timestamp()}")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def append_server_to_command(command: str | list[str], service_name: str) -> str | list[str]:
    def _append_servers(raw: str) -> str:
        items = [item.strip() for item in raw.split(",") if item.strip()]
        if service_name not in items:
            items.append(service_name)
        return "--servers=" + ",".join(items)

    if isinstance(command, list):
        out = list(command)
        for idx, token in enumerate(out):
            if isinstance(token, str) and token.startswith("--servers="):
                out[idx] = _append_servers(token.removeprefix("--servers="))
                return out
        out.append(f"--servers={service_name}")
        return out

    if isinstance(command, str):
        tokens = shlex.split(command)
        replaced = False
        for idx, token in enumerate(tokens):
            if token.startswith("--servers="):
                tokens[idx] = _append_servers(token.removeprefix("--servers="))
                replaced = True
                break
        if not replaced:
            tokens.append(f"--servers={service_name}")
        return shlex.join(tokens)

    raise RuntimeError("mcp-gateway command must be a string or list")


def restart_gateway(restart_cmd: list[str], run_cmd: Callable[[list[str]], int]) -> int:
    return run_cmd(restart_cmd)


def rollback(
    catalog_path: Path,
    compose_path: Path,
    catalog_backup: Path,
    compose_backup: Path,
    rollback_restart_cmd: list[str],
    run_cmd: Callable[[list[str]], int],
) -> int:
    catalog_path.write_bytes(catalog_backup.read_bytes())
    compose_path.write_bytes(compose_backup.read_bytes())
    return run_cmd(rollback_restart_cmd)


def _is_live_target(path: Path) -> bool:
    target = str(path.resolve())
    return target.startswith("/opt/docker/mcp-gateway/")


def _run_subprocess(cmd: list[str]) -> int:
    return subprocess.run(cmd, check=False).returncode


def _build_mutations(
    catalog_obj: dict,
    compose_obj: dict,
    *,
    service_name: str,
    service_url: str,
) -> tuple[str, str]:
    updated_catalog = dict(catalog_obj)
    registry = dict(updated_catalog.get("registry") or {})
    registry[service_name] = {
        "remote": {
            "url": service_url,
            "transport_type": "http",
        }
    }
    updated_catalog["registry"] = registry

    updated_compose = dict(compose_obj)
    services = dict(updated_compose.get("services") or {})
    if "mcp-gateway" not in services:
        raise RuntimeError("compose.yaml missing services.mcp-gateway")
    gateway_service = dict(services["mcp-gateway"])
    command = gateway_service.get("command")
    if command is None:
        raise RuntimeError("compose.yaml missing services.mcp-gateway.command")
    gateway_service["command"] = append_server_to_command(command, service_name)
    services["mcp-gateway"] = gateway_service
    updated_compose["services"] = services
    return dump_yaml(updated_catalog), dump_yaml(updated_compose)


def register_strava_gateway(
    catalog_path: Path = DEFAULT_CATALOG,
    compose_path: Path = DEFAULT_COMPOSE,
    *,
    service_name: str = DEFAULT_SERVICE_NAME,
    service_url: str = DEFAULT_SERVICE_URL,
    restart_cmd: list[str] | None = None,
    rollback_restart_cmd: list[str] | None = None,
    compose_config_cmd: list[str] | None = None,
    backup_dir: Path | None = None,
    apply: bool = False,
    confirm_live_gateway: bool = False,
    run_cmd: Callable[[list[str]], int] = _run_subprocess,
    atomic_write_fn: Callable[[Path, str], None] = atomic_write_text,
) -> int:
    if not catalog_path.exists() or not compose_path.exists():
        print("gateway files missing", file=sys.stderr)
        return EXIT_FAILED

    live_target = _is_live_target(catalog_path) or _is_live_target(compose_path)
    if live_target and apply and not confirm_live_gateway:
        print("live gateway mutation requires --apply and --confirm-live-gateway", file=sys.stderr)
        return EXIT_FAILED

    compose_config_cmd = compose_config_cmd or [
        "docker",
        "compose",
        "--env-file",
        "/opt/docker/mcp-gateway/.env",
        "-f",
        str(compose_path),
        "config",
    ]
    restart_cmd = restart_cmd or [
        "docker",
        "compose",
        "--env-file",
        "/opt/docker/mcp-gateway/.env",
        "-f",
        str(compose_path),
        "up",
        "-d",
        "--force-recreate",
        "mcp-gateway",
    ]
    rollback_restart_cmd = rollback_restart_cmd or restart_cmd
    backup_dir = backup_dir or (catalog_path.parent / "backups")

    catalog_obj = load_yaml(catalog_path)
    compose_obj = load_yaml(compose_path)
    next_catalog_text, next_compose_text = _build_mutations(
        catalog_obj,
        compose_obj,
        service_name=service_name,
        service_url=service_url,
    )
    next_catalog_obj = yaml.safe_load(next_catalog_text) or {}
    next_compose_obj = yaml.safe_load(next_compose_text) or {}
    if next_catalog_obj == catalog_obj and next_compose_obj == compose_obj:
        return EXIT_OK

    if not apply:
        print("dry-run: planned catalog/compose mutation prepared")
        return EXIT_OK

    if run_cmd(compose_config_cmd) != 0:
        print("compose prevalidation failed", file=sys.stderr)
        return EXIT_FAILED

    catalog_backup, compose_backup = backup_files(catalog_path, compose_path, backup_dir)
    try:
        atomic_write_fn(catalog_path, next_catalog_text)
        atomic_write_fn(compose_path, next_compose_text)
        if run_cmd(compose_config_cmd) != 0:
            raise RuntimeError("compose validation failed after write")
        if restart_gateway(restart_cmd, run_cmd) != 0:
            raise RuntimeError("gateway restart failed")
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001 - mutation boundary must rollback on any write/validation/restart failure.
        print(f"gateway mutation failed: {exc}", file=sys.stderr)
        restart_rc = rollback(
            catalog_path,
            compose_path,
            catalog_backup,
            compose_backup,
            rollback_restart_cmd,
            run_cmd,
        )
        if restart_rc != 0:
            print(
                f"rollback restart failed; manual recovery required from backups {catalog_backup} and {compose_backup}",
                file=sys.stderr,
            )
            return EXIT_ROLLBACK_RESTART_FAILED
        return EXIT_FAILED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register mcp-strava into docker mcp-gateway")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--service", default=DEFAULT_SERVICE_NAME)
    parser.add_argument("--url", default=DEFAULT_SERVICE_URL)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-live-gateway", action="store_true")
    args = parser.parse_args(argv)

    return register_strava_gateway(
        catalog_path=args.catalog,
        compose_path=args.compose,
        service_name=args.service,
        service_url=args.url,
        backup_dir=args.backup_dir,
        apply=args.apply,
        confirm_live_gateway=args.confirm_live_gateway,
    )


if __name__ == "__main__":
    raise SystemExit(main())
