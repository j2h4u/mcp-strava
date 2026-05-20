"""Athlete profile and algorithm constants — single source of truth.

All tunable parameters live in the `Config` hierarchy.
Import what you need::

    from strava_lib.constants import Config
    threshold = Config.Thresholds.PACE_CV_MAX
"""

from datetime import datetime


# ═══════════════════════════════════════════════════════════════
#  Config — hierarchical constants
# ═══════════════════════════════════════════════════════════════

class Config:
    """All athlete and algorithm parameters in one place."""

    class Athlete:
        """Athlete profile — not tunable, derived from real data."""
        DATE_OF_BIRTH = datetime([REDACTED-DOB])  # [REDACTED-NAME], [REDACTED-DOB]
        HR_MAX = 191                            # Observed max from hike streams
        HR_REST = 53                            # Samsung Health monthly avg (May 2026)

    class Zones:
        """HR zones for TRIMP calculation (Z0 added for recovery heart rates)."""
        BOUNDS = [122, 136, 150, 163, 177, 300]   # Z0=recovery(<122), Z1-Z5 Karvonen (HRrest=53, HRmax=191)
        COEFF  = [0.5, 1, 2, 3, 4, 5]             # Z0 discounted (recovery), Z1-Z5 standard

    class Drift:
        """Intra-activity cardiac drift parameters (Jenks-based, May 2026).
        Per-sport thresholds from expert panel: Run=10%, TrailRun=12%,
        Hike=8% (altitude-affected), Walk=6% (low baseline → sensitive sentinel)."""
        THRESHOLD_BY_SPORT = {
            'Run': 10.0, 'TrailRun': 12.0, 'VirtualRun': 10.0,
            'Hike': 8.0, 'Walk': 6.0,
        }
        THRESHOLD_DEFAULT = 10.0          # fallback for unknown sport types
        MIN_CLUSTER_SIZE = 30             # minimum points per Jenks pace cluster
        MIN_SEGMENT_DURATION = 60         # minimum seconds for a contiguous segment
        OUTLIER_IQR_MULT = 2.5            # IQR multiplier for HR outlier filtering
        MAX_K = 6                          # maximum pace clusters to evaluate
        GVF_THRESHOLD = 0.85              # GVF threshold for accepting classification

    class Thresholds:
        """Velocity thresholds and validity gates."""
        VEL_STOP    = 0.15    # m/s — standing still (pauses, HRR)
        VEL_MOVING  = 0.3     # m/s — minimum "in motion" (excludes GPS jitter)
        VEL_RUN_MIN = 1.8     # m/s — minimum for VO₂max extrapolation
        PACE_CV_MAX = 0.25    # CV above which decoupling is invalid
                              # (run→walk structural change, intervals)
        ACWR_DANGER = 1.35   # age-adjusted: injury risk at 1.3+ for 50+ athletes

    class Efficiency:
        """Cardiac efficiency and analytics parameters."""
        CC_ELEV_COEFF = 0.45  # strip ~0.45 CC per m/km elevation gain
        YOY_SHIFT_DAYS = 364  # 364 days back (52 weeks)

    class Metrics:
        """Per-activity metric calculation thresholds."""
        MIN_STREAM_POINTS = 120  # minimum second-by-second rows for valid calculation
        MIN_MOVING_TIME = 300    # seconds — minimum moving time for EF calc
        MIN_PAUSE_SEC = 30       # seconds — minimum pause duration for HRR detection
        MIN_HR_POINTS = 60       # minimum HR data points for EF calc
        MIN_ALT_POINTS = 60      # minimum altitude points for vertical speed

    class Plan:
        """Weekly plan parameters."""
        HIKE_TRIMP_TEMPLATE = 515  # TRIMP for a 5-6h mountain hike (mostly Z1-Z2)
        TRIMP_EASY = 80            # TRIMP ceiling for easy effort classification
        TRIMP_MEDIUM = 120         # TRIMP ceiling for medium effort classification
        TRIMP_HEAVY_DAY = 300      # TRIMP threshold for "heavy day" intensity cap
        TRIMP_WALK_RUN_BOUNDARY = 75  # below = walk-like, above = run-like (within EASY)

        class Score:
            """Brute-force optimizer scoring weights."""
            TARGET_HIT = 100        # form in 5..15
            NEAR_LOW = 60           # form in 0..5
            NEAR_HIGH = 50          # form in 15..25
            SLIGHTLY_TIRED = 30     # form in -5..0
            TOO_FRESH = 20          # form > 25
            MISS_PENALTY = -50      # form < -5
            DEVIATION_FACTOR = 2    # penalty multiplier per point from 10
            LOAD_BONUS = 0.1        # reward per TRIMP
            PROGRESSIVE_FACTOR = 0.5  # multiplier for active TRIMP × load_bonus
            AGGRESSIVE_PENALTY = 10  # penalty for too many active days
            AGGRESSIVE_THRESHOLD = 0.6  # fraction of active days threshold
            SAFETY_CRITICAL = 30    # penalty for form < -20
            SAFETY_WARNING = 10     # penalty for form < -15
            NO_REST_PENALTY = 25    # penalty for zero rest days (age 50+)
            VARIETY_BONUS = 5       # reward per unique activity type

    class Model:
        """Training model time constants (days)."""
        PROGRESSIVE_WINDOW = 21  # days for progressive signal quality trend analysis
        BANISTER_WARMUP_DAYS = 90  # days to warm up Banister model before trend analysis
        class Banister:
            TAU_FATIGUE = 10   # short-term load decay (age-adjusted: slower recovery at 50+)
            TAU_FITNESS = 42   # long-term fitness decay
            ALPHA_FATIGUE = 1 - pow(0.5, 1.0 / TAU_FATIGUE)    # ≈ 0.067
            ALPHA_FITNESS = 1 - pow(0.5, 1.0 / TAU_FITNESS)   # ≈ 0.016
        class ACWR:
            TAU_ATL = 7        # acute load EWMA window
            TAU_CTL = 28       # chronic load EWMA window


# ═══════════════════════════════════════════════════════════════
#  Sport type groups — imported from registry (single source)
# ═══════════════════════════════════════════════════════════════
# All 50 Strava sport types defined once in sports.py.

from strava_lib.sports import (              # noqa: E402
    SPORT_TRAINING  as TRAINING_SPORTS,
    SPORT_RUNNING   as RUNNING_SPORTS,
    SPORT_ALL       as ALL_SPORTS,
    is_training,
    is_running,
    is_hr_based,
    get_eff_windows,
    build_eff_config,
    detect_new_types,
    get_display,
    get_category,
)

# Individual sport type constants
SPORT_RUN      = 'Run'
SPORT_WALK     = 'Walk'
SPORT_HIKE     = 'Hike'
SPORT_TRAILRUN = 'TrailRun'


# ═══════════════════════════════════════════════════════════════
#  Pre-generated TRIMP SQL fragments
# ═══════════════════════════════════════════════════════════════

def _build_trimp_cases(alias=''):
    """Build TRIMP SQL CASE expressions from Config.Zones."""
    b = Config.Zones.BOUNDS
    c = Config.Zones.COEFF
    h = alias

    zones = [f"SUM(CASE WHEN {h}heartrate < {b[0]} THEN 1 ELSE 0 END) as z1"]
    for i in range(1, len(b) - 1):
        zones.append(f"SUM(CASE WHEN {h}heartrate >= {b[i-1]} AND {h}heartrate < {b[i]} THEN 1 ELSE 0 END) as z{i+1}")
    zones.append(f"SUM(CASE WHEN {h}heartrate >= {b[-2]} THEN 1 ELSE 0 END) as z{len(b)}")

    parts = [f"SUM(CASE WHEN {h}heartrate < {b[0]} THEN 1 ELSE 0 END) * {c[0]}"]
    for i in range(1, len(b) - 1):
        parts.append(f"SUM(CASE WHEN {h}heartrate >= {b[i-1]} AND {h}heartrate < {b[i]} THEN 1 ELSE 0 END) * {c[i]}")
    parts.append(f"SUM(CASE WHEN {h}heartrate >= {b[-2]} THEN 1 ELSE 0 END) * {c[-1]}")

    trimp = "(" + " +\n                ".join(parts) + ") / 60.0 as trimp"
    zones_str = ",\n                ".join(zones)
    return zones_str, trimp


ZONES_SQL, TRIMP_SQL   = _build_trimp_cases()
ZONES_SQL_S, TRIMP_SQL_S = _build_trimp_cases('s.')

# Attach to Config for clean imports
Config.SQL = type('SQL', (), {
    'TRIMP': TRIMP_SQL,
    'ZONES': ZONES_SQL,
    'TRIMP_S': TRIMP_SQL_S,
    'ZONES_S': ZONES_SQL_S,
})()
del _build_trimp_cases  # no longer needed after module init
