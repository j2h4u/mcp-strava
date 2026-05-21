import os
import subprocess
import sys
import ast
from pathlib import Path


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


def test_cli_has_operator_only_sql_and_explicit_db_safety_commands() -> None:
    commands = _command_registry_names()
    assert "sql" in commands
    assert "db-preflight" in commands
    assert "db-check" in commands
    assert "db-migrate" in commands


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
    assert _assert_no_schema_ddl_in_init_db() == []
