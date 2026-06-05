"""SQL fragments for TRIMP calculations over DuckDB stream rows."""

from mcp_strava.constants import Config


def build_trimp_sql(bounds: list[int], alias: str = "") -> str:
    """Build the TRIMP SQL fragment from precomputed integer zone bounds.

    Mirrors the structure of the old _build_trimp_cases() in constants.py so
    that TRIMP values are byte-identical for the same bounds. Uses
    Config.Zones.COEFF for zone weights (unchanged).

    Args:
        bounds: Ordered zone upper bounds list, e.g. [122, 136, 150, 163, 177, 300].
                Must have at least 2 elements; last element is the cap.
        alias:  Optional column alias prefix, e.g. "s." to produce "s.heartrate".

    Returns:
        SQL string ending with "/ 60.0 as trimp".
    """
    c = Config.Zones.COEFF
    h = alias
    parts = [
        f"SUM(CASE WHEN {h}heartrate < {bounds[0]} THEN 1 ELSE 0 END) * {c[0]}",
        *(
            f"SUM(CASE WHEN {h}heartrate >= {bounds[i - 1]} AND {h}heartrate < {bounds[i]} THEN 1 ELSE 0 END) * {c[i]}"
            for i in range(1, len(bounds) - 1)
        ),
        f"SUM(CASE WHEN {h}heartrate >= {bounds[-2]} THEN 1 ELSE 0 END) * {c[-1]}",
    ]
    return "(" + " +\n                ".join(parts) + ") / 60.0 as trimp"
