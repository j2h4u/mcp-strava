"""Product-level aggregate metric service."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from mcp_strava.adapters.duckdb.aggregate_queries import (
    AggregateRequest,
    query_training_aggregates,
    validate_aggregate_request,
)
from mcp_strava.adapters.duckdb.connection import ReadConn
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.application.freshness import _freshness_now, build_freshness_metadata
from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.settings import get_settings
from mcp_strava.types import (
    CompletenessMetadata,
    ServiceEnvelope,
    ServiceRationale,
    ServiceWarning,
    dc_to_dict,
)


@dataclass(frozen=True)
class AggregateServiceRequest:
    metric_ids: tuple[str, ...]
    bucket: str
    start_day: str | None
    end_day_exclusive: str
    bundle_id: str | None = None
    scope: str = "global"
    sport_filter: str | None = None
    include_empty_buckets: bool = False
    as_of_day: str | None = None
    window_days: int | None = None

    def to_query_request(self) -> AggregateRequest:
        return AggregateRequest(
            metric_ids=self.metric_ids,
            bucket=self.bucket,
            start_day=self.start_day,
            end_day_exclusive=self.end_day_exclusive,
            bundle_id=self.bundle_id,
            scope=self.scope,
            sport_filter=self.sport_filter,
            include_empty_buckets=self.include_empty_buckets,
            as_of_day=self.as_of_day,
            window_days=self.window_days,
        )


def get_training_aggregates_service(
    request: AggregateServiceRequest,
    *,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    query_request = request.to_query_request()
    metric_definitions = validate_aggregate_request(query_request)
    # WR-02: checked_at here feeds only the freshness instant comparison (the
    # as_of_day calendar is carried separately on the request), so default it to a
    # UTC-naive instant to match the UTC-stored last_success_at.
    checked_at = now if now is not None else _freshness_now()
    policy = RefreshPolicy.from_settings(get_settings())
    conn_context = nullcontext(connection) if connection is not None else ReadConn()

    with conn_context as conn:
        repo = DuckDBRepository.from_connection(conn)
        # Resolve the current version ONCE and thread it through every read in
        # this request so the status envelope and the aggregate rows agree (R11).
        version = repo.current_metric_version()
        freshness = build_freshness_metadata(
            repo,
            checked_at,
            policy,
            signal_first_use=signal_first_use,
        )
        read_model = repo.read_model_status(metric_version=version)
        rows = query_training_aggregates(conn, query_request, metric_version=version)

    # dc_to_dict returns Any; annotate as dict[str, object] to kill the Any cascade.
    freshness_payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(freshness))
    row_payloads: list[dict[str, object]] = []
    missing: set[str] = set()
    row_statuses: list[str] = []
    for row in rows:
        payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(row))
        payload["mirror_freshness"] = freshness_payload
        payload["read_model_freshness"] = read_model
        row_payloads.append(payload)
        row_statuses.append(str(payload["completeness_status"]))
        reasons_raw: object = payload.get("missing_reasons", [])
        reasons: list[object] = reasons_raw if isinstance(reasons_raw, list) else []
        missing.update(str(reason) for reason in reasons)

    completeness_status = _payload_completeness(row_statuses, read_model)
    if read_model.get("status") != "current":
        stale_reason = read_model.get("stale_reason")
        missing.add(str(stale_reason or "read_model_not_current"))

    data = {
        "request": _request_payload(request),
        "metrics": [metric.metric_id for metric in metric_definitions],
        "rows": row_payloads,
    }
    bundle_payload = _product_bundle_payload(request.bundle_id, row_payloads, read_model)
    if bundle_payload is not None:
        data["bundle"] = bundle_payload

    return ServiceEnvelope(
        data=data,
        freshness=freshness,
        completeness=CompletenessMetadata(
            status=completeness_status,
            missing=sorted(reason for reason in missing if reason),
            coverage={
                "read_model": read_model,
                "row_count": len(row_payloads),
                "metric_count": len(metric_definitions),
            },
        ),
        warnings=_warnings_for_aggregate_payload(row_statuses, read_model),
        rationale=[
            ServiceRationale(
                code="prepared_metric_facts",
                message="Rows are computed from prepared local metric facts and registry metadata.",
            )
        ],
    )


def _product_bundle_payload(
    bundle_id: str | None,
    rows: list[dict[str, Any]],
    read_model: dict[str, Any],
) -> dict[str, Any] | None:
    if bundle_id is None:
        return None
    from mcp_strava.application.product_facts import format_aggregate_product_bundle

    return format_aggregate_product_bundle(bundle_id, rows, read_model=read_model)


def _request_payload(request: AggregateServiceRequest) -> dict[str, Any]:
    return {
        "metric_ids": list(request.metric_ids),
        "bundle_id": request.bundle_id,
        "bucket": request.bucket,
        "start_day": request.start_day,
        "end_day_exclusive": request.end_day_exclusive,
        "scope": request.scope,
        "sport_filter": request.sport_filter,
        "include_empty_buckets": request.include_empty_buckets,
        "as_of_day": request.as_of_day,
        "window_days": request.window_days,
    }


def _payload_completeness(row_statuses: list[str], read_model: dict[str, Any]) -> str:
    if not row_statuses:
        return "unavailable"
    if read_model.get("status") != "current":
        return "partial"
    if all(status == "complete" for status in row_statuses):
        return "complete"
    if any(status == "complete" for status in row_statuses):
        return "partial"
    if any(status == "partial" for status in row_statuses):
        return "partial"
    return "unavailable"


def _warnings_for_aggregate_payload(
    row_statuses: list[str],
    read_model: dict[str, Any],
) -> list[ServiceWarning]:
    warnings: list[ServiceWarning] = []
    if read_model.get("status") != "current":
        warnings.append(
            ServiceWarning(
                code="read_model_not_current",
                severity="warning",
                message="Prepared metric facts are not current.",
                field="read_model",
                evidence={"status": read_model.get("status"), "stale_reason": read_model.get("stale_reason")},
            )
        )
    if any(status in {"partial", "unavailable"} for status in row_statuses):
        warnings.append(
            ServiceWarning(
                code="aggregate_rows_incomplete",
                severity="warning",
                message="Some aggregate rows have incomplete source coverage.",
                field="rows",
            )
        )
    return warnings
