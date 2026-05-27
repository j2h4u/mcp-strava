from pathlib import Path


REQUIRED_LOCAL_STATE_PATTERNS = {
    ".env",
    ".env.*",
    ".planning/config.json",
    "data/*.duckdb",
    "data/**/*.duckdb",
    "data/*.duckdb.wal",
    "data/**/*.duckdb.wal",
    "data/*.duckdb-*",
    "data/**/*.duckdb-*",
}


def _gitignore_patterns() -> set[str]:
    root = Path(__file__).resolve().parents[1]
    lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    return {
        line.strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_local_state_policy_is_static_and_git_runtime_independent() -> None:
    missing = REQUIRED_LOCAL_STATE_PATTERNS - _gitignore_patterns()
    assert missing == set()
