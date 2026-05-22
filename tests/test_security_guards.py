import os
import subprocess
import sys
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=False,
        text=True,
        capture_output=True,
    )


def test_local_state_paths_are_gitignored_and_untracked() -> None:
    protected_paths = [".env", ".planning/config.json", "data/strava.db"]

    for path in protected_paths:
        assert _git("check-ignore", path).returncode == 0, f"{path} must stay gitignored"
        tracked = _git("ls-files", "--error-unmatch", path)
        assert tracked.returncode != 0, f"{path} must not be tracked"


def test_existing_local_mirror_db_is_preserved_when_present() -> None:
    db_path = Path("data/strava.db")
    if not db_path.exists():
        return

    before = db_path.stat()
    assert before.st_size > 0

    after = db_path.stat()
    assert after.st_ino == before.st_ino
    assert after.st_size == before.st_size


def test_module_entrypoint_runs_from_source_tree_with_pythonpath() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        [sys.executable, "-m", "mcp_strava"],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )

    combined_output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "Usage:" in combined_output


def _source_text(rel_path: str) -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / rel_path).read_text(encoding="utf-8")


def _assert_no_schema_ddl_in_init_db() -> list[str]:
    violations: list[str] = []
    source = _source_text("src/mcp_strava/db.py")
    module = ast.parse(source)
    targets = {"create table", "create index", "alter table"}
    for node in module.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "init_db":
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                lowered = " ".join(child.value.lower().split())
                if any(target in lowered for target in targets):
                    violations.append(f"db.py:{child.lineno}")
    return violations


def _direct_sqlite_violations() -> list[str]:
    root = Path(__file__).resolve().parents[1]
    src_root = root / "src" / "mcp_strava"
    violations: list[str] = []
    allow_prefixes = ("src/mcp_strava/adapters/sqlite/",)
    allow_exact = {
        "src/mcp_strava/db.py",
    }
    for py_file in src_root.rglob("*.py"):
        rel = py_file.relative_to(root).as_posix()
        if rel.startswith(allow_prefixes) or rel in allow_exact:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for imported in node.names:
                    if imported.name == "sqlite3":
                        aliases.add(imported.asname or "sqlite3")
            elif isinstance(node, ast.ImportFrom) and node.module == "sqlite3":
                aliases.add("sqlite3")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    if node.func.value.id in aliases and node.func.attr == "connect":
                        violations.append(f"{rel}:{node.lineno} direct sqlite3.connect")
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id in aliases and node.attr == "Connection":
                    violations.append(f"{rel}:{node.lineno} sqlite3.Connection reference")
    return violations


def _command_registry_names() -> set[str]:
    source = _source_text("src/mcp_strava/cli.py")
    module = ast.parse(source)
    commands: set[str] = set()
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "COMMANDS" for target in node.targets):
            if isinstance(node.value, ast.Dict):
                for key in node.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        commands.add(key.value)
    return commands


def test_cli_has_product_admin_split_and_explicit_db_safety_commands() -> None:
    commands = _command_registry_names()
    assert {"report", "weekly", "workouts", "workout", "freshness", "admin"}.issubset(commands)
    assert {"sql", "db-preflight", "db-check", "db-migrate", "db-refresh"}.isdisjoint(commands)


def test_cli_includes_namespaced_admin_refresh_commands() -> None:
    import mcp_strava.cli as cli

    assert "admin" in _command_registry_names()
    assert "mirror-refresh" in cli.ADMIN_COMMANDS
    assert "token-refresh" in cli.ADMIN_COMMANDS
    assert "sync" not in cli.ADMIN_COMMANDS
    assert "refresh" not in cli.ADMIN_COMMANDS


def test_product_service_registry_excludes_admin_debug_commands() -> None:
    from mcp_strava.application.registry import PRODUCT_SERVICES

    forbidden = {
        "admin",
        "sync",
        "backfill",
        "sql",
        "raw",
        "log",
        "db-refresh",
        "mirror-refresh",
        "token-refresh",
        "db-preflight",
        "db-check",
        "db-migrate",
    }

    assert forbidden.isdisjoint(PRODUCT_SERVICES)


def test_cli_db_refresh_accepts_force_flag_per_D15(monkeypatch, tmp_path: Path) -> None:
    import mcp_strava.cli as cli
    from mcp_strava.refresh.runtime import RefreshResult

    calls: list[dict] = []

    class FakeDbConn:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_run_once(repo, transport, policy, clock, sleeper, **kwargs):
        calls.append(
            {
                "repo": repo,
                "transport": transport,
                "policy": policy,
                "clock": clock,
                "sleeper": sleeper,
                **kwargs,
            }
        )
        return RefreshResult(status="ok", mode=kwargs["mode"], checkpoint_stage="complete")

    monkeypatch.setattr(
        cli,
        "build_refresh_collaborators",
        lambda: (
            SimpleNamespace(database_path=tmp_path / "strava.db"),
            "clock",
            "sleeper",
            "transport",
            "policy",
        ),
    )
    monkeypatch.setattr(
        cli,
        "run_preflight",
        lambda *_args, **_kwargs: SimpleNamespace(row_counts={"refresh_state": 1, "refresh_requests": 0}),
    )
    monkeypatch.setattr(cli, "DbConn", FakeDbConn)
    monkeypatch.setattr(cli.SQLiteRepository, "from_connection", staticmethod(lambda _conn: "repo"))
    monkeypatch.setattr(cli.refresh_runtime, "run_once", fake_run_once)

    cli.cmd_db_refresh(["--force"])

    assert "--force" in _source_text("src/mcp_strava/cli.py")
    assert calls
    assert calls[0]["force"] is True
    assert calls[0]["mode"] == "daily"


def test_cmd_sql_is_not_reused_as_service_or_mcp_surface() -> None:
    violations: list[str] = []
    root = Path(__file__).resolve().parents[1]
    for py_file in (root / "src" / "mcp_strava").rglob("*.py"):
        rel = py_file.relative_to(root).as_posix()
        if rel == "src/mcp_strava/cli.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        if "cmd_sql(" in source or "COMMANDS['sql']" in source or 'COMMANDS["sql"]' in source:
            violations.append(rel)
    assert violations == []


def test_direct_sqlite_access_stays_inside_allowed_boundaries() -> None:
    assert _direct_sqlite_violations() == []


def test_sync_never_calls_init_db_and_db_init_db_has_no_ddl() -> None:
    sync_source = _source_text("src/mcp_strava/sync.py")
    assert "init_db(" not in sync_source
    assert "class RateLimiter" not in sync_source
    assert "def _fetch_with_retry" not in sync_source
    assert _assert_no_schema_ddl_in_init_db() == []


def _import_violations(rel_path: str, disallowed_prefixes: tuple[str, ...]) -> list[str]:
    root = Path(__file__).resolve().parents[1]
    py_file = root / rel_path
    module = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    violations: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(disallowed_prefixes):
                    violations.append(f"{rel_path}:{node.lineno} import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            imported_module = node.module or ""
            if imported_module.startswith(disallowed_prefixes):
                violations.append(f"{rel_path}:{node.lineno} from {imported_module}")
            if imported_module == "mcp_strava":
                for alias in node.names:
                    full_name = f"mcp_strava.{alias.name}"
                    if full_name.startswith(disallowed_prefixes):
                        violations.append(f"{rel_path}:{node.lineno} from mcp_strava import {alias.name}")
    return violations


def test_read_modules_do_not_import_strava_or_refresh() -> None:
    read_modules = [
        "src/mcp_strava/report.py",
        "src/mcp_strava/analytics.py",
        "src/mcp_strava/trends.py",
        "src/mcp_strava/training.py",
        "src/mcp_strava/metrics.py",
        "src/mcp_strava/cardiac_drift.py",
    ]
    violations: list[str] = []
    for rel_path in read_modules:
        violations.extend(
            _import_violations(
                rel_path,
                ("mcp_strava.adapters.strava", "mcp_strava.refresh"),
            )
        )
    assert violations == []


def test_urllib_lives_only_in_strava_adapter() -> None:
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for py_file in (root / "src" / "mcp_strava").rglob("*.py"):
        rel = py_file.relative_to(root).as_posix()
        if rel.startswith("src/mcp_strava/adapters/strava/"):
            continue
        module = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "urllib" or alias.name.startswith("urllib."):
                        violations.append(f"{rel}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                imported_module = node.module or ""
                if imported_module == "urllib" or imported_module.startswith("urllib."):
                    violations.append(f"{rel}:{node.lineno} from {imported_module}")
    assert violations == []


def test_refresh_does_not_import_sync_per_D17() -> None:
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for py_file in (root / "src" / "mcp_strava" / "refresh").rglob("*.py"):
        rel = py_file.relative_to(root).as_posix()
        module = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "mcp_strava.sync" or alias.name.startswith("mcp_strava.sync."):
                        violations.append(f"{rel}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                imported_module = node.module or ""
                if imported_module == "mcp_strava.sync" or imported_module.startswith("mcp_strava.sync."):
                    violations.append(f"{rel}:{node.lineno} from {imported_module}")
                if imported_module == "mcp_strava":
                    for alias in node.names:
                        if alias.name == "sync":
                            violations.append(f"{rel}:{node.lineno} from mcp_strava import sync")
    assert violations == []


def test_application_product_modules_do_not_import_strava_sync_or_admin_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    app_root = root / "src" / "mcp_strava" / "application"
    if not app_root.exists():
        pytest.fail("src/mcp_strava/application must exist for product services")

    disallowed = (
        "mcp_strava.adapters.strava",
        "mcp_strava.sync",
        "mcp_strava.refresh.runtime",
    )
    violations: list[str] = []

    for py_file in app_root.rglob("*.py"):
        rel = py_file.relative_to(root).as_posix()
        module = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(disallowed):
                        violations.append(f"{rel}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                imported_module = node.module or ""
                if imported_module.startswith(disallowed):
                    violations.append(f"{rel}:{node.lineno} from {imported_module}")
                for alias in node.names:
                    full_name = f"{imported_module}.{alias.name}" if imported_module else alias.name
                    if full_name in {
                        "mcp_strava.db.api_request",
                        "mcp_strava.db.refresh_token",
                    }:
                        violations.append(f"{rel}:{node.lineno} from {imported_module} import {alias.name}")

    assert violations == []


def test_metric_services_do_not_import_strava_sync_or_token_refresh() -> None:
    rel_path = "src/mcp_strava/application/metric_services.py"
    violations = _import_violations(
        rel_path,
        (
            "mcp_strava.adapters.strava",
            "mcp_strava.sync",
            "mcp_strava.refresh.runtime",
            "mcp_strava.db.api_request",
            "mcp_strava.db.refresh_token",
        ),
    )
    assert violations == []


def test_mcp_http_interface_does_not_import_admin_sync_or_strava_adapter() -> None:
    rel_path = "src/mcp_strava/interfaces/mcp_http.py"
    violations = _import_violations(
        rel_path,
        (
            "mcp_strava.adapters.strava",
            "mcp_strava.sync",
            "mcp_strava.refresh.runtime",
            "mcp_strava.cli",
        ),
    )
    assert violations == []


def test_sync_does_not_define_moved_helpers_per_D17() -> None:
    source = _source_text("src/mcp_strava/sync.py")
    module = ast.parse(source)
    moved = {
        "_sync_kudos",
        "_insert_streams",
        "_replace_streams",
        "_stream_payload",
        "STREAM_KEYS",
        "_is_iso_day",
        "_safe_quick_sync_start_day",
    }
    defined: set[str] = set()
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
    assert moved.intersection(defined) == set()


def test_sync_activities_quick_invokes_run_once_with_force_true_per_D15(monkeypatch, tmp_path: Path) -> None:
    import mcp_strava.sync as sync
    from mcp_strava.refresh.runtime import RefreshResult

    calls: list[dict] = []

    class FakeDbConn:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_run_once(repo, transport, policy, clock, sleeper, **kwargs):
        calls.append(
            {
                "repo": repo,
                "transport": transport,
                "policy": policy,
                "clock": clock,
                "sleeper": sleeper,
                **kwargs,
            }
        )
        return RefreshResult(status="ok", mode=kwargs["mode"], checkpoint_stage="complete")

    monkeypatch.setattr(sync, "get_settings", lambda: SimpleNamespace(database_path=tmp_path / "strava.db"))
    monkeypatch.setattr(
        sync,
        "run_preflight",
        lambda *_args, **_kwargs: SimpleNamespace(row_counts={"refresh_state": 1, "refresh_requests": 0}),
    )
    monkeypatch.setattr(
        sync,
        "build_refresh_collaborators",
        lambda _settings=None: (
            SimpleNamespace(database_path=tmp_path / "strava.db"),
            "clock",
            "sleeper",
            "transport",
            "policy",
        ),
    )
    monkeypatch.setattr(sync, "DbConn", FakeDbConn)
    monkeypatch.setattr(sync.SQLiteRepository, "from_connection", staticmethod(lambda _conn: "repo"))
    monkeypatch.setattr(sync.refresh_runtime, "run_once", fake_run_once)

    result = sync.sync_activities(quick=True)

    assert result.status == "ok"
    assert calls
    assert calls[0]["force"] is True
    assert calls[0]["mode"] == "quick"


def test_sync_entrypoints_fail_fast_without_refresh_schema(monkeypatch, tmp_path: Path) -> None:
    import mcp_strava.sync as sync

    def _unexpected_collaborators(*_args, **_kwargs):
        raise AssertionError("refresh collaborators must not be built before schema v2 exists")

    monkeypatch.setattr(sync, "get_settings", lambda: SimpleNamespace(database_path=tmp_path / "strava.db"))
    monkeypatch.setattr(sync, "run_preflight", lambda *_args, **_kwargs: SimpleNamespace(row_counts={}))
    monkeypatch.setattr(sync, "build_refresh_collaborators", _unexpected_collaborators)

    with pytest.raises(RuntimeError, match="db-migrate"):
        sync.sync_activities()
    with pytest.raises(RuntimeError, match="db-migrate"):
        sync.backfill_activities()


def test_default_compose_has_no_public_host_port_binding() -> None:
    compose = Path("deploy/docker-compose.yml")
    if not compose.exists():
        pytest.fail("deploy/docker-compose.yml must exist")
    text = compose.read_text(encoding="utf-8")
    assert '0.0.0.0:' not in text
    assert 'ports: ["0.0.0.0' not in text


def test_backfill_activities_invokes_run_backfill_per_D16(monkeypatch, tmp_path: Path) -> None:
    import mcp_strava.sync as sync
    from mcp_strava.refresh.runtime import RefreshResult

    calls: list[dict] = []

    class FakeDbConn:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_run_once(*_args, **_kwargs):
        raise AssertionError("backfill_activities must not call run_once")

    def fake_run_backfill(repo, transport, policy, clock, sleeper, **kwargs):
        calls.append(
            {
                "repo": repo,
                "transport": transport,
                "policy": policy,
                "clock": clock,
                "sleeper": sleeper,
                **kwargs,
            }
        )
        return RefreshResult(status="ok", mode="backfill", checkpoint_stage="complete_backfill")

    monkeypatch.setattr(sync, "get_settings", lambda: SimpleNamespace(database_path=tmp_path / "strava.db"))
    monkeypatch.setattr(
        sync,
        "run_preflight",
        lambda *_args, **_kwargs: SimpleNamespace(row_counts={"refresh_state": 1, "refresh_requests": 0}),
    )
    monkeypatch.setattr(
        sync,
        "build_refresh_collaborators",
        lambda _settings=None: (
            SimpleNamespace(database_path=tmp_path / "strava.db"),
            "clock",
            "sleeper",
            "transport",
            "policy",
        ),
    )
    monkeypatch.setattr(sync, "DbConn", FakeDbConn)
    monkeypatch.setattr(sync.SQLiteRepository, "from_connection", staticmethod(lambda _conn: "repo"))
    monkeypatch.setattr(sync.refresh_runtime, "run_once", fake_run_once)
    monkeypatch.setattr(sync.refresh_runtime, "run_backfill", fake_run_backfill)

    result = sync.backfill_activities(since="2024-01-01")

    assert result.status == "ok"
    assert calls
    assert calls[0]["since"] == "2024-01-01"
    assert calls[0]["owner"] == "refresh-backfill"
