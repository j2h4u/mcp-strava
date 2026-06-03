"""Tests for the source-text logic fingerprint.

The logic fingerprint is the detector that makes the read model
self-invalidating: it is a sha256 over the source text of every module on the
materializer compute path. When any of that source changes (a constant, a
formula, a registry column), the fingerprint changes and downstream plans
recompute the read-model facts automatically — no hand-bumped version int.

Three properties are proven here:

* **Determinism** — the digest is process-independent and NOT Python's builtin
  ``hash()`` (which is salted per process by ``PYTHONHASHSEED``).
* **Coverage-by-construction (sensitivity)** — the digest is a pure function of
  the source text of exactly the listed modules: altering a listed module's
  source flips it; altering an unlisted module's source does not.
* **Completeness (poka-yoke)** — every ``mcp_strava`` module reachable from the
  materializer compute path is present in ``COMPUTE_SOURCE_MODULES``. If a future
  edit adds a compute module to the import graph but forgets the tuple, this test
  fails loudly and names the missing module.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import os
import subprocess
import sys

import pytest

from mcp_strava.metric_registry import COMPUTE_SOURCE_MODULES, compute_logic_fingerprint

# Root of the materializer compute path. The completeness walk starts here.
_MATERIALIZER_MODULE = "mcp_strava.adapters.duckdb.read_model_materializer"


def _module_source_path(module_name: str) -> str | None:
    """Return the .py source path for a module, or None if it is not a .py file."""
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None or not spec.origin.endswith(".py"):
        return None
    return spec.origin


def _direct_mcp_strava_imports(module_name: str) -> set[str]:
    """Static AST walk: direct ``mcp_strava.*`` imports of one module.

    Uses ``ast.parse`` over the module's *source text* (not a runtime
    ``sys.modules`` snapshot) so the graph reflects the real source-level
    compute path and never pulls in test-only or lazily-imported modules.
    """
    path = _module_source_path(module_name)
    if path is None:
        return set()
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # Absolute ``from mcp_strava... import ...`` only (level 0).
            if node.level == 0 and node.module and node.module.startswith("mcp_strava"):
                found.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("mcp_strava"):
                    found.add(alias.name)
    return found


def _reachable_compute_modules() -> set[str]:
    """Full recursive ``mcp_strava.*`` import closure of the materializer.

    This is the *reality* the tuple must list: every module whose source text
    participates in materialization. A static closure (not a runtime
    ``sys.modules`` snapshot) keeps test-only modules out.
    """
    seen: set[str] = set()
    stack: list[str] = [_MATERIALIZER_MODULE]
    while stack:
        module_name = stack.pop()
        if module_name in seen:
            continue
        seen.add(module_name)
        for dependency in _direct_mcp_strava_imports(module_name):
            if dependency not in seen:
                stack.append(dependency)
    return seen


# --------------------------------------------------------------------------- #
# Determinism                                                                  #
# --------------------------------------------------------------------------- #


def test_fingerprint_is_64_char_hex() -> None:
    digest = compute_logic_fingerprint()
    assert isinstance(digest, str)
    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)


def test_fingerprint_is_stable_in_process() -> None:
    assert compute_logic_fingerprint() == compute_logic_fingerprint()


def _subprocess_fingerprint(hashseed: str) -> str:
    """Compute the fingerprint in a fresh interpreter with a given PYTHONHASHSEED."""
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["PYTHONHASHSEED"] = hashseed
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from mcp_strava.metric_registry import compute_logic_fingerprint;print(compute_logic_fingerprint())",
        ],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_fingerprint_matches_fresh_subprocess() -> None:
    in_process = compute_logic_fingerprint()
    in_subprocess = _subprocess_fingerprint("0")
    assert in_subprocess == in_process


def test_fingerprint_independent_of_pythonhashseed() -> None:
    # If the implementation leaned on builtin hash(), these would differ:
    # hash() of str/bytes is salted per process by PYTHONHASHSEED.
    seed_zero = _subprocess_fingerprint("0")
    seed_one = _subprocess_fingerprint("1")
    seed_random = _subprocess_fingerprint("random")
    assert seed_zero == seed_one == seed_random == compute_logic_fingerprint()


# --------------------------------------------------------------------------- #
# Coverage-by-construction (sensitivity)                                       #
# --------------------------------------------------------------------------- #


def test_altering_a_listed_module_changes_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = compute_logic_fingerprint()
    target = COMPUTE_SOURCE_MODULES[0]
    real_getsource = inspect.getsource

    def fake_getsource(obj: object) -> str:
        if getattr(obj, "__name__", None) == target:
            return real_getsource(obj) + "\n# fingerprint-sensitivity-probe\n"
        return real_getsource(obj)

    monkeypatch.setattr("mcp_strava.metric_registry.inspect.getsource", fake_getsource)
    assert compute_logic_fingerprint() != baseline


def test_altering_an_unlisted_module_does_not_change_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = compute_logic_fingerprint()
    # cli is a real mcp_strava module that is NOT on the materializer compute path.
    unlisted = "mcp_strava.cli"
    assert unlisted not in COMPUTE_SOURCE_MODULES
    real_getsource = inspect.getsource

    def fake_getsource(obj: object) -> str:
        if getattr(obj, "__name__", None) == unlisted:
            return real_getsource(obj) + "\n# should-not-matter\n"
        return real_getsource(obj)

    monkeypatch.setattr("mcp_strava.metric_registry.inspect.getsource", fake_getsource)
    assert compute_logic_fingerprint() == baseline


# --------------------------------------------------------------------------- #
# Completeness (poka-yoke)                                                     #
# --------------------------------------------------------------------------- #


def test_compute_source_modules_covers_full_compute_path() -> None:
    reachable = _reachable_compute_modules()
    listed = set(COMPUTE_SOURCE_MODULES)
    missing = reachable - listed
    assert not missing, (
        "COMPUTE_SOURCE_MODULES is missing modules reachable from the materializer "
        f"compute path: {sorted(missing)}. Add them to the tuple so a logic change "
        "in those modules invalidates the read model."
    )
    extra = listed - reachable
    assert not extra, (
        "COMPUTE_SOURCE_MODULES lists modules that are NOT on the materializer "
        f"compute path: {sorted(extra)}. The tuple must list reality, not aspiration."
    )


def test_materializer_direct_imports_are_all_listed() -> None:
    direct = _direct_mcp_strava_imports(_MATERIALIZER_MODULE)
    listed = set(COMPUTE_SOURCE_MODULES)
    missing = direct - listed
    assert not missing, (
        "read_model_materializer directly imports mcp_strava modules absent from "
        f"COMPUTE_SOURCE_MODULES: {sorted(missing)}"
    )


def test_metric_registry_is_listed() -> None:
    # The materializer imports metric_registry directly
    # (MATERIALIZED_ROLLING_WINDOW_DAYS), so registry-owned schema/metadata —
    # e.g. the 15-05 start_time_local column registration — must flip the
    # fingerprint. Guard that metric_registry is never dropped from the tuple.
    assert "mcp_strava.metric_registry" in COMPUTE_SOURCE_MODULES


def test_all_listed_modules_are_importable() -> None:
    for module_name in COMPUTE_SOURCE_MODULES:
        # Must not raise: import_module inside compute_logic_fingerprint relies on this.
        importlib.import_module(module_name)


# --------------------------------------------------------------------------- #
# Packaged-install getsource smoke (editable; unconditional)                   #
# --------------------------------------------------------------------------- #


def test_getsource_succeeds_on_every_compute_source_module() -> None:
    """inspect.getsource must succeed on EVERY COMPUTE_SOURCE_MODULES module.

    The fingerprint is computed by inspect.getsource over each compute module.
    Under some packaged layouts getsource can raise OSError (no source file
    available), which would crash the fingerprint compare on every refresh cycle
    (T-15-11). This UNCONDITIONAL local smoke runs under `uv run pytest -q` on the
    editable install and catches a getsource regression locally — not only in
    Docker. The real packaged pip-install layout is additionally proven by the
    docker compose exec smoke in tests/test_docker_runtime.py.
    """
    for module_name in COMPUTE_SOURCE_MODULES:
        module = importlib.import_module(module_name)
        try:
            source = inspect.getsource(module)
        except OSError as exc:  # pragma: no cover - failure path is the assertion
            raise AssertionError(f"inspect.getsource raised OSError for {module_name}: {exc}") from exc
        assert source, f"empty source returned for {module_name}"

    digest = compute_logic_fingerprint()
    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)
