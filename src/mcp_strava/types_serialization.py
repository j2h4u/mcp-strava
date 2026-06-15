from __future__ import annotations


def smart_round(value: float) -> int | float:
    """Round numeric facts for presentation without hiding small signals."""
    if value == 0:
        return 0
    magnitude = abs(value)
    if magnitude >= 10:  # noqa: PLR2004
        return round(value)
    if magnitude >= 1:
        return round(value, 1)
    if magnitude >= 0.1:  # noqa: PLR2004
        return round(value, 2)
    if magnitude >= 0.01:  # noqa: PLR2004
        return round(value, 3)
    return round(value, 4)


def dc_to_dict(obj: object, *, round_floats: bool = False) -> object:
    """Recursively convert dataclass (or list/dict of dataclasses) to plain dict.
    Safe for json.dumps()."""
    if hasattr(obj, "__dataclass_fields__"):
        dc_fields: dict[str, object] = vars(obj)
        return {k: dc_to_dict(v, round_floats=round_floats) for k, v in dc_fields.items() if k != "_raw"}
    if isinstance(obj, list):
        return [dc_to_dict(v, round_floats=round_floats) for v in obj]
    if isinstance(obj, dict):
        return {k: dc_to_dict(v, round_floats=round_floats) for k, v in obj.items()}
    if round_floats and isinstance(obj, float):
        return smart_round(obj)
    return obj
