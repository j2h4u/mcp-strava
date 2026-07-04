"""Athlete profile and algorithm constants — single source of truth.

All tunable parameters live in the `Config` hierarchy.
Import what you need::

    from mcp_strava.constants import Config
    threshold = Config.Thresholds.PACE_CV_MAX
"""

import math as _math
from typing import ClassVar

# ═══════════════════════════════════════════════════════════════
#  Config — hierarchical constants
# ═══════════════════════════════════════════════════════════════


class Config:
    """All athlete and algorithm parameters in one place."""

    class Zones:
        """HR zones for TRIMP calculation."""

        COEFF: ClassVar[list[float]] = [0.5, 1, 2, 3, 4, 5]  # Z0 discounted (recovery), Z1-Z5 standard

    class Drift:
        """Intra-activity cardiac drift parameters (Jenks-based, May 2026).
        Per-sport thresholds from expert panel: Run=10%, TrailRun=12%,
        Hike=8% (altitude-affected), Walk=6% (low baseline → sensitive sentinel)."""

        THRESHOLD_BY_SPORT: ClassVar[dict[str, float]] = {
            "Run": 10.0,
            "TrailRun": 12.0,
            "VirtualRun": 10.0,
            "Hike": 8.0,
            "Walk": 6.0,
        }
        THRESHOLD_DEFAULT = 10.0  # fallback for unknown sport types
        MIN_CLUSTER_SIZE = 30  # minimum points per Jenks pace cluster
        MIN_SEGMENT_DURATION = 60  # minimum seconds for a contiguous segment
        OUTLIER_IQR_MULT = 2.5  # IQR multiplier for HR outlier filtering
        MAX_K = 6  # maximum pace clusters to evaluate
        GVF_THRESHOLD = 0.85  # GVF threshold for accepting classification
        MIN_JENKS_K = 2  # Jenks is undefined below 2 clusters
        GVF_MIN_K = 3  # min k before the GVF marginal-gain cutoff applies
        MIN_CLUSTER_FOR_IQR = 4  # min points per cluster for IQR (needs Q1+Q3) to be meaningful
        MIN_HALF_HR_POINTS = 5  # min HR points per half-segment for a reliable median
        MIN_SEGMENTS = 2  # need at least an early and a late segment to measure drift
        MIN_CLUSTER_DURATION_S = 120  # min effective per-cluster duration (2 min) to score drift
        QUALITY_GOOD_S = 600  # >=10 min clustered data => "good" quality label
        QUALITY_FAIR_S = 300  # >=5 min clustered data => "fair" quality label
        # Drift severity label boundaries (percent). Distinct role from THRESHOLD_BY_SPORT,
        # which is the per-sport is_significant trigger; these label the magnitude.
        SEVERITY_STABLE_MAX = 3  # below => "stable"
        SEVERITY_BORDERLINE_MAX = 5  # below => "borderline"
        SEVERITY_MODERATE_MAX = 8  # below => "moderate"
        SEVERITY_SIGNIFICANT_MAX = 12  # below => "significant"; at/above => "high"
        MIN_DRIFT_CONSISTENCY = 0.6  # fraction of clusters that must drift positive to flag significant

    class Thresholds:
        """Velocity thresholds and validity gates."""

        VEL_STOP = 0.15  # m/s — standing still (pauses, HRR)
        VEL_MOVING = 0.3  # m/s — minimum "in motion" (excludes GPS jitter)
        VEL_RUN_MIN = 1.8  # m/s — minimum for VO₂max extrapolation
        PACE_CV_MAX = 0.25  # CV above which decoupling is invalid
        # (run→walk structural change, intervals)
        ACWR_DANGER = 1.35  # age-adjusted: injury risk at 1.3+ for 50+ athletes
        ACWR_SWEET_LOW = 0.8  # acute:chronic workload ratio sweet-spot lower bound
        ACWR_SWEET_HIGH = 1.3  # acute:chronic workload ratio sweet-spot upper bound
        FORM_TIRED_BELOW = -5  # form below this => "tired"
        FORM_NORMAL_BELOW = 10  # form below this (and >= tired) => "normal"; at/above => "fresh"

    class Efficiency:
        """Cardiac efficiency and analytics parameters."""

        CC_ELEV_COEFF = 0.45  # strip ~0.45 CC per m/km elevation gain
        YOY_SHIFT_DAYS = 364  # 364 days back (52 weeks)

    class Metrics:
        """Per-activity metric calculation thresholds."""

        MIN_STREAM_POINTS = 120  # minimum second-by-second rows for valid calculation
        MIN_MOVING_TIME = 300  # seconds — minimum moving time for EF calc
        MIN_PAUSE_SEC = 30  # seconds — minimum pause duration for HRR detection
        MIN_HR_POINTS = 60  # minimum HR data points for EF calc
        MIN_ALT_POINTS = 60  # minimum altitude points for vertical speed
        MAX_PAUSE_GAP_S = 3  # max gap between stream points still treated as a contiguous pause
        MIN_VMH_HOURS = 0.05  # minimum activity duration (hours) for vertical-speed (vmh) calc

    class Plan:
        """Weekly plan parameters."""

        HIKE_TRIMP_TEMPLATE = 515  # TRIMP for a 5-6h mountain hike (mostly Z1-Z2)
        TRIMP_EASY = 80  # TRIMP ceiling for easy effort classification
        TRIMP_MEDIUM = 120  # TRIMP ceiling for medium effort classification
        TRIMP_HEAVY_DAY = 300  # TRIMP threshold for "heavy day" intensity cap
        TRIMP_WALK_RUN_BOUNDARY = 75  # below = walk-like, above = run-like (within EASY)

    class Model:
        """Training model time constants (days)."""

        PROGRESSIVE_WINDOW = 21  # days for progressive signal quality trend analysis
        PROGRESSIVE_CC_MAX_STALENESS_DAYS = 7  # per-sport CC trend must include recent data
        BANISTER_WARMUP_DAYS = 90  # days to warm up Banister model before trend analysis

        class Banister:
            TAU_FATIGUE = 10  # short-term load decay (age-adjusted: slower recovery at 50+)
            TAU_FITNESS = 42  # long-term fitness decay
            ALPHA_FATIGUE: float = 1.0 - _math.exp(_math.log(0.5) / TAU_FATIGUE)  # ≈ 0.067
            ALPHA_FITNESS: float = 1.0 - _math.exp(_math.log(0.5) / TAU_FITNESS)  # ≈ 0.016

        class ACWR:
            TAU_ATL = 7  # acute load EWMA window
            TAU_CTL = 28  # chronic load EWMA window

    class Transport:
        """Strava HTTP transport retry budget."""

        MAX_RETRIES = 3  # total attempts for data-fetch and token-refresh HTTP calls

    class Api:
        """Strava API request shape."""

        MAX_ACTIVITY_LIMIT = 200  # upper bound on the list-activities limit parameter
        STRAVA_PAGE_SIZE = 100  # activities per page; a full page implies more pages follow

    class Athlete:
        """Physiological validity bounds for athlete inputs."""

        RESTING_HR_MIN = 20  # bpm — physiological lower bound for a valid resting HR
        RESTING_HR_MAX = 120  # bpm — physiological upper bound for a valid resting HR

    class Worker:
        """Background refresh worker timing bounds."""

        MIN_POLL_INTERVAL_S = 5  # minimum allowed worker poll interval
        MIN_REFRESH_INTERVAL_S = 60  # minimum allowed refresh interval


# Sport type groups (SPORT_ALL/SPORT_RUNNING/SPORT_TRAINING) and helpers
# (is_running, get_category, ...) live in mcp_strava.sports — import them from
# there directly. constants.py no longer re-exports them (the old E402/F401
# shim is gone now that all callers import from sports).

# Individual sport type constants
SPORT_RUN = "Run"
SPORT_WALK = "Walk"
SPORT_HIKE = "Hike"
SPORT_TRAILRUN = "TrailRun"

# Walk TRIMP discount: a walk should not count at full training load in the
# Banister model. The Walk-sport portion of a day's TRIMP is multiplied by this
# factor when computing the day's EFFECTIVE TRIMP (observed stays the raw sum).
# 0.5 means walks contribute at half their measured heart-rate load.
# This is a developer-authored constant (never input-derived). It lives here in
# constants.py — a module in COMPUTE_SOURCE_MODULES — so editing this value flips
# the logic fingerprint and auto-recomputes the read model (zero-knob).
WALK_TRIMP_DISCOUNT = 0.5
