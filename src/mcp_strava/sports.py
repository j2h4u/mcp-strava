"""
Strava sport type registry — complete reference with analytics semantics.

All 50 types from the official Strava API (SportType enum).
Unknown types are saved but treated as non-training safe defaults.

Usage:
    from mcp_strava.sports import is_training, is_running, get_eff_windows
    from mcp_strava.sports import SPORT_TRAINING, SPORT_RUN, SPORT_WALK, ...

Each sport_type is annotated with:
  - is_training : sustained cardio that contributes to Banister/TRIMP load
  - is_running  : running biomechanics (GAP applicable, cadence in SPM)
  - eff_windows : efficiency tracking windows in days (None = not tracked)
  - category    : 'foot', 'cycle', 'water', 'winter', 'gym', 'other'
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class SportMeta:
    key: str                                    # API value: 'Run', 'TrailRun', etc.
    display: str                                # Human-readable: 'Trail Run'
    category: str                               # 'foot', 'cycle', 'water', 'winter', 'gym', 'other'
    is_training: bool = False                   # Sustained cardio → Banister/TRIMP
    is_running: bool = False                    # Running biomechanics (GAP, SPM, VO2max)
    eff_windows: Optional[Tuple[int, ...]] = None  # Efficiency tracking, None = skip
    hr_based: bool = False                      # HR data meaningful for this sport


# ═══════════════════════════════════════════════════════════════════
#  Complete Registry — all 50 Strava sport types
# ═══════════════════════════════════════════════════════════════════

SPORT_REGISTRY: Dict[str, SportMeta] = {
    # ── Foot Sports ──────────────────────────────────────────────
    'Run':       SportMeta('Run',       'Run',         'foot',
                           is_training=True, is_running=True, hr_based=True,
                           eff_windows=(7, 28, 90)),
    'TrailRun':  SportMeta('TrailRun',  'Trail Run',   'foot',
                           is_training=True, is_running=True, hr_based=True,
                           eff_windows=(7, 28, 90)),
    'VirtualRun': SportMeta('VirtualRun', 'Virtual Run', 'foot',
                            is_training=True, is_running=True, hr_based=True,
                            eff_windows=(7, 28, 90)),
    'Walk':      SportMeta('Walk',      'Walk',        'foot',
                           is_training=False, is_running=False, hr_based=True,
                           eff_windows=(7, 28)),
    'Hike':      SportMeta('Hike',      'Hike',        'foot',
                           is_training=True, is_running=False, hr_based=True,
                           eff_windows=(28, 90)),
    'Wheelchair': SportMeta('Wheelchair', 'Wheelchair', 'foot',
                            is_training=False, is_running=False, hr_based=True),

    # ── Cycle Sports ─────────────────────────────────────────────
    'Ride':              SportMeta('Ride',              'Ride',             'cycle',
                                   is_training=True, hr_based=True, eff_windows=(7, 28, 90)),
    'VirtualRide':       SportMeta('VirtualRide',       'Virtual Ride',      'cycle',
                                   is_training=True, hr_based=True, eff_windows=(7, 28, 90)),
    'MountainBikeRide':  SportMeta('MountainBikeRide',  'Mountain Bike',     'cycle',
                                   is_training=True, hr_based=True, eff_windows=(7, 28, 90)),
    'GravelRide':        SportMeta('GravelRide',        'Gravel Ride',       'cycle',
                                   is_training=True, hr_based=True, eff_windows=(7, 28, 90)),
    'EBikeRide':         SportMeta('EBikeRide',         'E-Bike Ride',       'cycle',
                                   is_training=False, hr_based=True),
    'EMountainBikeRide': SportMeta('EMountainBikeRide', 'E-MTB Ride',        'cycle',
                                   is_training=False, hr_based=True),
    'Velomobile':        SportMeta('Velomobile',        'Velomobile',        'cycle',
                                   is_training=False, hr_based=False),
    'Handcycle':         SportMeta('Handcycle',         'Handcycle',         'cycle',
                                   is_training=False, hr_based=True),

    # ── Water Sports ─────────────────────────────────────────────
    'Swim':             SportMeta('Swim',             'Swim',              'water',
                                  is_training=True, hr_based=True, eff_windows=(7, 28)),
    'VirtualRow':       SportMeta('VirtualRow',       'Virtual Row',       'water',
                                  is_training=True, hr_based=True, eff_windows=(7, 28)),
    'Rowing':           SportMeta('Rowing',           'Rowing',            'water',
                                  is_training=True, hr_based=True, eff_windows=(7, 28)),
    'Canoeing':         SportMeta('Canoeing',         'Canoe',             'water',
                                  is_training=False, hr_based=False),
    'Kayaking':         SportMeta('Kayaking',         'Kayak',             'water',
                                  is_training=True, hr_based=True, eff_windows=(28,)),
    'StandUpPaddling':  SportMeta('StandUpPaddling',  'Stand Up Paddling', 'water',
                                  is_training=True, hr_based=True, eff_windows=(28,)),
    'Kitesurf':         SportMeta('Kitesurf',         'Kitesurf',          'water',
                                  is_training=False, hr_based=False),
    'Surfing':          SportMeta('Surfing',          'Surf',              'water',
                                  is_training=False, hr_based=False),
    'Sail':             SportMeta('Sail',             'Sailing',           'water',
                                  is_training=False, hr_based=False),
    'Windsurf':         SportMeta('Windsurf',         'Windsurf',          'water',
                                  is_training=False, hr_based=False),

    # ── Winter Sports ────────────────────────────────────────────
    'NordicSki':       SportMeta('NordicSki',       'Nordic Ski',       'winter',
                                  is_training=True, hr_based=True, eff_windows=(7, 28, 90)),
    'BackcountrySki':  SportMeta('BackcountrySki',  'Backcountry Ski',  'winter',
                                  is_training=True, hr_based=True, eff_windows=(28, 90)),
    'Snowshoe':        SportMeta('Snowshoe',        'Snowshoe',         'winter',
                                  is_training=True, hr_based=True, eff_windows=(28, 90)),
    'RollerSki':       SportMeta('RollerSki',       'Roller Ski',       'winter',
                                  is_training=True, hr_based=True, eff_windows=(7, 28, 90)),
    'AlpineSki':       SportMeta('AlpineSki',       'Alpine Ski',       'winter',
                                  is_training=False, hr_based=False),
    'Snowboard':       SportMeta('Snowboard',       'Snowboard',        'winter',
                                  is_training=False, hr_based=False),
    'IceSkate':        SportMeta('IceSkate',        'Ice Skate',        'winter',
                                  is_training=False, hr_based=False),

    # ── Gym / Indoor Cardio ──────────────────────────────────────
    'Workout':          SportMeta('Workout',          'Workout',            'gym',
                                   is_training=True, hr_based=True, eff_windows=(7, 28)),
    'Crossfit':         SportMeta('Crossfit',         'Crossfit',           'gym',
                                   is_training=True, hr_based=True, eff_windows=(7, 28)),
    'WeightTraining':   SportMeta('WeightTraining',   'Weight Training',    'gym',
                                   is_training=True, hr_based=True, eff_windows=(7, 28, 90)),
    'Elliptical':       SportMeta('Elliptical',       'Elliptical',         'gym',
                                   is_training=True, hr_based=True, eff_windows=(7, 28)),
    'StairStepper':     SportMeta('StairStepper',     'Stair Stepper',      'gym',
                                   is_training=True, hr_based=True, eff_windows=(7, 28)),
    'HighIntensityIntervalTraining':
                         SportMeta('HighIntensityIntervalTraining', 'HIIT', 'gym',
                                   is_training=True, hr_based=True, eff_windows=(7, 28)),
    'Yoga':             SportMeta('Yoga',             'Yoga',               'gym',
                                   is_training=False, hr_based=True),
    'Pilates':          SportMeta('Pilates',          'Pilates',            'gym',
                                   is_training=False, hr_based=False),

    # ── Other Sports ─────────────────────────────────────────────
    'Golf':             SportMeta('Golf',             'Golf',               'other'),
    'RockClimbing':     SportMeta('RockClimbing',     'Rock Climb',         'other'),
    'InlineSkate':      SportMeta('InlineSkate',      'Inline Skate',       'other'),
    'Skateboard':       SportMeta('Skateboard',       'Skateboarding',      'other'),
    'Soccer':           SportMeta('Soccer',           'Football (Soccer)',  'other',
                                   is_training=True, hr_based=True, eff_windows=(7, 28)),
    'Tennis':           SportMeta('Tennis',           'Tennis',             'other',
                                   is_training=True, hr_based=True, eff_windows=(7, 28)),
    'Badminton':        SportMeta('Badminton',        'Badminton',          'other'),
    'Pickleball':       SportMeta('Pickleball',       'Pickleball',         'other'),
    'Squash':           SportMeta('Squash',           'Squash',             'other'),
    'Racquetball':      SportMeta('Racquetball',      'Racquetball',        'other'),
    'TableTennis':      SportMeta('TableTennis',      'Table Tennis',       'other'),
}

# Verify we have all 50
assert len(SPORT_REGISTRY) == 50, f"Expected 50 sport types, got {len(SPORT_REGISTRY)}"


# ═══════════════════════════════════════════════════════════════════
#  Query helpers
# ═══════════════════════════════════════════════════════════════════

def _get_meta(sport_type: str) -> Optional[SportMeta]:
    """Get SportMeta for a known type, None if unknown."""
    return SPORT_REGISTRY.get(sport_type)


def is_known(sport_type: str) -> bool:
    """Is this a known Strava sport type?"""
    return sport_type in SPORT_REGISTRY


def is_training(sport_type: str) -> bool:
    """
    Does this sport contribute to Banister/TRIMP load?
    Unknown types → False (safe default).
    """
    m = _get_meta(sport_type)
    return m.is_training if m else False


def is_running(sport_type: str) -> bool:
    """
    Running biomechanics? GAP applicable, cadence in SPM.
    Unknown types → False.
    """
    m = _get_meta(sport_type)
    return m.is_running if m else False


def is_hr_based(sport_type: str) -> bool:
    """Is HR data meaningful for this sport?"""
    m = _get_meta(sport_type)
    return m.hr_based if m else False


def get_eff_windows(sport_type: str) -> Optional[Tuple[int, ...]]:
    """
    Efficiency tracking windows for this sport type.
    None → don't track efficiency for this sport.
    Unknown types → None.
    """
    m = _get_meta(sport_type)
    return m.eff_windows if m else None


def get_display(sport_type: str) -> str:
    """Human-readable name, falls back to sport_type for unknown."""
    m = _get_meta(sport_type)
    return m.display if m else sport_type


def get_category(sport_type: str) -> str:
    """Category: 'foot', 'cycle', 'water', 'winter', 'gym', 'other'."""
    m = _get_meta(sport_type)
    return m.category if m else 'other'


# ═══════════════════════════════════════════════════════════════════
#  Pre-computed groups (for SQL IN clauses, iteration)
# ═══════════════════════════════════════════════════════════════════

def _collect(attr: str) -> Tuple[str, ...]:
    """Collect sport keys where attr is True."""
    return tuple(sorted(k for k, v in SPORT_REGISTRY.items() if getattr(v, attr)))

SPORT_TRAINING: Tuple[str, ...] = _collect('is_training')
SPORT_RUNNING:  Tuple[str, ...] = _collect('is_running')
SPORT_ALL:      Tuple[str, ...] = tuple(sorted(SPORT_REGISTRY.keys()))

# Backward-compatible aliases
TRAINING_SPORTS = SPORT_TRAINING
RUNNING_SPORTS  = SPORT_RUNNING
ALL_SPORTS      = SPORT_ALL


# ═══════════════════════════════════════════════════════════════════
#  New type detection (for sync)
# ═══════════════════════════════════════════════════════════════════

def detect_new_types(sport_types: list) -> list:
    """
    Given a list of sport_type strings found in activities,
    return those NOT in the registry.

    Returns: [(sport_type, count), ...] sorted by count desc.
    """
    from collections import Counter
    c = Counter(sport_types)
    return [(s, c[s]) for s in c if s not in SPORT_REGISTRY]


# ═══════════════════════════════════════════════════════════════════
#  Sport-level efficiency config (for analytics.py)
# ═══════════════════════════════════════════════════════════════════

def build_eff_config() -> Dict[str, list]:
    """
    Build efficiency config for all sports that track it.
    Returns {sport_key: [window_days, ...]}.
    """
    cfg = {}
    for key, meta in SPORT_REGISTRY.items():
        if meta.eff_windows:
            cfg[key] = list(meta.eff_windows)
    return cfg
