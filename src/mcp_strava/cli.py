"""Strava CLI — thin dispatcher on top of mcp_strava modules."""

import sys
from datetime import datetime

from mcp_strava.application.freshness import get_freshness_service
from mcp_strava.application.metric_services import get_workout_detail_service, list_workouts_service
from mcp_strava.application.product_facts import get_daily_brief_facts_service, get_weekly_digest_facts_service
from mcp_strava.cli_admin import ADMIN_COMMANDS, cmd_admin
from mcp_strava.cli_common import _pop_json_flag, _usage_error
from mcp_strava.cli_render import (
    _print_product_envelope,
    _render_bundle_report,
    _render_freshness,
    _render_recent_workouts,
    _render_workout_analytics,
)

__all__ = ["ADMIN_COMMANDS", "COMMANDS", "cmd_admin", "main"]

# ═══════════════════════════════════════════════════════════════
#  CLI Commands
# ═══════════════════════════════════════════════════════════════


def cmd_report(args):
    """Daily training report product command."""
    json_output = _pop_json_flag(args)
    if not args or args[0] != "daily":
        _usage_error("Usage: python -m mcp_strava report daily [--json]")
    envelope = get_daily_brief_facts_service(as_of_day=_today_day())
    _print_product_envelope(envelope, json_output=json_output, title="Daily Report", renderer=_render_bundle_report)


def cmd_weekly(args):
    """Weekly summary product command."""
    json_output = _pop_json_flag(args)
    if args:
        _usage_error("Usage: python -m mcp_strava weekly [--json]")
    envelope = get_weekly_digest_facts_service(as_of_day=_today_day())
    _print_product_envelope(envelope, json_output=json_output, title="Weekly Summary", renderer=_render_bundle_report)


def cmd_workouts(args):
    """Recent workouts product command."""
    json_output = _pop_json_flag(args)
    if not args or args[0] != "recent":
        _usage_error(
            "Usage: python -m mcp_strava workouts recent [--limit N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] [--sport SPORT] [--json]"
        )
    options = _parse_workouts_recent_options(args[1:])
    envelope = list_workouts_service(**options)
    _print_product_envelope(
        envelope, json_output=json_output, title="Recent Workouts", renderer=_render_recent_workouts
    )


def cmd_workout(args):
    """Single workout analytics product command."""
    json_output = _pop_json_flag(args)
    if len(args) < 2 or args[0] != "analyze":  # noqa: PLR2004
        _usage_error("Usage: python -m mcp_strava workout analyze <id|latest> [--json]")
    envelope = get_workout_detail_service(args[1])
    _print_product_envelope(
        envelope, json_output=json_output, title="Workout Analytics", renderer=_render_workout_analytics
    )


def cmd_freshness(args):
    """Freshness product command."""
    json_output = _pop_json_flag(args)
    if args:
        _usage_error("Usage: python -m mcp_strava freshness [--json]")
    envelope = get_freshness_service()
    _print_product_envelope(envelope, json_output=json_output, title="Freshness", renderer=_render_freshness)


def _today_day() -> str:
    return datetime.now().date().isoformat()  # noqa: DTZ005 — local calendar day for CLI display


def _parse_workouts_recent_options(args):
    options = {
        "limit": 20,
        "start_date": None,
        "end_date": None,
        "sport": None,
    }
    if len(args) == 1 and args[0].isdigit():
        options["limit"] = int(args[0])
        return options

    index = 0
    while index < len(args):
        token = args[index]
        if token == "--limit":
            if index + 1 >= len(args) or not args[index + 1].isdigit():
                _usage_error("Usage: --limit N")
            options["limit"] = int(args[index + 1])
            index += 2
            continue
        if token in {"--start-date", "--end-date", "--sport"}:
            if index + 1 >= len(args):
                _usage_error("Usage: --start-date YYYY-MM-DD --end-date YYYY-MM-DD --sport SPORT")
            key = token[2:].replace("-", "_")
            options[key] = args[index + 1]
            index += 2
            continue
        _usage_error(
            "Usage: python -m mcp_strava workouts recent [--limit N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] [--sport SPORT] [--json]"
        )
    return options


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

COMMANDS = {
    "report": cmd_report,
    "weekly": cmd_weekly,
    "workouts": cmd_workouts,
    "workout": cmd_workout,
    "freshness": cmd_freshness,
    "admin": cmd_admin,
}


def main():
    if len(sys.argv) < 2:  # noqa: PLR2004
        print(f"Usage: python -m mcp_strava <command> [args]\nCommands: {', '.join(COMMANDS)}", file=sys.stderr)
        sys.exit(1)
    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd in COMMANDS:
        COMMANDS[cmd](args)
    else:
        print(f"Unknown command: {cmd}\nCommands: {', '.join(COMMANDS)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
