from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from deploy import gateway_register


CATALOG_FIXTURE = """registry:
  dotmd:
    remote:
      url: "http://dotmd:8080/mcp"
      transport_type: http
  ozon:
    remote:
      url: "http://ozon-mcp-server:3001/mcp"
      transport_type: http
  telegram:
    remote:
      url: "http://mcp-telegram:3100/mcp/"
      transport_type: http
  beads:
    remote:
      url: "http://host.docker.internal:3200/mcp/"
      transport_type: http
"""


COMPOSE_LIST_FIXTURE = """services:
  mcp-gateway:
    command:
      - --catalog=/mcp/catalog.yaml
      - --servers=ozon,telegram,beads,dotmd
      - --transport=streaming
      - --port=8811
"""


COMPOSE_STRING_FIXTURE = """services:
  mcp-gateway:
    command: "--catalog=/mcp/catalog.yaml --servers=ozon,telegram,beads,dotmd --transport=streaming"
"""


def _write_fixture(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _read_yaml(path: Path) -> dict:
    return gateway_register.load_yaml(path)


def test_apply_updates_catalog_and_compose_with_backups_and_restart(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    compose = tmp_path / "compose.yaml"
    _write_fixture(catalog, CATALOG_FIXTURE)
    _write_fixture(compose, COMPOSE_LIST_FIXTURE)
    backup_dir = tmp_path / "backups"

    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    rc = gateway_register.register_strava_gateway(
        catalog_path=catalog,
        compose_path=compose,
        smoke_cmd=["echo", "smoke"],
        restart_cmd=["echo", "restart"],
        rollback_restart_cmd=["echo", "rollback-restart"],
        compose_config_cmd=["echo", "config-ok"],
        backup_dir=backup_dir,
        apply=True,
        confirm_live_gateway=True,
        run_cmd=fake_run,
    )
    assert rc == 0

    backups = list(backup_dir.glob("*.bak"))
    assert len(backups) == 2

    updated_catalog = _read_yaml(catalog)
    assert updated_catalog["registry"]["strava"]["remote"]["url"] == "http://mcp-strava:8080/mcp"
    assert updated_catalog["registry"]["strava"]["remote"]["transport_type"] == "http"

    updated_compose = _read_yaml(compose)
    servers_arg = updated_compose["services"]["mcp-gateway"]["command"][1]
    assert "--servers=ozon,telegram,beads,dotmd,strava" == servers_arg
    assert calls == [
        ["echo", "config-ok"],
        ["echo", "config-ok"],
        ["echo", "restart"],
        ["echo", "smoke"],
    ]


def test_supports_string_command_and_preserves_existing_servers(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    compose = tmp_path / "compose.yaml"
    _write_fixture(catalog, CATALOG_FIXTURE)
    _write_fixture(compose, COMPOSE_STRING_FIXTURE)

    rc = gateway_register.register_strava_gateway(
        catalog_path=catalog,
        compose_path=compose,
        backup_dir=tmp_path / "backups",
        smoke_cmd=["echo", "smoke"],
        restart_cmd=["echo", "restart"],
        rollback_restart_cmd=["echo", "rollback-restart"],
        compose_config_cmd=["echo", "config-ok"],
        apply=True,
        confirm_live_gateway=True,
        run_cmd=lambda _cmd: 0,
    )
    assert rc == 0
    updated_compose = _read_yaml(compose)
    command = updated_compose["services"]["mcp-gateway"]["command"]
    assert isinstance(command, str)
    assert "--servers=ozon,telegram,beads,dotmd,strava" in command


def test_idempotent_when_strava_already_present(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    compose = tmp_path / "compose.yaml"
    _write_fixture(
        catalog,
        CATALOG_FIXTURE
        + """
  strava:
    remote:
      url: "http://mcp-strava:8080/mcp"
      transport_type: http
""",
    )
    _write_fixture(
        compose,
        """services:
  mcp-gateway:
    command:
      - --catalog=/mcp/catalog.yaml
      - --servers=ozon,telegram,beads,dotmd,strava
""",
    )
    before_catalog = catalog.read_bytes()
    before_compose = compose.read_bytes()

    rc = gateway_register.register_strava_gateway(
        catalog_path=catalog,
        compose_path=compose,
        backup_dir=tmp_path / "backups",
        smoke_cmd=["echo", "smoke"],
        restart_cmd=["echo", "restart"],
        rollback_restart_cmd=["echo", "rollback-restart"],
        compose_config_cmd=["echo", "config-ok"],
        apply=True,
        confirm_live_gateway=True,
        run_cmd=lambda _cmd: 0,
    )
    assert rc == 0
    assert catalog.read_bytes() == before_catalog
    assert compose.read_bytes() == before_compose


def test_default_is_dry_run_and_no_writes_no_backups_no_restart(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    compose = tmp_path / "compose.yaml"
    _write_fixture(catalog, CATALOG_FIXTURE)
    _write_fixture(compose, COMPOSE_LIST_FIXTURE)
    before_catalog = catalog.read_bytes()
    before_compose = compose.read_bytes()
    backup_dir = tmp_path / "backups"
    calls: list[list[str]] = []

    rc = gateway_register.register_strava_gateway(
        catalog_path=catalog,
        compose_path=compose,
        backup_dir=backup_dir,
        smoke_cmd=["echo", "smoke"],
        restart_cmd=["echo", "restart"],
        rollback_restart_cmd=["echo", "rollback-restart"],
        compose_config_cmd=["echo", "config-ok"],
        apply=False,
        run_cmd=lambda cmd: calls.append(cmd) or 0,
    )
    assert rc == 0
    assert catalog.read_bytes() == before_catalog
    assert compose.read_bytes() == before_compose
    assert not backup_dir.exists()
    assert calls == []


def test_live_paths_require_apply_and_confirm_flags(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    compose = tmp_path / "compose.yaml"
    _write_fixture(catalog, CATALOG_FIXTURE)
    _write_fixture(compose, COMPOSE_LIST_FIXTURE)
    live_catalog = Path("/opt/docker/mcp-gateway/catalog.yaml")
    live_compose = Path("/opt/docker/mcp-gateway/compose.yaml")

    rc_default = gateway_register.main(
        [
            "--catalog",
            str(live_catalog),
            "--compose",
            str(live_compose),
        ]
    )
    assert rc_default == 0

    rc_apply_only = gateway_register.main(
        [
            "--apply",
            "--catalog",
            str(live_catalog),
            "--compose",
            str(live_compose),
        ]
    )
    assert rc_apply_only != 0


def test_prevalidation_failure_writes_nothing(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    compose = tmp_path / "compose.yaml"
    _write_fixture(catalog, CATALOG_FIXTURE)
    _write_fixture(compose, COMPOSE_LIST_FIXTURE)
    before_catalog = catalog.read_bytes()
    before_compose = compose.read_bytes()

    rc = gateway_register.register_strava_gateway(
        catalog_path=catalog,
        compose_path=compose,
        backup_dir=tmp_path / "backups",
        smoke_cmd=["echo", "smoke"],
        restart_cmd=["echo", "restart"],
        rollback_restart_cmd=["echo", "rollback-restart"],
        compose_config_cmd=["echo", "config-fail"],
        apply=True,
        confirm_live_gateway=True,
        run_cmd=lambda _cmd: 2,
    )
    assert rc != 0
    assert catalog.read_bytes() == before_catalog
    assert compose.read_bytes() == before_compose


def test_mid_write_crash_restores_both_files_and_runs_rollback_restart(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    compose = tmp_path / "compose.yaml"
    _write_fixture(catalog, CATALOG_FIXTURE)
    _write_fixture(compose, COMPOSE_LIST_FIXTURE)
    before_catalog = catalog.read_bytes()
    before_compose = compose.read_bytes()
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    def crash_after_catalog(_path: Path, _content: str) -> None:
        if _path == catalog:
            shutil.copyfile(_path, _path)
            raise RuntimeError("boom-after-catalog")
        raise AssertionError("compose write should not happen when injected crash triggers")

    rc = gateway_register.register_strava_gateway(
        catalog_path=catalog,
        compose_path=compose,
        backup_dir=tmp_path / "backups",
        smoke_cmd=["echo", "smoke"],
        restart_cmd=["echo", "restart"],
        rollback_restart_cmd=["echo", "rollback-restart"],
        compose_config_cmd=["echo", "config-ok"],
        apply=True,
        confirm_live_gateway=True,
        run_cmd=fake_run,
        atomic_write_fn=crash_after_catalog,
    )
    assert rc != 0
    assert catalog.read_bytes() == before_catalog
    assert compose.read_bytes() == before_compose
    assert ["echo", "rollback-restart"] in calls


def test_smoke_failure_restores_both_files_and_runs_rollback_restart(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    compose = tmp_path / "compose.yaml"
    _write_fixture(catalog, CATALOG_FIXTURE)
    _write_fixture(compose, COMPOSE_LIST_FIXTURE)
    before_catalog = catalog.read_bytes()
    before_compose = compose.read_bytes()
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> int:
        calls.append(cmd)
        if cmd == ["echo", "smoke"]:
            return 3
        return 0

    rc = gateway_register.register_strava_gateway(
        catalog_path=catalog,
        compose_path=compose,
        backup_dir=tmp_path / "backups",
        smoke_cmd=["echo", "smoke"],
        restart_cmd=["echo", "restart"],
        rollback_restart_cmd=["echo", "rollback-restart"],
        compose_config_cmd=["echo", "config-ok"],
        apply=True,
        confirm_live_gateway=True,
        run_cmd=fake_run,
    )
    assert rc != 0
    assert catalog.read_bytes() == before_catalog
    assert compose.read_bytes() == before_compose
    assert calls[-1] == ["echo", "rollback-restart"]


def test_rollback_restart_failure_returns_distinct_code(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    compose = tmp_path / "compose.yaml"
    _write_fixture(catalog, CATALOG_FIXTURE)
    _write_fixture(compose, COMPOSE_LIST_FIXTURE)

    def fake_run(cmd: list[str]) -> int:
        if cmd == ["echo", "smoke"]:
            return 5
        if cmd == ["echo", "rollback-restart"]:
            return 7
        return 0

    rc = gateway_register.register_strava_gateway(
        catalog_path=catalog,
        compose_path=compose,
        backup_dir=tmp_path / "backups",
        smoke_cmd=["echo", "smoke"],
        restart_cmd=["echo", "restart"],
        rollback_restart_cmd=["echo", "rollback-restart"],
        compose_config_cmd=["echo", "config-ok"],
        apply=True,
        confirm_live_gateway=True,
        run_cmd=fake_run,
    )
    assert rc == gateway_register.EXIT_ROLLBACK_RESTART_FAILED


def test_missing_target_files_fail_before_writes(tmp_path: Path) -> None:
    rc = gateway_register.register_strava_gateway(
        catalog_path=tmp_path / "missing-catalog.yaml",
        compose_path=tmp_path / "missing-compose.yaml",
        apply=True,
        confirm_live_gateway=True,
    )
    assert rc != 0


def test_smoke_client_uses_sdk_and_not_raw_jsonrpc() -> None:
    smoke_path = Path("src/mcp_strava/deploy/smoke.py")
    text = smoke_path.read_text(encoding="utf-8")
    assert "mcp.client.streamable_http" in text
    assert "jsonrpc" not in text.lower()
