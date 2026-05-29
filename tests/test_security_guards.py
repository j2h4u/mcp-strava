import ast
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


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


def test_cli_retired_legacy_product_handlers_and_imports_are_absent() -> None:
    rel_path = "src/mcp_strava/cli.py"
    source = _source_text(rel_path)
    module = ast.parse(source, filename=rel_path)
    dead_handlers = {
        "cmd_activities",
        "cmd_gear",
        "cmd_stats",
        "cmd_backtest",
        "cmd_trend",
        "cmd_kudos",
    }
    legacy_modules = {
        "mcp_strava.application.reports",
        "mcp_strava.application.workouts",
        "mcp_strava.analytics",
        "mcp_strava.report",
        "mcp_strava.trends",
    }
    legacy_db_imports = {"api_request", "get_daily_trimp_history"}
    violations: list[str] = []

    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name in dead_handlers:
            violations.append(f"{rel_path}:{node.lineno} legacy handler {node.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in legacy_modules:
                    violations.append(f"{rel_path}:{node.lineno} import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            imported_module = node.module or ""
            if imported_module in legacy_modules:
                violations.append(f"{rel_path}:{node.lineno} from {imported_module}")
            if imported_module == "mcp_strava.db":
                for alias in node.names:
                    if alias.name in legacy_db_imports:
                        violations.append(f"{rel_path}:{node.lineno} from {imported_module} import {alias.name}")

    assert violations == []


def test_cli_product_commands_route_to_product_fact_and_metric_services() -> None:
    rel_path = "src/mcp_strava/cli.py"
    source = _source_text(rel_path)
    module = ast.parse(source, filename=rel_path)
    expected_calls = {
        "cmd_report": {"get_daily_brief_facts_service"},
        "cmd_weekly": {"get_weekly_digest_facts_service"},
        "cmd_workouts": {"list_workouts_service"},
        "cmd_workout": {"get_workout_detail_service"},
        "cmd_freshness": {"get_freshness_service"},
    }
    forbidden_calls = {
        "get_daily_report_service",
        "get_weekly_summary_service",
        "get_recent_workouts_service",
        "get_workout_analytics_service",
        "daily_report",
        "weekly_digest",
        "compute_trends",
        "api_request",
        "DbConn",
    }
    violations: list[str] = []

    for node in module.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in expected_calls:
            continue
        calls: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.add(child.func.attr)
        missing = expected_calls[node.name] - calls
        if missing:
            violations.append(f"{node.name} missing {sorted(missing)}")
        used_forbidden = sorted(forbidden_calls & calls)
        if used_forbidden:
            violations.append(f"{node.name} uses forbidden {used_forbidden}")

    assert violations == []


def test_cli_includes_namespaced_admin_refresh_commands() -> None:
    import mcp_strava.cli as cli

    assert "admin" in _command_registry_names()
    assert "catchup" in cli.ADMIN_COMMANDS
    assert "token-refresh" in cli.ADMIN_COMMANDS
    assert "mirror-refresh" not in cli.ADMIN_COMMANDS
    assert "backfill" not in cli.ADMIN_COMMANDS
    assert "backfill-streams" not in cli.ADMIN_COMMANDS
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
    }

    assert forbidden.isdisjoint(PRODUCT_SERVICES)


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


def _call_names(rel_path: str, function_names: set[str] | None = None) -> dict[str, set[str]]:
    module = ast.parse(_source_text(rel_path), filename=rel_path)
    calls_by_function: dict[str, set[str]] = {}
    for node in module.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if function_names is not None and node.name not in function_names:
            continue
        calls: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.add(child.func.attr)
        calls_by_function[node.name] = calls
    return calls_by_function


def test_product_bundle_services_do_not_import_admin_sync_raw_or_legacy_read_paths() -> None:
    product_modules = [
        "src/mcp_strava/application/product_facts.py",
        "src/mcp_strava/application/aggregate_services.py",
    ]
    disallowed_prefixes = (
        "mcp_strava.adapters.strava",
        "mcp_strava.sync",
        "mcp_strava.refresh.runtime",
        "mcp_strava.application.reports",
        "mcp_strava.application.workouts",
        "mcp_strava.analytics",
        "mcp_strava.report",
        "mcp_strava.trends",
    )
    violations: list[str] = []

    for rel_path in product_modules:
        violations.extend(_import_violations(rel_path, disallowed_prefixes))
        module = ast.parse(_source_text(rel_path), filename=rel_path)
        for node in ast.walk(module):
            if not isinstance(node, ast.ImportFrom):
                continue
            imported_module = node.module or ""
            if imported_module != "mcp_strava.db":
                continue
            for alias in node.names:
                if alias.name in {"api_request", "refresh_token"}:
                    violations.append(f"{rel_path}:{node.lineno} from {imported_module} import {alias.name}")

    assert violations == []


def test_product_bundle_services_do_not_call_request_time_recompute_or_admin_handlers() -> None:
    product_modules = [
        "src/mcp_strava/application/product_facts.py",
        "src/mcp_strava/application/aggregate_services.py",
    ]
    forbidden_calls = {
        "daily_report",
        "daily_report_from_connection",
        "weekly_digest",
        "compute_trends",
        "check_z5_minutes",
        "check_hr_anomalies",
        "activity_stream_rows",
        "stream_hr_velocity_rows",
        "stream_hr_velocity_simple_rows",
        "stream_hr_velocity_time_rows",
        "stream_hr_time_rows",
        "stream_altitude_rows",
        "api_request",
        "refresh_token",
        "cmd_sql",
        "cmd_strava_raw",
        "cmd_log",
        "cmd_backfill",
        "backfill_activities",
        "sync_activities",
    }
    violations: list[str] = []

    for rel_path in product_modules:
        for function_name, calls in _call_names(rel_path).items():
            used_forbidden = sorted(forbidden_calls & calls)
            if used_forbidden:
                violations.append(f"{rel_path}:{function_name} uses {used_forbidden}")

    assert violations == []


def test_cli_product_commands_do_not_call_admin_raw_or_recompute_paths() -> None:
    product_command_names = {
        "cmd_report",
        "cmd_weekly",
        "cmd_workouts",
        "cmd_workout",
        "cmd_freshness",
    }
    forbidden_calls = {
        "cmd_sql",
        "cmd_refresh",
        "cmd_backfill",
        "cmd_db_refresh",
        "cmd_strava_raw",
        "cmd_log",
        "cmd_mirror_coverage",
        "cmd_backfill_streams",
        "api_request",
        "refresh_token",
        "backfill_activities",
        "daily_report",
        "weekly_digest",
        "compute_trends",
        "DbConn",
    }
    violations: list[str] = []

    for function_name, calls in _call_names("src/mcp_strava/cli.py", product_command_names).items():
        missing_product_boundary = not calls & {
            "get_daily_brief_facts_service",
            "get_weekly_digest_facts_service",
            "list_workouts_service",
            "get_workout_detail_service",
            "get_freshness_service",
        }
        if missing_product_boundary:
            violations.append(f"{function_name} does not call a product read service")
        used_forbidden = sorted(forbidden_calls & calls)
        if used_forbidden:
            violations.append(f"{function_name} uses forbidden calls {used_forbidden}")

    assert violations == []


def test_legacy_application_report_and_workout_modules_remain_retired() -> None:
    root = Path(__file__).resolve().parents[1]
    retired = [
        root / "src" / "mcp_strava" / "application" / "reports.py",
        root / "src" / "mcp_strava" / "application" / "workouts.py",
    ]
    assert [path for path in retired if path.exists()] == []


def test_read_modules_do_not_import_storage_strava_or_refresh() -> None:
    """Domain modules must not import storage or adapter tiers (strava, refresh, db, duckdb adapter)."""
    read_modules = [
        "src/mcp_strava/training.py",
        "src/mcp_strava/metrics.py",
        "src/mcp_strava/cardiac_drift.py",
        "src/mcp_strava/hr_zones.py",
        "src/mcp_strava/sports.py",
    ]
    violations: list[str] = []
    for rel_path in read_modules:
        violations.extend(
            _import_violations(
                rel_path,
                (
                    "mcp_strava.adapters.strava",
                    "mcp_strava.refresh",
                    "mcp_strava.db",
                    "mcp_strava.adapters.duckdb",
                ),
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


def test_metric_services_do_not_import_or_call_request_time_recompute_helpers() -> None:
    rel_path = "src/mcp_strava/application/metric_services.py"
    source = _source_text(rel_path)
    module = ast.parse(source)
    forbidden_imports = {
        "mcp_strava.analytics.weekly_digest",
        "mcp_strava.report.daily_report_from_connection",
    }
    forbidden_calls = {
        "weekly_digest",
        "daily_report_from_connection",
        "activity_stream_rows",
        "stream_hr_velocity_rows",
        "stream_hr_velocity_simple_rows",
        "stream_hr_velocity_time_rows",
        "stream_hr_time_rows",
        "stream_altitude_rows",
        "activity_trimp",
        "activity_cc",
        "activity_z5_seconds",
    }
    violations: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom):
            imported_module = node.module or ""
            for alias in node.names:
                full_name = f"{imported_module}.{alias.name}"
                if full_name in forbidden_imports:
                    violations.append(f"{rel_path}:{node.lineno} import {full_name}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                violations.append(f"{rel_path}:{node.lineno} call {node.func.id}")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in forbidden_calls:
                violations.append(f"{rel_path}:{node.lineno} call {node.func.attr}")

    assert violations == []


def test_metric_services_do_not_query_raw_streams() -> None:
    source = _source_text("src/mcp_strava/application/metric_services.py").lower()
    assert " from streams" not in source
    assert " join streams" not in source
    assert " streams " not in source


def test_mcp_request_modules_do_not_reference_raw_stream_table_sql() -> None:
    request_modules = [
        "src/mcp_strava/application/metric_services.py",
        "src/mcp_strava/application/metric_registry.py",
        "src/mcp_strava/interfaces/mcp_http.py",
    ]
    forbidden_fragments = (
        "from streams",
        "join streams",
        "pragma table_info(streams)",
        "from stream_channels",
        "join stream_channels",
    )
    violations: list[str] = []
    for rel_path in request_modules:
        lowered = _source_text(rel_path).lower()
        for fragment in forbidden_fragments:
            if fragment in lowered:
                violations.append(f"{rel_path}: contains {fragment!r}")

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

    monkeypatch.setattr(sync, "get_settings", lambda: SimpleNamespace(database_path=tmp_path / "strava.duckdb"))
    monkeypatch.setattr(sync, "ensure_runtime_refresh_schema", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sync,
        "build_refresh_collaborators",
        lambda _settings=None: (
            SimpleNamespace(database_path=tmp_path / "strava.duckdb"),
            "clock",
            "sleeper",
            "transport",
            "policy",
        ),
    )
    monkeypatch.setattr(sync, "DbConn", FakeDbConn)
    monkeypatch.setattr(sync.DuckDBRepository, "from_connection", staticmethod(lambda _conn: "repo"))
    monkeypatch.setattr(sync.refresh_runtime, "run_once", fake_run_once)

    result = sync.sync_activities(quick=True)

    assert result.status == "ok"
    assert calls
    assert calls[0]["force"] is True
    assert calls[0]["mode"] == "quick"


def test_default_compose_has_no_public_host_port_binding() -> None:
    compose = Path("deploy/docker-compose.yml")
    if not compose.exists():
        pytest.fail("deploy/docker-compose.yml must exist")
    text = compose.read_text(encoding="utf-8")
    assert "0.0.0.0:" not in text
    assert 'ports: ["0.0.0.0' not in text


def test_backfill_activities_invokes_run_catchup_per_D16(monkeypatch, tmp_path: Path) -> None:
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

    def fake_run_catchup(repo, transport, policy, clock, sleeper, **kwargs):
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

    monkeypatch.setattr(sync, "get_settings", lambda: SimpleNamespace(database_path=tmp_path / "strava.duckdb"))
    monkeypatch.setattr(sync, "ensure_runtime_refresh_schema", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sync,
        "build_refresh_collaborators",
        lambda _settings=None: (
            SimpleNamespace(database_path=tmp_path / "strava.duckdb"),
            "clock",
            "sleeper",
            "transport",
            "policy",
        ),
    )
    monkeypatch.setattr(sync, "DbConn", FakeDbConn)
    monkeypatch.setattr(sync.DuckDBRepository, "from_connection", staticmethod(lambda _conn: "repo"))
    monkeypatch.setattr(sync.refresh_runtime, "run_once", fake_run_once)
    monkeypatch.setattr(sync.refresh_runtime, "run_catchup", fake_run_catchup)

    result = sync.backfill_activities(since="2024-01-01")

    assert result.status == "ok"
    assert calls
    assert calls[0]["since"] == "2024-01-01"
    assert calls[0]["owner"] == "refresh-backfill"
