from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

from mcp_strava.types import (
    CompletenessMetadata,
    FreshnessMetadata,
    ServiceEnvelope,
    ServiceRationale,
    ServiceWarning,
)


OLD_COMMAND_KEYS = {
    "activities",
    "gear",
    "stats",
    "sql",
    "refresh",
    "sync",
    "backfill",
    "backtest",
    "trend",
    "report",
    "weekly",
    "raw",
    "log",
    "kudos",
    "db-preflight",
    "db-check",
    "db-migrate",
    "db-refresh",
}

ADMIN_COMMANDS = {
    "mirror-refresh",
    "token-refresh",
    "backfill",
    "sql",
    "raw",
    "log",
    "db-preflight",
    "db-check",
    "db-migrate",
}


def _fake_envelope(data: object | None = None) -> ServiceEnvelope:
    return ServiceEnvelope(
        data={} if data is None else data,
        freshness=FreshnessMetadata(
            freshness_state="fresh",
            checked_at="2026-05-21T09:00:00",
            last_successful_refresh_at="2026-05-21T06:00:00",
            refresh_age_seconds=10_800,
            last_activity_at="2026-05-21T07:00:00",
            last_activity_age_seconds=7_200,
        ),
        completeness=CompletenessMetadata(
            status="partial",
            missing=["missing_streams"],
            coverage={"fixture": True},
        ),
        warnings=[
            ServiceWarning(
                code="missing_streams",
                severity="warning",
                message="Fixture stream metrics are incomplete.",
            )
        ],
        rationale=[ServiceRationale(code="fixture", message="Fixture response.")],
    )


def _run_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[str, str]:
    import mcp_strava.cli as cli

    monkeypatch.setattr(sys, "argv", ["mcp_strava", *args])
    cli.main()
    captured = capsys.readouterr()
    return captured.out, captured.err


def _install_product_service_spies(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[object]]:
    import mcp_strava.cli as cli

    calls: dict[str, list[object]] = {
        "daily": [],
        "weekly": [],
        "recent": [],
        "workout": [],
        "freshness": [],
    }

    def daily_service(**kwargs):
        calls["daily"].append(kwargs)
        return _fake_envelope({"today": "2026-05-21", "recommendation": {"action": "rest"}})

    def weekly_service(**kwargs):
        calls["weekly"].append(kwargs)
        return _fake_envelope({"period": {"today": "2026-05-21"}, "current_state": {}, "trends": {}})

    def recent_service(limit=15, **kwargs):
        calls["recent"].append({"limit": limit, **kwargs})
        return _fake_envelope(
            [
                {
                    "id": 702,
                    "date": "2026-05-21",
                    "name": "Morning Run",
                    "sport_type": "Run",
                    "distance_km": 5.0,
                    "moving_time_min": 30.0,
                    "trimp": 80.0,
                    "avg_hr": 145.0,
                    "max_hr": 165,
                }
            ]
        )

    def workout_service(activity_id, **kwargs):
        calls["workout"].append({"activity_id": activity_id, **kwargs})
        return _fake_envelope({"id": 702, "name": "Morning Run", "trimp": 80.0, "avg_hr": 145.0})

    def freshness_service(**kwargs):
        calls["freshness"].append(kwargs)
        return _fake_envelope({"freshness_state": "fresh"})

    monkeypatch.setattr(cli, "get_daily_report_service", daily_service, raising=False)
    monkeypatch.setattr(cli, "get_weekly_summary_service", weekly_service, raising=False)
    monkeypatch.setattr(cli, "get_recent_workouts_service", recent_service, raising=False)
    monkeypatch.setattr(cli, "get_workout_analytics_service", workout_service, raising=False)
    monkeypatch.setattr(cli, "get_freshness_service", freshness_service, raising=False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("product CLI must call application services, not legacy internals")

    monkeypatch.setattr(cli, "daily_report", forbidden, raising=False)
    monkeypatch.setattr(cli, "weekly_digest", forbidden, raising=False)
    monkeypatch.setattr(cli, "api_request", forbidden, raising=False)
    monkeypatch.setattr(cli, "sync_activities", forbidden, raising=False)
    monkeypatch.setattr(cli, "backfill_activities", forbidden, raising=False)
    monkeypatch.setattr(cli, "DbConn", forbidden, raising=False)
    return calls


@pytest.mark.parametrize(
    ("args", "service_name", "label"),
    [
        (("report", "daily"), "daily", "Daily Report"),
        (("weekly",), "weekly", "Weekly Summary"),
        (("workouts", "recent", "--limit", "1"), "recent", "Recent Workouts"),
        (("workout", "analyze", "702"), "workout", "Workout Analytics"),
        (("freshness",), "freshness", "Freshness"),
    ],
)
def test_product_commands_use_services_and_render_human_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    args: tuple[str, ...],
    service_name: str,
    label: str,
) -> None:
    calls = _install_product_service_spies(monkeypatch)

    stdout, stderr = _run_cli(monkeypatch, capsys, *args)

    assert stderr == ""
    assert calls[service_name]
    assert label in stdout
    assert "Freshness" in stdout
    assert "Warnings" in stdout
    assert "ServiceEnvelope(" not in stdout


@pytest.mark.parametrize(
    "args",
    [
        ("report", "daily", "--json"),
        ("weekly", "--json"),
        ("workouts", "recent", "--limit", "1", "--json"),
        ("workout", "analyze", "latest", "--json"),
        ("freshness", "--json"),
    ],
)
def test_product_commands_support_json_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    args: tuple[str, ...],
) -> None:
    _install_product_service_spies(monkeypatch)

    stdout, _stderr = _run_cli(monkeypatch, capsys, *args)
    payload = json.loads(stdout)

    assert set(payload) == {"data", "freshness", "completeness", "warnings", "rationale"}
    assert payload["freshness"]["freshness_state"] == "fresh"
    assert payload["completeness"]["status"] == "partial"
    assert payload["warnings"][0]["code"] == "missing_streams"


def test_admin_commands_are_namespaced_and_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    import mcp_strava.cli as cli
    from mcp_strava.application.registry import PRODUCT_SERVICES

    assert set(cli.ADMIN_COMMANDS) == ADMIN_COMMANDS
    assert "mirror-refresh" in cli.ADMIN_COMMANDS
    assert "token-refresh" in cli.ADMIN_COMMANDS
    assert "sync" not in cli.COMMANDS
    assert "refresh" not in cli.COMMANDS
    assert "admin" in cli.COMMANDS
    assert ADMIN_COMMANDS.isdisjoint(PRODUCT_SERVICES)


def test_cli_docs_replacement_mapping_accounts_for_old_commands() -> None:
    docs_path = Path("docs/cli.md")
    assert docs_path.exists()
    text = docs_path.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "| old command | new command/status | notes |" in lowered
    for command in OLD_COMMAND_KEYS:
        assert f"| `{command}` |" in lowered
    assert "`refresh`" in text
    assert "`db-refresh`" in text
    assert "token-refresh" in text
    assert "mirror-refresh" in text
    assert "not part of the mcp surface" in lowered


def test_product_cli_handlers_do_not_call_legacy_or_admin_runtime_directly() -> None:
    source = Path("src/mcp_strava/cli.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    product_handlers = {"cmd_report", "cmd_weekly", "cmd_workouts", "cmd_workout", "cmd_freshness"}
    forbidden_names = {
        "daily_report",
        "weekly_digest",
        "DbConn",
        "api_request",
        "sync_activities",
        "backfill_activities",
        "refresh_token",
    }
    forbidden_attrs = {"execute"}
    violations: list[str] = []

    for node in module.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in product_handlers:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in forbidden_names:
                violations.append(f"{node.name}:{child.lineno} uses {child.id}")
            elif isinstance(child, ast.Attribute) and child.attr in forbidden_attrs:
                violations.append(f"{node.name}:{child.lineno} uses .{child.attr}")
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                lowered = " ".join(child.value.lower().split())
                if "select " in lowered or " from " in lowered:
                    violations.append(f"{node.name}:{child.lineno} embeds SQL")

    assert violations == []
