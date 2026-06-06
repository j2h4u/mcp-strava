"""Aggregate metric metadata decoration."""

from __future__ import annotations

from dataclasses import replace

from mcp_strava.metric_registry_aggregate_data import _AGGREGATE_METADATA_BY_METRIC_ID, AGGREGATE_METRIC_BUNDLES
from mcp_strava.metric_registry_metrics import METRIC_REGISTRY


def _bundle_ids_by_metric_id(metric_id: str) -> list[str]:
    return [bundle_id for bundle_id, metric_ids in AGGREGATE_METRIC_BUNDLES.items() if metric_id in metric_ids]


def _apply_aggregate_metadata() -> None:
    known_metric_ids = set(METRIC_REGISTRY)
    for bundle_id, metric_ids in AGGREGATE_METRIC_BUNDLES.items():
        unknown = set(metric_ids) - known_metric_ids
        if unknown:
            raise ValueError(f"{bundle_id} has unknown metric ids: {sorted(unknown)}")
        missing_metadata = set(metric_ids) - set(_AGGREGATE_METADATA_BY_METRIC_ID)
        if missing_metadata:
            raise ValueError(f"{bundle_id} has metrics without aggregate metadata: {sorted(missing_metadata)}")

    for metric_id, metadata in _AGGREGATE_METADATA_BY_METRIC_ID.items():
        if metric_id not in METRIC_REGISTRY:
            raise ValueError(f"Unknown aggregate metric id: {metric_id}")
        exposed_in = list(METRIC_REGISTRY[metric_id].exposed_in)
        if "get_training_aggregates" not in exposed_in:
            exposed_in.append("get_training_aggregates")
        METRIC_REGISTRY[metric_id] = replace(
            METRIC_REGISTRY[metric_id],
            bundle_ids=_bundle_ids_by_metric_id(metric_id),
            exposed_in=exposed_in,
            **metadata,
        )


_apply_aggregate_metadata()


def _apply_compare_periods_exposure() -> None:
    compare_metrics = set(AGGREGATE_METRIC_BUNDLES["period_comparison"])
    for metric_id, metric in tuple(METRIC_REGISTRY.items()):
        exposed_in = [tool_id for tool_id in metric.exposed_in if tool_id != "compare_periods"]
        if metric_id in compare_metrics and metric.comparison_mode != "none":
            exposed_in.append("compare_periods")
        METRIC_REGISTRY[metric_id] = replace(metric, exposed_in=exposed_in)


_apply_compare_periods_exposure()
