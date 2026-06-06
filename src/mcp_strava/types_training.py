from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BanisterResult:
    """Fitness-Fatigue-Form from EWMA model."""

    fitness: float
    fatigue: float
    form: float
    form_zone: str  # tired / normal / fresh


@dataclass
class SimDay:
    """One simulated day in a Banister forward projection (pure model output)."""

    date: str
    trimp: float
    fitness: float
    fatigue: float
    form: float
    weekday: str = ""
