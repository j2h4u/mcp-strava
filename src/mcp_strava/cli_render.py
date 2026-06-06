"""Human and JSON rendering helpers for product CLI commands."""

from __future__ import annotations

import json

from mcp_strava.types import dc_to_dict


def _print_product_envelope(envelope, *, json_output, title, renderer):
    converted = dc_to_dict(envelope)
    payload: dict[str, object] = converted if isinstance(converted, dict) else {}
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(title)
    print("=" * len(title))
    renderer(payload.get("data"))
    _render_metadata(payload)


def _render_metadata(payload):
    freshness = payload.get("freshness") or {}
    completeness = payload.get("completeness") or {}
    warnings = payload.get("warnings") or []
    rationale = payload.get("rationale") or []

    print()
    print("Freshness")
    print(f"- state: {freshness.get('freshness_state')}")
    print(f"- checked_at: {freshness.get('checked_at')}")
    print(f"- last_successful_refresh_at: {freshness.get('last_successful_refresh_at')}")
    print(f"- refresh_age_seconds: {freshness.get('refresh_age_seconds')}")
    print(f"- last_activity_at: {freshness.get('last_activity_at')}")
    print(f"- last_activity_age_seconds: {freshness.get('last_activity_age_seconds')}")
    if freshness.get("refresh_requested"):
        print(f"- refresh_requested: {freshness.get('refresh_request_reason')}")

    print()
    print("Completeness")
    print(f"- status: {completeness.get('status')}")
    missing = completeness.get("missing") or []
    print(f"- missing: {', '.join(missing) if missing else 'none'}")

    print()
    print("Warnings")
    if warnings:
        for warning in warnings:
            print(f"- {warning.get('code')}: {warning.get('message')}")
    else:
        print("- none")

    if rationale:
        print()
        print("Rationale")
        for item in rationale:
            print(f"- {item.get('code')}: {item.get('message')}")


def _render_bundle_report(data):
    data = data or {}
    _render_bundle_sections(data)


def _render_recent_workouts(data):
    rows = data or []
    if not rows:
        print("No workouts.")
        return
    print("| date | id | sport | distance_km | moving_min | trimp | name |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        print(
            f"| {row.get('activity_date') or row.get('date')} | "
            f"{row.get('activity_id') or row.get('id')} | {row.get('sport_type')} | "
            f"{row.get('distance_km')} | {row.get('moving_time_min')} | "
            f"{row.get('trimp')} | {row.get('activity_name') or row.get('name')} |"
        )


def _render_workout_analytics(data):
    data = data or {}
    if not data:
        print("Workout not found.")
        return
    print(f"- id: {data.get('activity_id') or data.get('id')}")
    print(f"- date: {data.get('activity_date') or data.get('date')}")
    print(f"- name: {data.get('activity_name') or data.get('name')}")
    print(f"- sport_type: {data.get('sport_type')}")
    print(f"- distance_km: {data.get('distance_km')}")
    print(f"- moving_time_min: {data.get('moving_time_min')}")
    print(f"- trimp: {data.get('trimp')}")
    print(f"- avg_hr: {data.get('avg_hr')}")
    print(f"- max_hr: {data.get('max_hr')}")
    print(f"- cardiac_drift_pct: {data.get('cardiac_drift_pct') or data.get('cardiac_drift')}")
    if data.get("kudos_count") is not None:
        print(f"- kudos_count: {data.get('kudos_count')}")
    if data.get("kudos_names"):
        print(f"- kudos_names: {', '.join(data.get('kudos_names') or [])}")
    if data.get("gear_id") or data.get("gear_name"):
        print(f"- gear: {data.get('gear_name') or data.get('gear_id')}")


def _render_freshness(data):
    data = data or {}
    if data:
        for key, value in data.items():
            print(f"- {key}: {value}")
    else:
        print("- no additional freshness data")


def _render_bundle_sections(data):
    print(f"Bundle: {data.get('bundle_id')}")
    if data.get("as_of_day"):
        print(f"As of: {data.get('as_of_day')}")
    sections = data.get("sections") or {}
    if not isinstance(sections, dict) or not sections:
        print("- no sections")
        return
    for section_id, section in sections.items():
        print()
        print(str(section_id).replace("_", " ").title())
        if not isinstance(section, dict):
            print(f"- {section}")
            continue
        metrics = section.get("metrics") or section.get("facts")
        if isinstance(metrics, dict) and metrics:
            for key, value in list(metrics.items())[:8]:
                print(f"- {key}: {value}")
        rows = section.get("rows")
        if isinstance(rows, list) and rows:
            for row in rows[:5]:
                if isinstance(row, dict):
                    print(f"- {row.get('metric_id')}: {row.get('value', row.get('completeness_status'))}")
        items = section.get("items")
        if isinstance(items, list) and items:
            for item in items[:5]:
                if isinstance(item, dict):
                    label = item.get("activity_name") or item.get("activity_id") or item.get("gear_name") or item
                    print(f"- {label}")
        comparison = section.get("comparison")
        if isinstance(comparison, dict):
            global_metrics = (comparison.get("global") or {}).get("metrics") or {}
            for metric_id, payload in list(global_metrics.items())[:5]:
                if isinstance(payload, dict):
                    print(f"- {metric_id}: delta={payload.get('delta')} trend={payload.get('trend_direction')}")
