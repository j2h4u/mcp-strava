"""Raw DuckDB result-row helpers for aggregate queries."""

from __future__ import annotations

from typing import Any, cast

from mcp_strava.adapters.duckdb.connection import DuckDBConn


def _rows(result: DuckDBConn) -> list[dict[str, object]]:
    # The fetched cell tuple is ``tuple[Any, ...]``; cast it to ``tuple[object,
    # ...]`` so the assembled row maps column -> opaque ``object`` rather than
    # leaking ``Any`` into every downstream ``row[...]`` access. Callers coerce
    # each cell explicitly (``to_iso``/``int``/``float``) at the point of use.
    columns: list[str] = [item[0] for item in result.description]
    return [dict(zip(columns, cast("tuple[object, ...]", row), strict=False)) for row in result.fetchall()]


def _scalar_cell(row: tuple[Any, ...] | None, index: int = 0) -> object:
    """Return one cell from a raw ``fetchone()`` tuple as opaque ``object``.

    Centralizes the ``Any -> object`` narrowing for the status-fact queries, which
    read positional aggregate columns off a single fetched row. The bare DB-API
    tuple is ``tuple[Any, ...]``; this hands back an ``object`` the caller coerces
    (``int``/``float``/``str``/``to_iso``) explicitly.
    """
    if row is None:
        return None
    return cast("tuple[object, ...]", row)[index]


def _obj_dict(value: dict[str, Any]) -> dict[str, object]:
    """View an ``Any``-valued registry dict (``StatusFactDefinition.threshold`` /
    ``.window``) as ``dict[str, object]`` so element reads are opaque ``object``
    instead of leaking ``Any``. The registry dicts are shared contracts in
    ``types.py`` (out of this wave's scope); narrowing them at the read site
    keeps the typing local."""
    return cast("dict[str, object]", value)
