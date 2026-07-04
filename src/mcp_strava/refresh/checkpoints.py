"""Refresh checkpoint stages."""

from __future__ import annotations

from enum import StrEnum


class Stage(StrEnum):
    SUMMARIES = "summaries"
    STREAMS = "streams"
    DETAILS = "details"
    SCHEMA_VALIDATE = "schema_validate"
    READ_MODEL_MATERIALIZE = "read_model_materialize"
    KUDOS = "kudos"
    COMPLETE = "complete"
    STREAMS_BACKFILL = "streams_backfill"
    DETAILS_BACKFILL = "details_backfill"
    READ_MODEL_MATERIALIZE_BACKFILL = "read_model_materialize_backfill"
    COMPLETE_BACKFILL = "complete_backfill"
    STREAM_CHANNELS_BACKFILL = "stream_channels_backfill"
    COMPLETE_STREAM_CHANNELS_BACKFILL = "complete_stream_channels_backfill"


NEXT_STAGE_DAILY: dict[Stage, Stage] = {
    Stage.SUMMARIES: Stage.STREAMS,
    Stage.STREAMS: Stage.DETAILS,
    Stage.DETAILS: Stage.SCHEMA_VALIDATE,
    Stage.SCHEMA_VALIDATE: Stage.READ_MODEL_MATERIALIZE,
    Stage.READ_MODEL_MATERIALIZE: Stage.KUDOS,
    Stage.KUDOS: Stage.COMPLETE,
}

NEXT_STAGE_BACKFILL: dict[Stage, Stage] = {
    Stage.STREAMS_BACKFILL: Stage.DETAILS_BACKFILL,
    Stage.DETAILS_BACKFILL: Stage.READ_MODEL_MATERIALIZE_BACKFILL,
    Stage.READ_MODEL_MATERIALIZE_BACKFILL: Stage.COMPLETE_BACKFILL,
}


def is_active_backfill_stage(stage: str | Stage | None) -> bool:
    if stage is None:
        return False
    return str(stage) in {
        Stage.STREAMS_BACKFILL.value,
        Stage.DETAILS_BACKFILL.value,
        Stage.READ_MODEL_MATERIALIZE_BACKFILL.value,
        Stage.STREAM_CHANNELS_BACKFILL.value,
    }


def is_stream_channel_backfill_stage(stage: str | Stage | None) -> bool:
    if stage is None:
        return False
    return str(stage) in {
        Stage.STREAM_CHANNELS_BACKFILL.value,
        Stage.COMPLETE_STREAM_CHANNELS_BACKFILL.value,
    }
