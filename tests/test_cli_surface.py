from __future__ import annotations

import ast
import json
import sqlite3
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
    "mirror-coverage",
    "token-refresh",
    "duckdb-cutover",
    "backfill",
    "backfill-streams",
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
        "daily_brief": [],
        "weekly_digest": [],
        "recent": [],
        "workout": [],
        "freshness": [],
    }

    def daily_brief_service(**kwargs):
        calls["daily_brief"].append(kwargs)
        return _fake_envelope(
            {
                "bundle_id": "daily_brief",
                "as_of_day": kwargs.get("as_of_day"),
                "sections": {
                    "current_state": {"metrics": {"fitness": 42.0, "form": -3.0}},
                    "supported_gear": {
                        "items": [{"activity_id": 702, "gear_id": "g1", "gear_name": "Tempo Shoe"}]
                    },
                },
                "bundle_completeness": {"requested_metrics": ["fitness"], "included_metrics": ["fitness"]},
            }
        )

    def weekly_digest_service(**kwargs):
        calls["weekly_digest"].append(kwargs)
        return _fake_envelope(
            {
                "bundle_id": "weekly_digest",
                "as_of_day": kwargs.get("as_of_day"),
                "sections": {
                    "load": {"rows": [{"metric_id": "trimp", "value": 120.0}]},
                    "period_trends": {
                        "comparison": {
                            "global": {
                                "metrics": {
                                    "trimp": {
                                        "delta": 15.0,
                                        "trend_direction": "up",
                                        "sample_size": {"period_a": 4, "period_b": 3},
                                    }
                                }
                            }
                        }
                    },
                },
                "bundle_completeness": {"requested_metrics": ["trimp"], "included_metrics": ["trimp"]},
            }
        )

    def recent_service(limit=20, **kwargs):
        calls["recent"].append({"limit": limit, **kwargs})
        return _fake_envelope(
            [
                {
                    "activity_id": 702,
                    "activity_date": "2026-05-21",
                    "activity_name": "Morning Run",
                    "sport_type": "Run",
                    "distance_km": 5.0,
                    "moving_time_min": 30.0,
                    "elevation_m": 40.0,
                    "trimp": 80.0,
                    "avg_hr": 145.0,
                    "max_hr": 165,
                    "kudos_count": 4,
                }
            ]
        )

    def workout_service(activity_id, **kwargs):
        calls["workout"].append({"activity_id": activity_id, **kwargs})
        return _fake_envelope(
            {
                "activity_id": 702,
                "activity_date": "2026-05-21",
                "activity_name": "Morning Run",
                "sport_type": "Run",
                "distance_km": 5.0,
                "moving_time_min": 30.0,
                "trimp": 80.0,
                "avg_hr": 145.0,
                "max_hr": 165,
                "cardiac_drift_pct": 3.5,
                "kudos_count": 4,
                "kudos_names": ["Ada Lovelace", "Grace Hopper"],
                "gear_id": "g1",
                "gear_name": "Tempo Shoe",
                "gear_distance_km": 123.4,
                "gear_primary": True,
            }
        )

    def freshness_service(**kwargs):
        calls["freshness"].append(kwargs)
        return _fake_envelope({"freshness_state": "fresh"})

    monkeypatch.setattr(cli, "get_daily_brief_facts_service", daily_brief_service, raising=False)
    monkeypatch.setattr(cli, "get_weekly_digest_facts_service", weekly_digest_service, raising=False)
    monkeypatch.setattr(cli, "list_workouts_service", recent_service, raising=False)
    monkeypatch.setattr(cli, "get_workout_detail_service", workout_service, raising=False)
    monkeypatch.setattr(cli, "get_freshness_service", freshness_service, raising=False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("product CLI must call application services, not legacy internals")

    monkeypatch.setattr(cli, "get_daily_report_service", forbidden, raising=False)
    monkeypatch.setattr(cli, "get_weekly_summary_service", forbidden, raising=False)
    monkeypatch.setattr(cli, "get_recent_workouts_service", forbidden, raising=False)
    monkeypatch.setattr(cli, "get_workout_analytics_service", forbidden, raising=False)
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
        (("report", "daily"), "daily_brief", "Daily Report"),
        (("weekly",), "weekly_digest", "Weekly Summary"),
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


def test_daily_and_weekly_json_delegate_to_product_fact_bundles(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = _install_product_service_spies(monkeypatch)

    daily_stdout, _ = _run_cli(monkeypatch, capsys, "report", "daily", "--json")
    weekly_stdout, _ = _run_cli(monkeypatch, capsys, "weekly", "--json")

    daily_payload = json.loads(daily_stdout)
    weekly_payload = json.loads(weekly_stdout)
    assert calls["daily_brief"] and calls["daily_brief"][0]["as_of_day"]
    assert calls["weekly_digest"] and calls["weekly_digest"][0]["as_of_day"]
    assert daily_payload["data"]["bundle_id"] == "daily_brief"
    assert weekly_payload["data"]["bundle_id"] == "weekly_digest"
    assert "supported_gear" in daily_payload["data"]["sections"]
    assert "period_trends" in weekly_payload["data"]["sections"]
    assert "trimp" in weekly_payload["data"]["sections"]["period_trends"]["comparison"]["global"]["metrics"]


def test_workouts_recent_forwards_supported_filters_to_metric_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = _install_product_service_spies(monkeypatch)

    stdout, _ = _run_cli(
        monkeypatch,
        capsys,
        "workouts",
        "recent",
        "--limit",
        "7",
        "--start-date",
        "2026-05-01",
        "--end-date",
        "2026-05-21",
        "--sport",
        "Run",
        "--json",
    )
    payload = json.loads(stdout)

    assert calls["recent"] == [
        {
            "limit": 7,
            "start_date": "2026-05-01",
            "end_date": "2026-05-21",
            "sport": "Run",
        }
    ]
    assert payload["data"][0]["activity_id"] == 702
    assert payload["data"][0]["kudos_count"] == 4


def test_workout_detail_json_exposes_kudos_names_and_supported_gear_facts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = _install_product_service_spies(monkeypatch)

    stdout, _ = _run_cli(monkeypatch, capsys, "workout", "analyze", "702", "--json")
    payload = json.loads(stdout)

    assert calls["workout"] == [{"activity_id": "702"}]
    assert payload["data"]["kudos_count"] == 4
    assert payload["data"]["kudos_names"] == ["Ada Lovelace", "Grace Hopper"]
    assert payload["data"]["gear_id"] == "g1"
    assert payload["data"]["gear_name"] == "Tempo Shoe"
    assert payload["data"]["gear_distance_km"] == 123.4
    assert payload["data"]["gear_primary"] is True


def test_admin_commands_are_namespaced_and_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    import mcp_strava.cli as cli
    from mcp_strava.application.registry import PRODUCT_SERVICES

    assert set(cli.ADMIN_COMMANDS) == ADMIN_COMMANDS
    assert "mirror-refresh" in cli.ADMIN_COMMANDS
    assert "mirror-coverage" in cli.ADMIN_COMMANDS
    assert "token-refresh" in cli.ADMIN_COMMANDS
    assert "duckdb-cutover" in cli.ADMIN_COMMANDS
    assert "sync" not in cli.COMMANDS
    assert "refresh" not in cli.COMMANDS
    assert "admin" in cli.COMMANDS
    assert ADMIN_COMMANDS.isdisjoint(PRODUCT_SERVICES)
    assert {"daily_brief_facts", "weekly_digest_facts", "historical_facts"}.issubset(PRODUCT_SERVICES)
    assert {"daily_report", "weekly_summary", "workout_analytics"}.isdisjoint(PRODUCT_SERVICES)


def test_admin_duckdb_cutover_help_uses_canonical_runtime_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mcp_strava.cli as cli

    monkeypatch.setattr(sys, "argv", ["mcp_strava", "admin", "duckdb-cutover", "--help"])

    cli.main()
    captured = capsys.readouterr()
    text = captured.out + captured.err

    assert "admin duckdb-cutover" in text
    assert "/runtime/data/strava.duckdb" in text
    assert "full Strava resync" not in text.lower()


def test_admin_duckdb_cutover_requires_apply_confirmation_for_live_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mcp_strava.cli as cli

    def forbidden_cutover(*_args, **_kwargs):
        raise AssertionError("live-looking cutover must fail before migration runs")

    monkeypatch.setattr(cli, "run_duckdb_cutover", forbidden_cutover, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mcp_strava",
            "admin",
            "duckdb-cutover",
            "--source-sqlite",
            str(tmp_path / "source.db"),
            "--target-duckdb",
            "/runtime/data/strava.duckdb",
            "--backup-dir",
            str(tmp_path / "backups"),
            "--json",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "confirm" in captured.err.lower()


def test_admin_duckdb_cutover_prints_report_and_does_not_construct_strava_collaborators(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mcp_strava.cli as cli

    source = tmp_path / "source.db"
    target = tmp_path / "target.duckdb"
    backups = tmp_path / "backups"
    source.write_bytes(b"sqlite-fixture-placeholder")
    calls: list[dict[str, object]] = []

    class FakeReport:
        backup_path = backups / "strava-pre-phase-8-20260525T120000Z.db"
        duckdb_path = target
        parity_ok = True
        cast_failures: list[dict[str, object]] = []
        rollback = {
            "sqlite_backup_path": str(backup_path),
            "instructions": ["stop runtime", "restore pinned SQLite backup", "run preflight"],
        }

        def to_dict(self) -> dict[str, object]:
            return {
                "backup_path": str(self.backup_path),
                "duckdb_path": str(self.duckdb_path),
                "parity_ok": self.parity_ok,
                "cast_failures": self.cast_failures,
                "rollback": self.rollback,
            }

    def fake_cutover(**kwargs):
        calls.append(kwargs)
        return FakeReport()

    def forbidden_strava(*_args, **_kwargs):
        raise AssertionError("DuckDB cutover must not construct Strava collaborators")

    monkeypatch.setattr(cli, "run_duckdb_cutover", fake_cutover, raising=False)
    monkeypatch.setattr(cli, "build_refresh_collaborators", forbidden_strava, raising=False)
    monkeypatch.setattr(cli, "api_request", forbidden_strava, raising=False)
    monkeypatch.setattr(cli, "sync_activities", forbidden_strava, raising=False)
    monkeypatch.setattr(cli, "backfill_activities", forbidden_strava, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mcp_strava",
            "admin",
            "duckdb-cutover",
            "--source-sqlite",
            str(source),
            "--target-duckdb",
            str(target),
            "--backup-dir",
            str(backups),
            "--apply",
            "--confirm-live-cutover",
            "--json",
        ],
    )

    cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert calls == [
        {
            "source_sqlite_path": source,
            "target_duckdb_path": target,
            "backup_dir": backups,
            "now": None,
            "owner": "cli-admin",
        }
    ]
    assert payload["backup_path"] == str(FakeReport.backup_path)
    assert payload["duckdb_path"] == str(target)
    assert payload["parity_ok"] is True
    assert payload["cast_failures"] == []
    assert "rollback" in payload


def test_duckdb_cutover_is_absent_from_mcp_and_product_surfaces() -> None:
    from mcp_strava.application.registry import PRODUCT_SERVICES
    from mcp_strava.interfaces.mcp_http import MCP_INSTRUCTIONS, MCP_TOOL_NAMES

    rendered_tools = " ".join(MCP_TOOL_NAMES).lower()
    rendered_instructions = MCP_INSTRUCTIONS.lower()

    assert "duckdb-cutover" not in PRODUCT_SERVICES
    assert "duckdb-cutover" not in rendered_tools
    assert "storage-migrate" not in rendered_tools
    assert "duckdb-cutover" not in rendered_instructions


def test_admin_mirror_coverage_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import mcp_strava.cli as cli
    from mcp_strava.adapters.sqlite.migrations import run_migrations
    from tests.test_full_fidelity_mirror import _create_v2_fixture

    fixture = tmp_path / "coverage.db"
    _create_v2_fixture(fixture)
    with sqlite3.connect(fixture) as conn:
        conn.execute(
            "UPDATE activities SET summary_json = ?, detail_json = ? WHERE id = 10",
            (
                json.dumps({"STRAVA_ACCESS_TOKEN": "summary-secret"}),
                json.dumps({"refresh_token": "detail-secret"}),
            ),
        )
    run_migrations(fixture)

    monkeypatch.setattr(sys, "argv", ["mcp_strava", "admin", "mirror-coverage", "--db", str(fixture), "--json"])
    cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "ok"
    for key in ("activities_with_streams", "stream_points", "gps_points", "channels", "backfill_needed"):
        assert key in payload
    rendered = json.dumps(payload, sort_keys=True)
    assert "summary_json" not in rendered
    assert "detail_json" not in rendered
    assert "summary-secret" not in rendered
    assert "detail-secret" not in rendered
    assert "access_token" not in rendered.lower()
    assert "refresh_token" not in rendered.lower()


def test_admin_backfill_streams_dry_run_json_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import mcp_strava.cli as cli
    from tests.test_full_fidelity_mirror import _create_v2_fixture

    def fake_backfill(*_args, **kwargs):
        assert kwargs["dry_run"] is True
        return {
            "status": "ok",
            "mode": "backfill_stream_channels",
            "activities_considered": 10,
            "activities_to_backfill": 3,
            "missing_channels": {"watts": 3},
            "metadata_missing": 3,
            "estimated_api_calls": 3,
            "checkpoint_stage": "stream_channels_backfill",
        }

    def fail_build_refresh_collaborators():
        raise AssertionError("dry-run must not require Strava credentials")

    monkeypatch.setattr(cli, "backfill_stream_channels", fake_backfill, raising=False)
    monkeypatch.setattr(cli, "build_refresh_collaborators", fail_build_refresh_collaborators, raising=False)
    fixture = tmp_path / "coverage.db"
    _create_v2_fixture(fixture)
    monkeypatch.setattr(
        sys,
        "argv",
        ["mcp_strava", "admin", "backfill-streams", "--db", str(fixture), "--dry-run", "--json"],
    )
    cli.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    for key in (
        "mode",
        "activities_considered",
        "activities_to_backfill",
        "missing_channels",
        "metadata_missing",
        "estimated_api_calls",
        "checkpoint_stage",
    ):
        assert key in payload


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
    assert "| `gear` | available via workout detail |" in lowered
    assert "| `stats` | folded into product bundle |" in lowered
    assert "| `trend` | folded into `weekly --json` |" in lowered
    assert "| `kudos` | available via workout detail |" in lowered


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
