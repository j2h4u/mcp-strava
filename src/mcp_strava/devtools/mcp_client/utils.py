from __future__ import annotations

from datetime import date, timedelta

from mcp_strava.devtools.mcp_client.contracts import McpClientError


def _require_success(name: str, result: dict[str, object]) -> dict[str, object]:
    if result.get("isError") is True:
        raise McpClientError(f"{name} returned isError=true")
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise McpClientError(f"{name} returned no structuredContent object")
    return result


def _extract_first_workout_id(result: dict[str, object]) -> int:
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise McpClientError("list_workouts returned no structuredContent")
    data = structured.get("data")
    candidates = data if isinstance(data, list) else []
    if isinstance(data, dict):
        for key in ("workouts", "items", "activities"):
            value = data.get(key)
            if isinstance(value, list):
                candidates = value
                break
    for item in candidates:
        if not isinstance(item, dict):
            continue
        for key in ("activity_id", "workout_id", "id"):
            val = item.get(key)
            if val is not None:
                return int(str(val))
    raise McpClientError("list_workouts returned no extractable workout id")


def _get_structured_data(payload: dict[str, object]) -> object:
    """Extract ``structuredContent.data`` from a tool result, or ``None``."""
    sc = payload.get("structuredContent")
    if isinstance(sc, dict):
        return sc.get("data")
    return None


def _coerce_day(value: str | date | None) -> date:
    if value is None:
        return date.today()  # noqa: DTZ011 — local calendar default day for the devtools client
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _product_bundle_aggregate_calls(today_date: date) -> list[dict[str, object]]:
    end_exclusive = (today_date + timedelta(days=1)).isoformat()
    return [
        {
            "name": "get_training_aggregates",
            "arguments": {
                "start_date": (today_date - timedelta(days=13)).isoformat(),
                "end_date": end_exclusive,
                "bucket": "all_time",
                "metric_bundle": "daily_brief",
                "scope": "both",
            },
        },
        {
            "name": "get_training_aggregates",
            "arguments": {
                "start_date": (today_date - timedelta(days=27)).isoformat(),
                "end_date": end_exclusive,
                "bucket": "week",
                "metric_bundle": "weekly_digest",
                "scope": "both",
            },
        },
        {
            "name": "get_training_aggregates",
            "arguments": {
                "start_date": (today_date - timedelta(days=365)).isoformat(),
                "end_date": end_exclusive,
                "bucket": "all_time",
                "metric_bundle": "historical_facts",
                "scope": "both",
            },
        },
    ]


def _data_shape(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {"type": "dict", "keys": sorted(value.keys())[:30]}
    if isinstance(value, list):
        first = value[0] if value else None
        first_keys: list[str] | None = sorted(first.keys())[:30] if isinstance(first, dict) else None
        return {"type": "list", "count": len(value), "first_keys": first_keys}
    return {"type": type(value).__name__}


def _warning_digest(payload: dict[str, object]) -> list[dict[str, str]]:
    """Summarize a tool payload's warnings as ``[{code, severity}]``.

    The smoke output previously reported only a count (e.g. ``1``), which forced
    a source dive to learn what the warning actually was. Returning the stable
    ``code`` (and ``severity``) makes the summary self-explanatory while keeping
    the count derivable via ``len()``.
    """
    sc = payload.get("structuredContent")
    warnings_raw = sc.get("warnings") if isinstance(sc, dict) else None
    warnings: list[object] = list(warnings_raw) if isinstance(warnings_raw, list) else []
    digest: list[dict[str, str]] = []
    for entry in warnings:
        if isinstance(entry, dict):
            digest.append(
                {
                    "code": str(entry.get("code", "unknown")),
                    "severity": str(entry.get("severity", "warning")),
                }
            )
        else:
            digest.append({"code": str(entry), "severity": "warning"})
    return digest


def _lookup_path(payload: object, path: str) -> object:
    current: object = payload
    for segment in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError) as exc:
                raise McpClientError(f"cannot resolve list segment {segment!r} in path {path!r}") from exc
            continue
        if isinstance(current, dict):
            if segment not in current:
                raise McpClientError(f"missing path segment {segment!r} in path {path!r}")
            current = current[segment]
            continue
        raise McpClientError(f"cannot descend into non-container value at segment {segment!r} for path {path!r}")
    return current
