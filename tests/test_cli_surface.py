from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import duckdb
import pytest

from mcp_strava.types import (
    CompletenessMetadata,
    FreshnessMetadata,
    ServiceEnvelope,
    ServiceRationale,
    ServiceWarning,
)
from tests._fixtures_duckdb import create_fixture_db

ADMIN_COMMANDS = {
    "mirror-coverage",
    "token-refresh",
    "catchup",
    "compact",
    "sql",
    "raw",
    "log",
    "db-preflight",
    "db-check",
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
                    "supported_gear": {"items": [{"activity_id": 702, "gear_id": "g1", "gear_name": "Tempo Shoe"}]},
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
    monkeypatch.setattr(cli, "StravaClient", forbidden)
    monkeypatch.setattr(cli, "sync_activities", forbidden, raising=False)
    monkeypatch.setattr(cli, "backfill_activities", forbidden, raising=False)
    monkeypatch.setattr(cli, "MirrorConn", forbidden)
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

    # Exact contract on the admin command set (drift detector).
    assert set(cli.ADMIN_COMMANDS) == ADMIN_COMMANDS
    assert "admin" in cli.COMMANDS
    # Admin and product surfaces must not overlap; product services must be present.
    assert ADMIN_COMMANDS.isdisjoint(PRODUCT_SERVICES)
    assert {"daily_brief_facts", "weekly_digest_facts", "historical_facts"}.issubset(PRODUCT_SERVICES)


def test_admin_mirror_coverage_json_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import mcp_strava.cli as cli

    fixture = tmp_path / "coverage.duckdb"
    create_fixture_db(fixture)
    conn = duckdb.connect(str(fixture))
    try:
        conn.execute(
            "UPDATE activities SET summary_json = ?, detail_json = ? WHERE id = 10",
            [
                json.dumps({"STRAVA_ACCESS_TOKEN": "summary-secret"}),
                json.dumps({"refresh_token": "detail-secret"}),
            ],
        )
    finally:
        conn.close()

    monkeypatch.setattr(sys, "argv", ["mcp_strava", "admin", "mirror-coverage", "--db", str(fixture), "--json"])
    cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "ok"
    for key in ("activities_with_streams", "stream_points", "gps_points", "channels", "backfill_needed"):
        assert key in payload
    # Report must name WHICH activities/channels need backfill, not just a count, and stay bounded.
    sample = payload["stream_channel_backfill_sample"]
    assert isinstance(sample, list)
    assert len(sample) <= 20
    assert all({"activity_id", "missing_channels"} == set(entry) for entry in sample)
    rendered = json.dumps(payload, sort_keys=True)
    assert "summary_json" not in rendered
    assert "detail_json" not in rendered
    assert "summary-secret" not in rendered
    assert "detail-secret" not in rendered
    assert "access_token" not in rendered.lower()
    assert "refresh_token" not in rendered.lower()


def test_admin_catchup_dry_run_json_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import mcp_strava.cli as cli

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

    def fail_backfill_activities(*_args, **_kwargs):
        raise AssertionError("dry-run catchup must not run activity backfill")

    def fail_build_refresh_collaborators():
        raise AssertionError("dry-run must not require Strava credentials")

    monkeypatch.setattr(cli, "backfill_stream_channels", fake_backfill, raising=False)
    monkeypatch.setattr(cli, "backfill_activities", fail_backfill_activities, raising=False)
    monkeypatch.setattr(cli, "build_refresh_collaborators", fail_build_refresh_collaborators, raising=False)
    fixture = tmp_path / "coverage.duckdb"
    create_fixture_db(fixture)
    monkeypatch.setattr(
        sys,
        "argv",
        ["mcp_strava", "admin", "catchup", "--db", str(fixture), "--dry-run", "--json"],
    )
    cli.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["dry_run"] is True
    assert payload["activities"]["status"] == "skipped"
    stream = payload["stream_channels"]
    for key in (
        "mode",
        "activities_considered",
        "activities_to_backfill",
        "missing_channels",
        "metadata_missing",
        "estimated_api_calls",
        "checkpoint_stage",
    ):
        assert key in stream


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
