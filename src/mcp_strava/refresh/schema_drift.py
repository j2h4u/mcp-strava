"""Journal Strava API schema drift.

Runs each fetched Strava response through the api_schema validator and logs a
structured event when something new shows up — an unknown field (Strava added it
and we do not model it yet) or a Summit-only field that suddenly carries data.

The raw response JSON is already persisted in full (activities.summary_json /
detail_json), so no data is ever lost by us. This is purely an awareness signal:
a journal entry so an operator notices new fields worth promoting into the read
model. It writes nothing to the database.
"""

from __future__ import annotations

import json
from typing import Any

from mcp_strava.api_schema import validate_batch, validate_response


def _emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def journal_schema_drift(data: Any, endpoint_name: str, *, is_batch: bool = False) -> None:
    """Validate one Strava response (or a list of them) and journal any drift.

    Side-effect only: emits a ``strava_schema_drift`` event when the validator
    finds unknown or newly-active Summit fields, and does nothing otherwise. The
    inputs are type-guarded (the validator only iterates dicts), so this never
    needs to write to or read from the mirror. ``is_batch`` validates the first
    few items of a list response (summary-activity pages); otherwise ``data`` is
    a single response dict (a detailed activity or a streams payload).
    """
    if is_batch:
        if not isinstance(data, list):
            return
        result = validate_batch(data, endpoint_name)
    else:
        if not isinstance(data, dict):
            return
        result = validate_response(data, endpoint_name)

    if result.has_findings:
        _emit(
            "strava_schema_drift",
            endpoint=result.endpoint,
            unknown_fields=result.unknown_fields,
            active_summit=result.active_summit,
            checked_at=result.checked_at,
        )
