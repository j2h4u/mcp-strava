# Testing Patterns

**Analysis Date:** 2026-05-20

## Test Framework

**Runner:**
- Custom smoke runner in `scripts/run_tests.py`.
- No pytest or unittest config detected.

**Assertion Library:**
- Plain `assert` statements inside test functions.

**Run Commands:**
```bash
just test
python3 scripts/run_tests.py
```

## Test File Organization

**Location:**
- Tests are centralized in `tests/test_smoke.py`.
- The runner loads that file directly with `importlib.util.spec_from_file_location()` in `scripts/run_tests.py`.

**Naming:**
- Test functions are named `test_*`.
- The runner executes every callable in `tests/test_smoke.py` whose name starts with `test_`.

**Structure:**
```text
tests/
  test_smoke.py
```

## Test Structure

**Suite Organization:**
```python
def test_ewma():
    """EWMA: empty, single value, decay behavior."""
    from strava_lib.training import ewma

    assert ewma({}, tau=7) == {}
    r = ewma({"2026-01-01": 100}, tau=7, end_date="2026-01-01")
    assert 5 < r["2026-01-01"] < 15
```

**Patterns:**
- Tests are direct function calls with inline assertions.
- Each test prints a short success line, which the custom runner relays.
- Docstrings describe the scenario under test and the expected behavior.
- Some tests mix unit-level checks with light integration checks, for example `test_daily_report()` calls `daily_report()` end-to-end.

## Mocking

**Framework:** None detected.

**Patterns:**
```python
def test_forward_simulate():
    from strava_lib.training import forward_simulate
    result = forward_simulate(50.0, 25.0, [30, 0, 50], date(2026, 5, 4), alpha_fitness, alpha_fatigue)
    assert len(result) == 3
```

**What to Mock:**
- Not established in the current suite.
- The repository favors real function execution over mocked collaborators for the covered paths.

**What NOT to Mock:**
- `test_daily_report()` exercises the real report pipeline instead of stubbing it.
- `test_imports()` validates real module imports and config constants from `scripts/strava_lib/constants.py`.

## Fixtures and Factories

**Test Data:**
- Inline literals are used instead of shared fixtures.
- Date-sensitive tests create their own `date(...)` or string inputs.
- There are no factory modules or fixture directories detected.

**Location:**
- Not detected.

## Coverage

**Requirements:** None enforced.

**View Coverage:**
```bash
python3 -m coverage run scripts/run_tests.py
python3 -m coverage report
```

## Test Types

**Unit Tests:**
- Pure-function checks dominate the suite, especially in `scripts/strava_lib/training.py`, `metrics.py`, `analytics.py`, and `sports.py`.
- Coverage includes edge cases for EWMA, trend detection, decoupling gates, median and percent-change helpers, and sport registry lookups.

**Integration Tests:**
- `test_imports()` verifies that the package imports cleanly and that `Config` exposes the expected hierarchy.
- `test_daily_report()` calls `daily_report()` through `scripts/strava_lib/report.py` and validates the returned object shape.

**E2E Tests:**
- Not used.

## Common Patterns

**Async Testing:**
- Not used.

**Error Testing:**
```python
assert trend([1, 2, 3]) is None
assert calc_decoupling([]) is None
assert pct_change(100, 0) is None
```
- Error-path behavior is usually verified by asserting `None` or invalid-state dataclasses rather than expecting exceptions.

## Runner Behavior

- `scripts/run_tests.py` changes into the `scripts/` directory before loading `tests/test_smoke.py`.
- It prints `PASS` or `FAIL: ...` for each test and exits with status 1 if any test fails.
- There is no discovery beyond `test_*` callables in the single smoke file.

## Current Coverage Shape

- Strongest coverage: pure analytics helpers in `scripts/strava_lib/training.py`, `metrics.py`, `analytics.py`, and `sports.py`.
- Moderate coverage: module import surfaces and `daily_report()` in `scripts/strava_lib/report.py`.
- Weak or absent coverage: CLI command dispatch in `scripts/cli.py`, sync retry behavior in `scripts/strava_lib/sync.py`, and database migration behavior in `scripts/strava_lib/db.py`.

## Practical Rules

- Add new tests to `tests/test_smoke.py` unless the suite is intentionally expanded to a new framework.
- Keep tests deterministic and cheap; avoid live API calls in the main smoke suite.
- When a function can fail due to missing data, assert the `None` or fallback shape explicitly.
- Preserve the `test_*` naming convention so `scripts/run_tests.py` can find the test automatically.

---

*Testing analysis: 2026-05-20*
