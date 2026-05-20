import importlib.util
import os
import sys
from collections.abc import Callable
from pathlib import Path

TestFn = Callable[[], None]


def load_tests(tests_path: Path) -> list[TestFn]:
    spec = importlib.util.spec_from_file_location("test_smoke", tests_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load smoke tests from {tests_path}")

    test_smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_smoke)

    return [
        value
        for name, value in vars(test_smoke).items()
        if name.startswith("test_") and callable(value)
    ]


def main() -> int:
    scripts_dir = Path(__file__).resolve().parent
    os.chdir(scripts_dir)
    sys.path.insert(0, str(scripts_dir))

    tests_path = scripts_dir.parent / "tests" / "test_smoke.py"
    tests = load_tests(tests_path)

    passed = 0
    for fn in tests:
        name = fn.__name__
        try:
            print(f"{name}...", end=" ")
            fn()
            print("PASS")
            passed += 1
        except Exception as exc:
            print(f"FAIL: {exc}")

    print(f"\n{passed}/{len(tests)} tests passed")
    if passed == len(tests):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
