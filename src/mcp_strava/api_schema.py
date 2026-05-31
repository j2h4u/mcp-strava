"""
Strava API schema — machine-readable field contracts for validation.

Two-layer detection:
  1. Unknown keys: field in JSON but not in schema → API update
  2. Newly-active Summit: field marked 💰 suddenly becomes non-null/non-zero

Derived from strava_api_reference.py (single source of human docs).

STATUS: planned, not yet wired. These dataclasses were designed for the sync
path to flag unknown Strava fields and newly-active Summit fields, but nothing
imports this module yet — the detection pass was never connected. Kept for when
the feature is implemented.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ═══════════════════════════════════════════════════════════════════
#  Status constants
# ═══════════════════════════════════════════════════════════════════


class Status:
    """Field status — mirrors strava_api_reference.py icons."""

    FREE_USED = "free_used"  # ✅ we actively consume this
    FREE_UNUSED = "free_unused"  # 🔵 available, not used yet
    SUMMIT = "summit"  # 💰 requires paid subscription
    NOT_APPLICABLE = "not_applicable"  # ⬜ exists but irrelevant


# ═══════════════════════════════════════════════════════════════════
#  Dataclasses
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FieldSchema:
    """One field in a Strava API response."""

    name: str
    type_hint: str  # "int", "float", "str", "bool", "list", "dict", "float?"
    status: str  # Status.* constant
    description: str = ""
    summit_null_value: Any | None = None  # What free accounts get for this field

    def is_summit_active(self, value: Any) -> bool:
        """
        Check if a Summit field is suddenly non-null for a free account.
        Returns True if the field looks "active" (not the null-equivalent).
        """
        if self.status != Status.SUMMIT:
            return False
        null_val = self.summit_null_value
        if null_val is None:
            return value is not None
        if isinstance(null_val, (int, float)):
            return value is not None and value != null_val
        if isinstance(null_val, bool):
            return value is not False
        if isinstance(null_val, list):
            return bool(value)
        if isinstance(null_val, dict):
            return bool(value)
        return value != null_val


@dataclass
class EndpointSchema:
    """Schema for one Strava API endpoint response."""

    name: str  # "summary_activity", "detailed_activity", "streams"
    endpoint: str  # "GET /athlete/activities"
    fields: dict[str, FieldSchema] = field(default_factory=dict)

    def unknown_keys(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Return keys in data but NOT in schema."""
        result = []
        for key in data:
            if key not in self.fields:
                val = data[key]
                result.append(
                    {
                        "field": key,
                        "value_type": type(val).__name__,
                        "is_null": val is None,
                    }
                )
        return result

    def active_summit_fields(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Return Summit fields that are now non-null/non-zero."""
        result = []
        for key, value in data.items():
            fs = self.fields.get(key)
            if fs and fs.is_summit_active(value):
                result.append(
                    {
                        "field": key,
                        "value": str(value)[:100],
                        "expected_null": str(fs.summit_null_value),
                    }
                )
        return result


@dataclass
class ValidationResult:
    """Result of validating a response against a schema."""

    endpoint: str
    unknown_fields: list[dict[str, Any]] = field(default_factory=list)
    active_summit: list[dict[str, Any]] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def has_findings(self) -> bool:
        return bool(self.unknown_fields or self.active_summit)

    @property
    def is_clean(self) -> bool:
        return not self.has_findings


# ═══════════════════════════════════════════════════════════════════
#  Schema Registry
# ═══════════════════════════════════════════════════════════════════

# ─── SummaryActivity (GET /athlete/activities) ───

SUMMARY_ACTIVITY = EndpointSchema(
    name="summary_activity",
    endpoint="GET /athlete/activities",
    fields={
        # ✅ Actively consumed
        "id": FieldSchema("id", "int", Status.FREE_USED, "primary key"),
        "name": FieldSchema("name", "str", Status.FREE_USED),
        "sport_type": FieldSchema("sport_type", "str", Status.FREE_USED),
        "start_date": FieldSchema("start_date", "str", Status.FREE_USED, "UTC ISO 8601"),
        "start_date_local": FieldSchema("start_date_local", "str", Status.FREE_USED, "stored as date"),
        "distance": FieldSchema("distance", "float", Status.FREE_USED, "metres"),
        "moving_time": FieldSchema("moving_time", "int", Status.FREE_USED, "seconds"),
        "elapsed_time": FieldSchema("elapsed_time", "int", Status.FREE_USED, "seconds"),
        "total_elevation_gain": FieldSchema("total_elevation_gain", "float", Status.FREE_USED, "metres"),
        "has_heartrate": FieldSchema("has_heartrate", "bool", Status.FREE_USED),
        "average_heartrate": FieldSchema("average_heartrate", "float?", Status.FREE_USED, "bpm"),
        "max_heartrate": FieldSchema("max_heartrate", "float?", Status.FREE_USED, "bpm"),
        # 🔵 Available, not used yet
        "average_speed": FieldSchema("average_speed", "float?", Status.FREE_UNUSED, "m/s"),
        "max_speed": FieldSchema("max_speed", "float?", Status.FREE_UNUSED, "m/s"),
        "average_cadence": FieldSchema("average_cadence", "float?", Status.FREE_UNUSED, "steps/min"),
        "gear_id": FieldSchema("gear_id", "str?", Status.FREE_UNUSED, "shoe id"),
        # 💰 Summit-only
        "suffer_score": FieldSchema("suffer_score", "int?", Status.SUMMIT, summit_null_value=0),
        "perceived_exertion": FieldSchema("perceived_exertion", "int?", Status.SUMMIT, summit_null_value=None),
        # ⬜ Not used / not interesting
        "type": FieldSchema("type", "str", Status.NOT_APPLICABLE, "deprecated alias"),
        "workout_type": FieldSchema("workout_type", "int?", Status.NOT_APPLICABLE),
        "resource_state": FieldSchema("resource_state", "int", Status.NOT_APPLICABLE),
        "athlete": FieldSchema("athlete", "dict", Status.NOT_APPLICABLE),
        "map": FieldSchema("map", "dict", Status.NOT_APPLICABLE),
        "device_name": FieldSchema("device_name", "str?", Status.NOT_APPLICABLE),
        "external_id": FieldSchema("external_id", "str?", Status.NOT_APPLICABLE),
        "upload_id": FieldSchema("upload_id", "int?", Status.NOT_APPLICABLE),
        "upload_id_str": FieldSchema("upload_id_str", "str?", Status.NOT_APPLICABLE),
        "start_latlng": FieldSchema("start_latlng", "list?", Status.NOT_APPLICABLE),
        "end_latlng": FieldSchema("end_latlng", "list?", Status.NOT_APPLICABLE),
        "elev_high": FieldSchema("elev_high", "float?", Status.NOT_APPLICABLE),
        "elev_low": FieldSchema("elev_low", "float?", Status.NOT_APPLICABLE),
        "trainer": FieldSchema("trainer", "bool", Status.NOT_APPLICABLE),
        "commute": FieldSchema("commute", "bool", Status.NOT_APPLICABLE),
        "manual": FieldSchema("manual", "bool", Status.NOT_APPLICABLE),
        "private": FieldSchema("private", "bool", Status.NOT_APPLICABLE),
        "visibility": FieldSchema("visibility", "str", Status.NOT_APPLICABLE),
        "flagged": FieldSchema("flagged", "bool", Status.NOT_APPLICABLE),
        "timezone": FieldSchema("timezone", "str", Status.NOT_APPLICABLE),
        "utc_offset": FieldSchema("utc_offset", "float", Status.NOT_APPLICABLE),
        "location_city": FieldSchema("location_city", "str?", Status.NOT_APPLICABLE),
        "location_state": FieldSchema("location_state", "str?", Status.NOT_APPLICABLE),
        "location_country": FieldSchema("location_country", "str?", Status.NOT_APPLICABLE),
        "achievement_count": FieldSchema("achievement_count", "int", Status.NOT_APPLICABLE),
        "kudos_count": FieldSchema("kudos_count", "int", Status.NOT_APPLICABLE),
        "comment_count": FieldSchema("comment_count", "int", Status.NOT_APPLICABLE),
        "athlete_count": FieldSchema("athlete_count", "int", Status.NOT_APPLICABLE),
        "photo_count": FieldSchema("photo_count", "int", Status.NOT_APPLICABLE),
        "total_photo_count": FieldSchema("total_photo_count", "int", Status.NOT_APPLICABLE),
        "pr_count": FieldSchema("pr_count", "int", Status.NOT_APPLICABLE),
        "has_kudoed": FieldSchema("has_kudoed", "bool", Status.NOT_APPLICABLE),
        "heartrate_opt_out": FieldSchema("heartrate_opt_out", "bool", Status.NOT_APPLICABLE),
        "display_hide_heartrate_option": FieldSchema("display_hide_heartrate_option", "bool", Status.NOT_APPLICABLE),
        "from_accepted_tag": FieldSchema("from_accepted_tag", "bool", Status.NOT_APPLICABLE),
    },
)

# ─── DetailedActivity extras (GET /activities/{id}) ───
# NOTE: DetailedActivity includes ALL SummaryActivity fields PLUS these extras.

DETAILED_ACTIVITY = EndpointSchema(
    name="detailed_activity",
    endpoint="GET /activities/{id}",
    fields={
        **SUMMARY_ACTIVITY.fields,  # Inherits all SummaryActivity fields
        # 🔵 Available, not used yet
        "description": FieldSchema("description", "str?", Status.FREE_UNUSED),
        "calories": FieldSchema("calories", "float?", Status.FREE_UNUSED, "kcal"),
        "best_efforts": FieldSchema("best_efforts", "list", Status.FREE_UNUSED),
        "splits_metric": FieldSchema("splits_metric", "list", Status.FREE_UNUSED, "per-km with GAP"),
        "splits_standard": FieldSchema("splits_standard", "list", Status.FREE_UNUSED, "per-mile"),
        "laps": FieldSchema("laps", "list", Status.FREE_UNUSED),
        "segment_efforts": FieldSchema("segment_efforts", "list", Status.FREE_UNUSED),
        "gear": FieldSchema("gear", "dict", Status.FREE_UNUSED),
        "similar_activities": FieldSchema("similar_activities", "dict", Status.FREE_UNUSED, "trend analysis"),
        # 💰 Summit-only
        "prefer_perceived_exertion": FieldSchema(
            "prefer_perceived_exertion", "bool?", Status.SUMMIT, summit_null_value=None
        ),
        "available_zones": FieldSchema("available_zones", "list", Status.SUMMIT, summit_null_value=[]),
        # ⬜ Not used
        "hide_from_home": FieldSchema("hide_from_home", "bool", Status.NOT_APPLICABLE),
        "embed_token": FieldSchema("embed_token", "str", Status.NOT_APPLICABLE),
        "photos": FieldSchema("photos", "dict", Status.NOT_APPLICABLE),
        "stats_visibility": FieldSchema("stats_visibility", "list", Status.NOT_APPLICABLE),
    },
)

# ─── Streams (GET /activities/{id}/streams) ───

STREAMS = EndpointSchema(
    name="streams",
    endpoint="GET /activities/{id}/streams",
    fields={
        # ✅ Actively consumed
        "time": FieldSchema("time", "dict", Status.FREE_USED, "{data:[...], series_type, original_size, resolution}"),
        "heartrate": FieldSchema("heartrate", "dict", Status.FREE_USED),
        "velocity_smooth": FieldSchema("velocity_smooth", "dict", Status.FREE_USED),
        "altitude": FieldSchema("altitude", "dict", Status.FREE_USED),
        "cadence": FieldSchema("cadence", "dict", Status.FREE_USED),
        "latlng": FieldSchema("latlng", "dict", Status.FREE_USED),
        "grade_smooth": FieldSchema("grade_smooth", "dict", Status.FREE_USED),
        "distance": FieldSchema("distance", "dict", Status.FREE_USED),
        "moving": FieldSchema("moving", "dict", Status.FREE_USED),
        # 🔵 Available, not used yet
        "grade_adjusted_speed": FieldSchema("grade_adjusted_speed", "dict", Status.FREE_UNUSED, "Run only GAP"),
        "grade_adjusted_distance": FieldSchema("grade_adjusted_distance", "dict", Status.FREE_UNUSED, "Run only"),
        # ❌ Not available from our device
        # 'temp', 'watts', 'velocity' — documented but never returned
    },
)


# ─── Registry ───

SCHEMA_REGISTRY: dict[str, EndpointSchema] = {
    "summary_activity": SUMMARY_ACTIVITY,
    "detailed_activity": DETAILED_ACTIVITY,
    "streams": STREAMS,
}


# ═══════════════════════════════════════════════════════════════════
#  Validator
# ═══════════════════════════════════════════════════════════════════


def validate_response(
    data: dict[str, Any],
    endpoint_name: str,
) -> ValidationResult:
    """
    Validate a Strava API response against the known schema.

    Args:
        data: Raw JSON dict from the API
        endpoint_name: One of 'summary_activity', 'detailed_activity', 'streams'

    Returns:
        ValidationResult with unknown_fields and active_summit lists.
    """
    schema = SCHEMA_REGISTRY.get(endpoint_name)
    if not schema:
        return ValidationResult(
            endpoint=f"unknown:{endpoint_name}",
            unknown_fields=[{"field": "schema_not_found", "value_type": str(type(data))}],
        )

    return ValidationResult(
        endpoint=schema.endpoint,
        unknown_fields=schema.unknown_keys(data),
        active_summit=schema.active_summit_fields(data),
    )


def validate_batch(
    items: list[dict[str, Any]],
    endpoint_name: str,
    max_samples: int = 3,
) -> ValidationResult:
    """
    Validate the first few items of a list response (summary activities).
    Only checks max_samples to avoid overhead on large pages.
    """
    schema = SCHEMA_REGISTRY.get(endpoint_name)
    if not schema:
        return ValidationResult(endpoint=f"unknown:{endpoint_name}")

    # Collect findings from first N items
    all_unknown = {}
    all_summit = {}
    for _i, item in enumerate(items[:max_samples]):
        if not isinstance(item, dict):
            continue
        for f in schema.unknown_keys(item):
            all_unknown[f["field"]] = f
        for f in schema.active_summit_fields(item):
            all_summit[f["field"]] = f

    return ValidationResult(
        endpoint=schema.endpoint,
        unknown_fields=list(all_unknown.values()),
        active_summit=list(all_summit.values()),
    )
