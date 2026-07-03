"""Shared SQL fragments for bronze-hydrated activity reads."""

from __future__ import annotations


def activity_hydration_joins(activity_alias: str = "a") -> str:
    return f"""
        LEFT JOIN bronze.latest_activity_payloads summary_payload
          ON summary_payload.activity_id = {activity_alias}.id
         AND summary_payload.payload_kind = 'summary'
        LEFT JOIN bronze.latest_activity_payloads detail_payload
          ON detail_payload.activity_id = {activity_alias}.id
         AND detail_payload.payload_kind = 'detail'
    """


def hydrated_activity_select(activity_alias: str = "a") -> str:
    return f"""
        {activity_alias}.id,
        COALESCE(summary_payload.activity_day, {activity_alias}.activity_day) AS activity_day,
        COALESCE(json_extract_string(summary_payload.payload_json, '$.name'), {activity_alias}.name, '') AS name,
        COALESCE(
            json_extract_string(summary_payload.payload_json, '$.sport_type'),
            {activity_alias}.sport_type,
            'Unknown'
        ) AS sport_type,
        COALESCE(
            TRY_CAST(json_extract_string(summary_payload.payload_json, '$.distance') AS DOUBLE),
            {activity_alias}.distance,
            0
        ) AS distance,
        COALESCE(
            TRY_CAST(json_extract_string(summary_payload.payload_json, '$.moving_time') AS BIGINT),
            {activity_alias}.moving_time,
            0
        ) AS moving_time,
        COALESCE(
            TRY_CAST(json_extract_string(summary_payload.payload_json, '$.elapsed_time') AS BIGINT),
            {activity_alias}.elapsed_time,
            0
        ) AS elapsed_time,
        COALESCE(
            TRY_CAST(
                json_extract_string(summary_payload.payload_json, '$.total_elevation_gain') AS DOUBLE
            ),
            {activity_alias}.total_elevation_gain,
            0
        ) AS total_elevation_gain,
        COALESCE(summary_payload.payload_json, {activity_alias}.summary_json) AS summary_json,
        COALESCE(detail_payload.payload_json, {activity_alias}.detail_json) AS detail_json,
        COALESCE(summary_payload.fetched_at, {activity_alias}.synced_at) AS synced_at
    """


def hydrated_activity_group_by(activity_alias: str = "a") -> str:
    return f"""
        {activity_alias}.id,
        {activity_alias}.activity_day,
        {activity_alias}.name,
        {activity_alias}.sport_type,
        {activity_alias}.distance,
        {activity_alias}.moving_time,
        {activity_alias}.elapsed_time,
        {activity_alias}.total_elevation_gain,
        summary_payload.activity_day,
        summary_payload.fetched_at,
        summary_payload.payload_json,
        {activity_alias}.summary_json,
        detail_payload.payload_json,
        {activity_alias}.detail_json,
        {activity_alias}.synced_at
    """


def hydrated_activity_fact_select(activity_alias: str = "a") -> str:
    return f"""
        COALESCE(json_extract_string(summary_payload.payload_json, '$.name'), {activity_alias}.name, '') AS activity_name,
        COALESCE(summary_payload.activity_day, {activity_alias}.activity_day) AS activity_date,
        COALESCE(summary_payload.payload_json, {activity_alias}.summary_json) AS summary_json,
        COALESCE(detail_payload.payload_json, {activity_alias}.detail_json) AS detail_json
    """
