"""Semantic source hashing for DuckDB mirror provenance."""

import hashlib
import json
from datetime import date
from typing import cast

NON_SEMANTIC_SOURCE_KEYS = frozenset(
    {
        "synced_at",
        "fetched_at",
        "timestamp",
        "updated_at",
        "modified_at",
        "batch_id",
        # Strava summary payloads can include this string duplicate of ``id``.
        # It is useful for API clients, but not a semantic training-data change.
        "id_str",
    }
)


def loads_json_if_possible(value: object) -> object:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        # json.loads returns Any; pin it to object here so the parsed value stays
        # opaque to callers.
        return cast("object", json.loads(stripped))
    except json.JSONDecodeError:
        return value


def canonical_semantic_value(value: object) -> object:
    value = loads_json_if_possible(value)
    if isinstance(value, dict):
        return {
            str(key): canonical_semantic_value(item)
            for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
            if str(key).lower() not in NON_SEMANTIC_SOURCE_KEYS
        }
    if isinstance(value, list):
        return [canonical_semantic_value(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


def semantic_json_hash(value: object) -> str:
    payload = json.dumps(
        canonical_semantic_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def raw_payload_hash(payload_json: str) -> str:
    """Hash the exact persisted source payload string."""
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def summary_payload_changed(stored_summary_json: object, new_summary_json: object) -> bool:
    """True when two Strava summary payloads differ in semantic content.

    Compares canonicalized content (sorted keys, non-semantic keys like
    synced_at/fetched_at dropped) so that re-syncing an unchanged activity is
    not treated as a change. The daily refresh re-sees the same ~600 activities
    every cycle; rewriting an unchanged PRIMARY-KEY-indexed row churns the
    DuckDB ART index, which bloats the file (freed index blocks are never
    reused) and re-triggers the upstream ART stale-update-read corruption.

    A plain string-equality fast path covers the common case (Strava returns
    byte-identical JSON for an unchanged activity); the semantic hash is the
    fallback that tolerates key reordering or whitespace differences.
    """
    if stored_summary_json is None:
        return True
    if stored_summary_json == new_summary_json:
        return False
    return semantic_json_hash(stored_summary_json) != semantic_json_hash(new_summary_json)
