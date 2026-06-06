from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HrRecovery:
    """HR recovery analysis from pauses during an activity.

    median_rate is the primary metric (bpm/min).
    """

    pauses_found: int
    total_rest_sec: int
    median_rate: float | None  # bpm/min — main metric
    best_rate: float | None
    worst_rate: float | None
    avg_rate: float | None


@dataclass
class VerticalSpeed:
    """Vertical ascent speed."""

    vmh: int  # metres per hour of ascent
    total_ascent_m: float
    duration_hours: float


@dataclass
class DecouplingResult:
    """Heart-rate drift between first and second half of activity.

    decoupling_pct is None when:
    - Not enough data (<120 stream points)
    - Pace too variable (CV > PACE_CV_MAX) — decoupling requires steady effort
    """

    decoupling_pct: float | None
    pace_too_variable: bool = False


@dataclass
class CardiacDriftResult:
    """Intra-activity cardiac drift via Jenks pace clustering.

    Compares median HR in early vs late temporal segments within each
    auto-detected pace cluster (Jenks natural breaks).

    drift_pct is None when:
    - <120 stream points
    - No clusters with ≥2 temporal segments
    - No HR/velocity data available
    """

    drift_pct: float | None  # weighted drift % across clusters
    severity: str | None  # 'stable' | 'borderline' | 'moderate' |
    # 'significant' | 'severe'
    quality: str = "low"  # 'good' (≥10min data) | 'fair' (≥5min) | 'low'
    is_significant: bool = False  # True if drift ≥ threshold AND consistency ≥ 0.6
    n_clusters: int = 0  # number of pace clusters (Jenks k)
    gvf: float = 0.0  # Goodness of Variance Fit
    cluster_count: int = 0  # clusters with valid early/late comparison
    error: str | None = None  # reason when drift can't be computed


@dataclass
class EnrichedActivity:
    """Full enriched activity with computed metrics."""

    id: int
    date: str
    name: str
    sport_type: str
    distance_km: float
    moving_time_min: float
    elapsed_time_min: float
    elevation_m: float | None
    trimp: float
    avg_hr: float | None
    max_hr: int | None
    zone_minutes: list[float] = field(default_factory=lambda: [0.0] * 5)
    hr_recovery: HrRecovery | None = None
    vertical_speed: VerticalSpeed | None = None
    cc: float | None = None  # Cardiac Cost = avg_hr / avg_vel
    cardiac_drift: CardiacDriftResult | None = None  # intra-activity drift
    hrr_pct: float | None = None  # avg %HRR = (avg_hr − HRrest) / (HRmax − HRrest) × 100
    start_time: str | None = None  # "HH:MM" local (from start_date_local)
