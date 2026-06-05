"""Generic DuckDB repository row and scalar helpers."""

from __future__ import annotations

import re
from datetime import date

# The generic DB-API row boundary. A raw row out of DuckDB is a heterogeneous
# mapping of column name -> cell value whose static shape fetch helpers cannot
# know, so the honest type is ``dict[str, object]`` rather than ``dict[str, Any]``.
Row = dict[str, object]

_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def safe_identifier(name: str) -> str:
    if not _SQL_IDENTIFIER.match(name):
        raise ValueError(f"unsafe SQL identifier (not a bare table/column name): {name!r}")
    return name


def normalize_cell(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    return value


def as_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (float, str)):
        return int(value)
    raise TypeError(f"expected an int-like cell, got {type(value).__name__}")


def as_float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"expected a float-like cell, got {type(value).__name__}")


def as_str(value: object) -> str:
    return str(value)


def as_int_opt(value: object) -> int | None:
    """Narrow a nullable cell to ``int | None`` and preserve SQL NULL."""
    return None if value is None else as_int(value)


def as_str_opt(value: object) -> str | None:
    """Narrow a nullable cell to ``str | None`` and preserve SQL NULL."""
    return None if value is None else str(value)


def placeholders(count: int) -> str:
    return ", ".join("?" for _ in range(count))
