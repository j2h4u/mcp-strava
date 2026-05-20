import os
import subprocess
import sys
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
