"""Product-level aggregate metric service."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime

from mcp_strava.adapters.duckdb.aggregate_queries import (
    AggregateRequest,
    query_training_aggregates,
    validate_aggregate_request,
)
from mcp_strava.application.freshness import build_freshness_metadata
from mcp_strava.db import DbConn, repository_from_connection
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
    checked_at = now or datetime.now()
    policy = RefreshPolicy.from_settings(get_settings())
    conn_context = nullcontext(connection) if connection is not None else DbConn()

    with conn_context as conn:
        repo = repository_from_connection(conn)
        freshness = build_freshness_metadata(
            repo,
            checked_at,
            policy,
            signal_first_use=signal_first_use,
        )
        read_model = repo.read_model_status()
        rows = query_training_aggregates(conn, query_request)

    freshness_payload = dc_to_dict(freshness)
    row_payloads = []
    missing: set[str] = set()
    row_statuses: list[str] = []
    for row in rows:
        payload = dc_to_dict(row)
        payload["mirror_freshness"] = freshness_payload
        payload["read_model_freshness"] = read_model
        row_payloads.append(payload)
        row_statuses.append(str(payload["completeness_status"]))
        missing.update(str(reason) for reason in payload.get("missing_reasons", []))

    completeness_status = _payload_completeness(row_statuses, read_model)
    if read_model.get("status") != "current":
        stale_reason = read_model.get("stale_reason")
        missing.add(str(stale_reason or "read_model_not_current"))

    return ServiceEnvelope(
        data={
            "request": _request_payload(request),
            "metrics": [metric.metric_id for metric in metric_definitions],
            "rows": row_payloads,
        },
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


def _request_payload(request: AggregateServiceRequest) -> dict[str, object]:
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


def _payload_completeness(row_statuses: list[str], read_model: dict[str, object]) -> str:
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
    read_model: dict[str, object],
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
