"""Shared CLI helpers."""

from __future__ import annotations

import sys


def _as_str(v: object) -> str:
    """Convert any value to str without passing Any to str()."""
    return str(v)


def _pop_json_flag(args):
    if "--json" not in args:
        return False
    args.remove("--json")
    return True


def _usage_error(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)
