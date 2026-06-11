"""Plain-language glossary of metric jargon, and its hard link to the metric registry.

Single source of truth for what each abbreviation / coined training term means.
Every concept declares the ``metric_ids`` it covers; the metric factory stamps the
matching ``MetricDefinition.concept`` from the inverted map, so a metric never copies
the prose and the link cannot drift. ``validate_concept_links`` enforces referential
integrity against the live registry at import time (fail-fast).

The concept knowledge lives here on purpose: a term like TSB ("Form") or TRIMP spans
many metric_ids, so a per-metric ``description`` would be the wrong grain and would
duplicate the same definition N times.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Concept:
    """One glossary entry: an abbreviation or coined term and the metrics it covers."""

    key: str
    term: str  # display heading, including the abbreviation and any friendly name
    expansion: str  # the abbreviation spelled out in full
    definition: str  # plain-language meaning (one short paragraph)
    metric_ids: tuple[str, ...]  # every metric this concept explains; the hard FK target
    formula: str | None = None  # compact precise relation, when one exists


# Insertion order is the rendered order — kept deliberate (load model first, then
# the per-activity efficiency/HR family, then trend/volume helpers).
CONCEPT_GLOSSARY: dict[str, Concept] = {
    "trimp": Concept(
        key="trimp",
        term="TRIMP",
        expansion="Training Impulse",
        definition=(
            "A single-number dose of one workout's cardiovascular load: the time spent in each "
            "heart-rate zone multiplied by that zone's weight, expressed in minutes-of-effort. "
            "Higher means a harder session."
        ),
        formula="sum(seconds in HR zone * zone weight) / 60",
        metric_ids=(
            "trimp",
            "daily_trimp",
            "weekly_trimp",
            "total_trimp_14d",
            "avg_trimp_per_day",
            "by_sport_trimp",
            "daily_avg_trimp_7d",
            "daily_avg_trimp_28d",
            "daily_avg_trimp_90d",
            "projected_daily_trimp",
            "activity_template_trimp",
        ),
    ),
    "banister": Concept(
        key="banister",
        term="Banister model",
        expansion="Banister impulse-response model",
        definition=(
            "The impulse-response model that turns daily TRIMP into two curves: a slow-moving "
            "'Fitness' (CTL) and a fast-moving 'Fatigue' (ATL). Their difference is 'Form' (TSB). "
            "It underlies get_fitness_state and project_fitness_state."
        ),
        formula="Fitness, Fatigue = EWMA(daily TRIMP); Form = Fitness - Fatigue",
        metric_ids=("banister_history",),
    ),
    "ctl": Concept(
        key="ctl",
        term="CTL — Chronic Training Load (shown as 'Fitness')",
        expansion="Chronic Training Load",
        definition=(
            "Your slow-moving fitness baseline: a long-term exponentially-weighted average of "
            "daily TRIMP. It builds over weeks of consistent training and fades just as slowly."
        ),
        formula="EWMA(daily TRIMP, TAU_FITNESS)",
        metric_ids=("fitness", "projected_fitness"),
    ),
    "atl": Concept(
        key="atl",
        term="ATL — Acute Training Load (shown as 'Fatigue')",
        expansion="Acute Training Load",
        definition=(
            "Your fast-moving fatigue: a short-term exponentially-weighted average of daily TRIMP. "
            "It spikes after hard days and decays within a few days of rest."
        ),
        formula="EWMA(daily TRIMP, TAU_FATIGUE)",
        metric_ids=("fatigue", "projected_fatigue"),
    ),
    "tsb": Concept(
        key="tsb",
        term="TSB — Training Stress Balance (shown as 'Form')",
        expansion="Training Stress Balance",
        definition=(
            "Freshness = Fitness minus Fatigue. Positive means fresh / tapered, negative means "
            "loaded / tired. The form_zone label bands it: tired < -5 <= normal < 10 <= fresh."
        ),
        formula="Fitness - Fatigue",
        metric_ids=(
            "form",
            "form_zone",
            "projected_form",
            "target_date_form",
            "post_weekend_monday_form",
        ),
    ),
    "acwr": Concept(
        key="acwr",
        term="ACWR",
        expansion="Acute:Chronic Workload Ratio",
        definition=(
            "Recent load relative to chronic load = Fatigue / Fitness. Roughly 0.8-1.3 is the "
            "'sweet spot'; well above that flags a spike in load (an injury-risk heuristic); "
            "below 0.8 suggests undertraining."
        ),
        formula="Fatigue / Fitness",
        metric_ids=("acwr", "acwr_zone", "acwr_history"),
    ),
    "cardiac_cost": Concept(
        key="cardiac_cost",
        term="Cardiac Cost (CC)",
        expansion="Cardiac Cost",
        definition=(
            "An aerobic-efficiency ratio: average heart rate divided by average speed over moving "
            "samples. Lower is more efficient (fewer heartbeats per unit of speed). The 'adjusted' "
            "variant corrects for elevation gain."
        ),
        formula="avg HR / avg speed",
        metric_ids=(
            "cardiac_cost",
            "cardiac_cost_adjusted",
            "rolling_median_cc",
            "rolling_median_cc_adj",
            "run_90d_median_cc_trend_pct",
            "efficiency_trend_pct",
            "progressive_cc_trends",
        ),
    ),
    "cardiac_drift": Concept(
        key="cardiac_drift",
        term="Cardiac Drift",
        expansion="Cardiac (heart-rate) drift",
        definition=(
            "How much heart rate creeps up over a session at the same pace: the algorithm clusters "
            "speed into pace bands and compares early-vs-late median HR within them. High drift "
            "signals fatigue, heat, dehydration, or under-recovery."
        ),
        metric_ids=(
            "cardiac_drift_pct",
            "cardiac_drift_severity",
            "cardiac_drift_significant",
            "cardiac_drift_quality",
            "rolling_median_cardiac_drift_pct",
        ),
    ),
    "hr_zones": Concept(
        key="hr_zones",
        term="HR zones",
        expansion="Heart-rate zones (5-zone model)",
        definition=(
            "Five heart-rate bands derived from resting and maximum HR. They underpin TRIMP (each "
            "zone carries a weight) and time_in_hr_zones_min. The zone model and resting HR are "
            "configurable."
        ),
        metric_ids=("time_in_hr_zones_min",),
    ),
    "hrr": Concept(
        key="hrr",
        term="HRR",
        expansion="Heart Rate Reserve (percent)",
        definition=(
            "How much of the gap between resting and maximum heart rate was used: "
            "(median HR - resting HR) / (max HR - resting HR) * 100. It normalises intensity to an "
            "individual's heart-rate range."
        ),
        formula="(HR - HR_rest) / (HR_max - HR_rest) * 100",
        metric_ids=("hrr_pct",),
    ),
    "hr_recovery": Concept(
        key="hr_recovery",
        term="HR Recovery",
        expansion="Heart-rate recovery rate",
        definition=(
            "How fast heart rate falls during rest pauses within a workout, in bpm per minute. A "
            "faster drop means better recovery / autonomic tone. Measured over detected pauses "
            "(slower than VEL_STOP, longer than MIN_PAUSE_SEC)."
        ),
        metric_ids=(
            "hr_recovery_pauses",
            "hr_recovery_total_rest_sec",
            "hr_recovery_median_bpm_per_min",
            "hr_recovery_best_bpm_per_min",
            "hr_recovery_worst_bpm_per_min",
            "hr_recovery_avg_bpm_per_min",
            "rolling_median_hr_recovery",
        ),
    ),
    "hr_anomaly": Concept(
        key="hr_anomaly",
        term="HR anomaly",
        expansion="Heart-rate anomaly",
        definition=(
            "A count of consecutive heart-rate jumps greater than 30 bpm in the stream — a "
            "data-quality / sensor-artifact signal, not a training load."
        ),
        metric_ids=("hr_anomaly_count",),
    ),
    "progressive_load": Concept(
        key="progressive_load",
        term="Progressive overload",
        expansion="Progressive-overload signal",
        definition=(
            "A scalar from 21-day quality trends: positive when training quality is improving, "
            "negative when fatigue signals worsen. It rewards a gradual, sustainable increase in load."
        ),
        metric_ids=("progressive_load_bonus",),
    ),
    "load_trend": Concept(
        key="load_trend",
        term="Load trend",
        expansion="Training-load trend",
        definition=(
            "Percent change of rolling daily TRIMP load between the current window and the previous "
            "window of equal length. Positive means ramping volume up, negative means easing off."
        ),
        metric_ids=("load_trend_pct",),
    ),
    "volume": Concept(
        key="volume",
        term="Volume",
        expansion="Training volume (here: activity count)",
        definition=(
            "In this server 'volume' means the NUMBER OF ACTIVITIES in a window (7 or 28 days), not "
            "time or distance. Do not confuse it with TRIMP (load): volume counts sessions, TRIMP "
            "measures how hard they were."
        ),
        metric_ids=("volume_7d", "volume_28d"),
    ),
}


def _build_concept_by_metric_id(glossary: Mapping[str, Concept]) -> dict[str, str]:
    """Invert the glossary into metric_id -> concept key, rejecting collisions."""
    mapping: dict[str, str] = {}
    for key, concept in glossary.items():
        for metric_id in concept.metric_ids:
            if metric_id in mapping:
                raise ValueError(
                    f"metric_id {metric_id!r} is bound to two concepts: {mapping[metric_id]!r} and {key!r}"
                )
            mapping[metric_id] = key
    return mapping


# metric_id -> concept key. Consumed by the metric factory to stamp ``concept``.
CONCEPT_BY_METRIC_ID: dict[str, str] = _build_concept_by_metric_id(CONCEPT_GLOSSARY)


def validate_concept_links(known_metric_ids: frozenset[str]) -> None:
    """Fail fast if any glossary metric_id is not a real registry metric.

    The reverse direction (every ``metric.concept`` resolves to a glossary key) holds
    by construction, because ``concept`` is stamped from this very glossary.
    """
    unknown = sorted(metric_id for metric_id in CONCEPT_BY_METRIC_ID if metric_id not in known_metric_ids)
    if unknown:
        raise ValueError(
            f"glossary references metric_ids absent from the registry: {unknown}. "
            "Fix the metric_ids tuple in metric_glossary.py or the metric_id in the registry."
        )


def render_glossary_markdown() -> str:
    """Render the glossary as the ``strava://glossary`` resource body."""
    lines = [
        "# Strava metric glossary",
        "",
        "Plain-language expansions of the abbreviations and coined terms behind this server's "
        "metrics. Each entry lists the metric ids it explains; use the metric catalog resource "
        "(`strava://metric-catalog`) for units, calculations, and the per-metric `concept` link.",
        "",
        "## Times & timezones",
        "",
        "Three distinct time references appear in this surface — do not conflate them:",
        "",
        "- **Activity dates and time-of-day are LOCAL to where the activity happened** "
        "(the athlete's timezone, from Strava `start_date_local`). `activity_date` is that local "
        "calendar day; `start_time_local` (e.g. `07:16`) is the local wall-clock start, read "
        'as-written with no conversion. So "morning run" is morning *where the workout was*, '
        "regardless of where you or the user are now.",
        "- **Operational timestamps are UTC**, suffixed with `Z`: `checked_at`, "
        "`last_successful_refresh_at`, `backoff_until`. These are mirror-freshness instants, not "
        "training times.",
        "- **`last_activity_at` is a LOCAL calendar date** (athlete tz), not a UTC instant — it has no `Z`.",
        "",
        "The MCP user's / calling agent's own timezone is deliberately **not** applied: it would "
        "distort time-of-day (a 07:00 run in one zone is not a 02:00 run just because the reader "
        "sits elsewhere). `relative_time` (e.g. `2h 5m`) is a duration, so it is timezone-agnostic.",
        "",
    ]
    for concept in CONCEPT_GLOSSARY.values():
        lines.append(f"## {concept.term}")
        lines.append(f"*{concept.expansion}*")
        lines.append("")
        lines.append(concept.definition)
        if concept.formula:
            lines.append("")
            lines.append(f"**Formula:** `{concept.formula}`")
        covered = ", ".join(f"`{metric_id}`" for metric_id in sorted(concept.metric_ids))
        lines.append("")
        lines.append(f"**Metrics:** {covered}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
