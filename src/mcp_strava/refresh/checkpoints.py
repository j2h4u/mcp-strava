"""Refresh checkpoint stages."""

from __future__ import annotations

from enum import StrEnum


class Stage(StrEnum):
    SUMMARIES = "summaries"
    STREAMS = "streams"
    DETAILS = "details"
    SCHEMA_VALIDATE = "schema_validate"
    KUDOS = "kudos"
    COMPLETE = "complete"
    STREAMS_BACKFILL = "streams_backfill"
    DETAILS_BACKFILL = "details_backfill"
    COMPLETE_BACKFILL = "complete_backfill"


NEXT_STAGE_DAILY: dict[Stage, Stage] = {
    Stage.SUMMARIES: Stage.STREAMS,
    Stage.STREAMS: Stage.DETAILS,
    Stage.DETAILS: Stage.SCHEMA_VALIDATE,
    Stage.SCHEMA_VALIDATE: Stage.KUDOS,
    Stage.KUDOS: Stage.COMPLETE,
}

NEXT_STAGE_BACKFILL: dict[Stage, Stage] = {
    Stage.STREAMS_BACKFILL: Stage.DETAILS_BACKFILL,
    Stage.DETAILS_BACKFILL: Stage.COMPLETE_BACKFILL,
}


def is_backfill_stage(stage: str | Stage | None) -> bool:
    if stage is None:
        return False
    return str(stage) in {Stage.STREAMS_BACKFILL.value, Stage.DETAILS_BACKFILL.value, Stage.COMPLETE_BACKFILL.value}


def is_active_backfill_stage(stage: str | Stage | None) -> bool:
    if stage is None:
        return False
    return str(stage) in {Stage.STREAMS_BACKFILL.value, Stage.DETAILS_BACKFILL.value}
