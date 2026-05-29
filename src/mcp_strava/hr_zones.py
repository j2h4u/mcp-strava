"""Heart-rate zone models — an isolated, swappable strategy.

A *zone model* turns the athlete's heart-rate anchors (resting HR and maximum
HR) into the ordered upper bounds of the heart-rate zones used to compute
training load (TRIMP). It is deliberately isolated so the boundary method can
be replaced later — for example a threshold-based model derived from a lab or
field test — without touching load computation or storage.

Each model carries a stable string ``identifier``. That identifier is persisted
next to any facts the model produces, so historical facts are never silently
recomputed when the active model changes: a different model only applies to
newly computed activities.

Currently the only model is Karvonen heart-rate reserve (``karvonen_hrr``). To
add another, implement :class:`HRZoneModel` and register it in ``_MODELS``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# Upper cap that closes the top zone (Z5). No real heart rate reaches it; it
# lets the top zone be expressed as a normal "[lower, cap)" interval.
ZONE_CAP_BPM = 300


@runtime_checkable
class HRZoneModel(Protocol):
    """Strategy that derives heart-rate zone upper bounds from HR anchors."""

    identifier: str

    def zone_bounds(self, *, hr_max: int, hr_rest: int) -> list[int]:
        """Return ordered zone upper bounds (Z1..Z5 edges) plus the closing cap."""
        ...


class KarvonenHRR:
    """Karvonen heart-rate-reserve zones at fixed %HRR breakpoints.

    Each bound is ``round(hr_rest + pct * (hr_max - hr_rest))`` for ``pct`` in
    :attr:`PERCENTAGES`, followed by :data:`ZONE_CAP_BPM` to close the top zone.

    For ``hr_rest=53, hr_max=191`` this reproduces ``[122, 136, 150, 163, 177,
    300]`` — the historical hard-coded boundaries — so existing TRIMP values are
    unchanged.
    """

    identifier = "karvonen_hrr"
    PERCENTAGES: tuple[float, ...] = (0.50, 0.60, 0.70, 0.80, 0.90)

    def zone_bounds(self, *, hr_max: int, hr_rest: int) -> list[int]:
        if hr_max <= hr_rest:
            raise ValueError(f"hr_max ({hr_max}) must be greater than hr_rest ({hr_rest})")
        reserve = hr_max - hr_rest
        bounds = [round(hr_rest + pct * reserve) for pct in self.PERCENTAGES]
        bounds.append(ZONE_CAP_BPM)
        return bounds


_MODELS: dict[str, HRZoneModel] = {
    KarvonenHRR.identifier: KarvonenHRR(),
}

DEFAULT_MODEL_ID = KarvonenHRR.identifier


def known_model_ids() -> tuple[str, ...]:
    return tuple(sorted(_MODELS))


def get_zone_model(identifier: str) -> HRZoneModel:
    """Return the registered zone model, or raise with the known identifiers."""
    try:
        return _MODELS[identifier]
    except KeyError:
        raise ValueError(f"Unknown HR zone model {identifier!r}; known models: {known_model_ids()}") from None


def zone_bounds(hr_max: int, hr_rest: int, *, model_id: str = DEFAULT_MODEL_ID) -> list[int]:
    """Convenience: compute zone bounds with the named model (default Karvonen)."""
    return get_zone_model(model_id).zone_bounds(hr_max=hr_max, hr_rest=hr_rest)
