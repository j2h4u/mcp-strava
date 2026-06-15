"""
Intra-Activity Cardiac Drift Detection
======================================
Jenks Natural Breaks clustering of pace, then early-vs-late HR comparison
within each pace cluster. The Jenks DP is numpy-vectorized.
"""

import math
from dataclasses import dataclass
from typing import cast

import numpy as np

from mcp_strava.constants import Config


@dataclass(frozen=True, slots=True, kw_only=True)
class DriftParams:
    """Algorithm tuning knobs for cardiac_drift — all have Config-backed defaults."""

    min_cluster_size: int = Config.Drift.MIN_CLUSTER_SIZE
    min_segment_duration: int = Config.Drift.MIN_SEGMENT_DURATION
    drift_threshold_pct: float = Config.Drift.THRESHOLD_DEFAULT
    outlier_iqr_mult: float = Config.Drift.OUTLIER_IQR_MULT
    max_k: int = Config.Drift.MAX_K
    gvf_threshold: float = Config.Drift.GVF_THRESHOLD
    max_points: int = 600


_JENKS_FALLBACK_ERRORS = (ArithmeticError, IndexError, ValueError)

# ═══════════════════════════════════════════════════════════════════════
# JENKS NATURAL BREAKS — numpy-vectorized DP
# ═══════════════════════════════════════════════════════════════════════


def _prefix_sums(x):
    """Prefix sums of x and x² with a leading 0.

    np.cumsum is a sequential scan (not a pairwise reduction), so these match a
    plain Python running sum bit-for-bit — the vectorized DP below therefore
    yields breaks identical to the former pure-Python O(n²) version, just faster.
    """
    a = np.asarray(x, dtype=np.float64)
    cs = np.empty(a.size + 1, dtype=np.float64)
    cs2 = np.empty(a.size + 1, dtype=np.float64)
    cs[0] = 0.0
    cs2[0] = 0.0
    np.cumsum(a, out=cs[1:])
    np.cumsum(a * a, out=cs2[1:])
    return cs, cs2


def _ss_matrix(x):
    """Full sum-of-squared-deviations matrix SS[j, m] = SS of x[j:m], built once
    per series via broadcasting over cumulative sums. Entries with m <= j are NOT
    valid (the DP masks them); their nan/inf from the m==j division is never read.
    O(n²) memory (~2.9 MB at the n=600 cap) — built once and reused across all k.
    """
    cs, cs2 = _prefix_sums(x)
    n = len(x)
    rows = np.arange(n + 1)
    cols = rows
    nij = cols[None, :] - rows[:, None]
    s1 = cs[None, :] - cs[:, None]
    s2 = cs2[None, :] - cs2[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        ss = s2 - (s1 * s1) / nij
    return ss, n


def _jenks_dp(ss, n, k):
    """Vectorized Jenks DP over a precomputed SS matrix. For each class count the
    whole row of D[t] is computed as one column-wise argmin over the candidate
    matrix D[t-1][j] + SS[j, m] — O(k) Python iterations, each O(n²) numpy. argmin
    keeps the first minimum on ties, matching the former `if cost < best`.
    """
    inf = float("inf")
    cost_d = np.full((k + 1, n + 1), inf)
    back = np.zeros((k + 1, n + 1), dtype=np.int64)
    # Valid split point j must satisfy j < m; mask the rest to +inf once.
    j_ge_m = np.arange(n + 1)[:, None] >= np.arange(n + 1)[None, :]

    cost_d[1, 1:] = ss[0, 1:]  # one class over x[0:m]
    for t in range(2, k + 1):
        cand = cost_d[t - 1][:, None] + ss  # cand[j, m] = D[t-1][j] + SS[j, m]
        cand[: t - 1, :] = inf  # j must be >= t-1 (earlier classes need >=1 point each)
        cand[j_ge_m] = inf
        cost_d[t] = cand.min(axis=0)
        back[t] = cand.argmin(axis=0)

    boundaries = [0] * (k + 1)
    boundaries[k] = n
    m = n
    for t in range(k, 0, -1):
        m = int(cast("int", back[t, m]))
        boundaries[t - 1] = m

    sdcm = float(cost_d[k, n])
    sdam = float(ss[0, n])
    gvf = (sdam - sdcm) / sdam if sdam > 0 else 1.0
    return boundaries, sdcm, sdam, gvf


def jenks_breaks(x, k):
    """Jenks Natural Breaks for 1D sorted list x into k classes.

    Returns (boundaries, sdcm, sdam, gvf). Fully vectorized; results are identical
    to the prior pure-Python O(k·n²) DP.
    """
    if k < Config.Drift.MIN_JENKS_K:
        raise ValueError("k must be >= 2")
    ss, n = _ss_matrix(x)
    return _jenks_dp(ss, n, min(k, n))


def auto_jenks(x, max_k=6, gvf_threshold=0.85, gvf_gain_min=0.03, min_cluster_size=30):
    """Auto-determine optimal k using GVF. The O(n²) SS matrix is built once here
    and reused across every candidate k (the DP is numpy-vectorized)."""
    n = len(x)
    k_results = []
    prev_gvf = 0.0
    best_k = 1
    best_boundaries = [0, n]
    ss, _ = _ss_matrix(x)

    for k in range(2, min(max_k, n // min_cluster_size, n) + 1):
        try:
            boundaries, _sdcm, _sdam, gvf = _jenks_dp(ss, n, min(k, n))
            sizes = [boundaries[i + 1] - boundaries[i] for i in range(k)]
            min_sz = min(sizes)
            k_results.append((k, gvf, min_sz))
            if min_sz < min_cluster_size:
                continue
            gvf_gain = gvf - prev_gvf
            best_k = k
            best_boundaries = boundaries
            if gvf >= gvf_threshold:
                break
            if gvf_gain < gvf_gain_min and k >= Config.Drift.GVF_MIN_K:
                break
            prev_gvf = gvf
        except _JENKS_FALLBACK_ERRORS:
            break

    if best_k == 1:
        try:
            best_boundaries, _, _, gvf = _jenks_dp(ss, n, min(2, n))
            best_k = 2
        except _JENKS_FALLBACK_ERRORS:
            gvf = 1.0

    gvf_final = k_results[-1][1] if k_results else 1.0
    return best_boundaries, best_k, gvf_final, k_results


# ═══════════════════════════════════════════════════════════════════════
# HELPERS — pure Python
# ═══════════════════════════════════════════════════════════════════════


def _median(vals):
    """Median of a sorted list."""
    n = len(vals)
    if n == 0:
        return 0
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2


def _percentile(vals, p):
    """p-th percentile (p in 0..100) of a sorted list, linear interpolation."""
    n = len(vals)
    if n == 0:
        return 0
    if n == 1:
        return vals[0]
    rank = p / 100 * (n - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return vals[lo]
    frac = rank - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def extract_contiguous_runs(mask, min_duration=60):
    """Extract contiguous True runs from boolean list."""
    runs = []
    n = len(mask)
    i = 0
    while i < n:
        if mask[i]:
            start = i
            while i < n and mask[i]:
                i += 1
            duration = i - start
            if duration >= min_duration:
                runs.append((start, i, duration))
        else:
            i += 1
    return runs


def _filter_hr_outliers(heartrate, cluster_labels, n_clusters, outlier_iqr_mult=2.5):
    """Filter HR outliers per cluster using IQR. Pure Python."""
    hr_filt = list(heartrate)
    for c in range(n_clusters):
        mask = [i for i, lbl in enumerate(cluster_labels) if lbl == c]
        if len(mask) < Config.Drift.MIN_CLUSTER_FOR_IQR:
            continue
        hr_c = sorted(heartrate[i] for i in mask)
        q25 = _percentile(hr_c, 25)
        q75 = _percentile(hr_c, 75)
        iqr = q75 - q25
        lower = q25 - outlier_iqr_mult * iqr
        upper = q75 + outlier_iqr_mult * iqr
        med = _median(hr_c)
        for i in mask:
            if heartrate[i] < lower or heartrate[i] > upper:
                hr_filt[i] = med
    return hr_filt


# ═══════════════════════════════════════════════════════════════════════
# MAIN ALGORITHM — private stage helpers
# ═══════════════════════════════════════════════════════════════════════


def _subsample_streams(hr, vel, time_offset, max_points):
    """Subsample hr/vel/time_offset evenly to at most max_points entries.

    Returns (hr, vel, time_offset, n, subsample_step).
    """
    n = len(hr)
    subsample_step = 1
    if max_points and n > max_points:
        subsample_step = max(n // max_points, 1)
        idxs = list(range(0, n, subsample_step))[:max_points]
        hr = [hr[i] for i in idxs]
        vel = [vel[i] for i in idxs]
        time_offset = [time_offset[i] for i in idxs]
        n = len(hr)
    return hr, vel, time_offset, n, subsample_step


def _cluster_velocity(vel, n, max_k, gvf_threshold, min_cluster_pts):
    """Run auto-Jenks on velocity and return per-point cluster labels.

    Returns (cluster_labels, k_opt, gvf, k_results).
    """
    vel_with_idx = [(vel[i], i) for i in range(n)]
    vel_with_idx.sort(key=lambda x: x[0])
    sorted_idx = [item[1] for item in vel_with_idx]
    vel_sorted = [item[0] for item in vel_with_idx]

    boundaries, k_opt, gvf, k_results = auto_jenks(
        vel_sorted,
        max_k=max_k,
        gvf_threshold=gvf_threshold,
        gvf_gain_min=0.03,
        min_cluster_size=min_cluster_pts,
    )

    cluster_labels = [0] * n
    for c_idx in range(k_opt):
        start = boundaries[c_idx]
        end = boundaries[c_idx + 1]
        for idx in sorted_idx[start:end]:
            cluster_labels[idx] = c_idx

    return cluster_labels, k_opt, gvf, k_results


def _resolve_segments(segs):
    """Ensure at least 2 usable segments: split a single run in half if needed.

    Returns the (possibly modified) segment list, or None when < MIN_SEGMENTS.
    """
    if len(segs) == 0:
        return None
    if len(segs) == 1:
        s, e, dur = segs[0]
        mid = s + dur // 2
        segs = [(s, mid, dur // 2), (mid, e, dur - dur // 2)]
    if len(segs) < Config.Drift.MIN_SEGMENTS:
        return None
    return segs


def _compute_cluster_drift(c, segs, hr_filtered, vel, cluster_labels, n, subsample_step):
    """Compute drift for a single velocity cluster.

    Returns (drift_pct, weight, detail_dict) or None if quality gates fail.
    """
    mid = max(1, len(segs) // 2)
    early_segs = segs[:mid]
    late_segs = segs[mid:]

    early_indices = [i for s, e, _ in early_segs for i in range(s, e)]
    late_indices = [i for s, e, _ in late_segs for i in range(s, e)]

    early_hr_vals = sorted(hr_filtered[i] for i in early_indices)
    late_hr_vals = sorted(hr_filtered[i] for i in late_indices)

    if len(early_hr_vals) < Config.Drift.MIN_HALF_HR_POINTS or len(late_hr_vals) < Config.Drift.MIN_HALF_HR_POINTS:
        return None

    cluster_duration_s = sum(e - s for s, e, _ in segs) * subsample_step
    if cluster_duration_s < Config.Drift.MIN_CLUSTER_DURATION_S:
        return None

    early_hr = _median(early_hr_vals)
    late_hr = _median(late_hr_vals)

    if early_hr <= 0:
        return None

    drift_pct = (late_hr - early_hr) / early_hr * 100.0
    vel_mask = [cluster_labels[i] == c for i in range(n)]
    cluster_vel = [vel[i] for i, m in enumerate(vel_mask) if m]
    weight = sum(vel_mask)

    detail = {
        "cluster_id": c,
        "velocity_min": round(min(cluster_vel), 3),
        "velocity_max": round(max(cluster_vel), 3),
        "velocity_median": round(_median(sorted(cluster_vel)), 3),
        "n_segments": len(segs),
        "total_duration_s": weight,
        "early_hr": round(early_hr, 1),
        "late_hr": round(late_hr, 1),
        "drift_pct": round(drift_pct, 2),
    }
    return drift_pct, weight, detail


def _aggregate_drift(cluster_drifts, drift_threshold_pct):
    """Weighted-average drift and consistency from per-cluster (drift, weight) pairs.

    Returns (drift_weighted_pct, drift_consistency, is_significant).
    """
    drifts = [d for d, _ in cluster_drifts]
    weights = [w for _, w in cluster_drifts]
    total_w = sum(weights)
    drift_weighted_pct = sum(d * w for d, w in zip(drifts, weights, strict=False)) / total_w if total_w > 0 else 0
    drift_consistency = sum(1 for d in drifts if d > 0) / len(drifts)
    return drift_weighted_pct, drift_consistency


def _quality_label(segments_by_cluster, subsample_step):
    """Derive quality label from total clustered duration."""
    total_dur_s = sum(sum(e - s for s, e, _ in segs) for segs in segments_by_cluster) * subsample_step
    if total_dur_s >= Config.Drift.QUALITY_GOOD_S:
        return "good"
    if total_dur_s >= Config.Drift.QUALITY_FAIR_S:
        return "fair"
    return "low"


def _severity_and_significance(drift_weighted_pct, drift_consistency, drift_threshold_pct):
    """Classify severity and significance from weighted drift.

    Negative drift = warmup/HR-settling (not fatigue) → always stable/not-significant.
    Returns (severity, is_significant).
    """
    if drift_weighted_pct <= 0:
        return "stable", False

    ad = drift_weighted_pct
    if ad < Config.Drift.SEVERITY_STABLE_MAX:
        severity = "stable"
    elif ad < Config.Drift.SEVERITY_BORDERLINE_MAX:
        severity = "borderline"
    elif ad < Config.Drift.SEVERITY_MODERATE_MAX:
        severity = "moderate"
    elif ad < Config.Drift.SEVERITY_SIGNIFICANT_MAX:
        severity = "significant"
    else:
        severity = "severe"

    is_significant = (ad >= drift_threshold_pct) and (drift_consistency >= Config.Drift.MIN_DRIFT_CONSISTENCY)
    return severity, is_significant


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════


def cardiac_drift(
    heartrate,
    velocity,
    time_offset=None,
    params: DriftParams | None = None,
):
    """Intra-activity cardiac drift via Jenks pace clustering.

    Args:
        heartrate: iterable of HR values (bpm)
        velocity: iterable of velocity values (m/s)
        time_offset: optional iterable of time offsets (seconds); defaults to range(n)
        params: DriftParams with algorithm tuning knobs; uses Config-backed defaults if None.

    Returns:
        dict with drift_weighted_pct, is_significant, severity, etc.
    """
    p = params if params is not None else DriftParams()
    min_cluster_size = p.min_cluster_size
    min_segment_duration = p.min_segment_duration
    drift_threshold_pct = p.drift_threshold_pct
    outlier_iqr_mult = p.outlier_iqr_mult
    max_k = p.max_k
    gvf_threshold = p.gvf_threshold
    max_points = p.max_points
    hr = list(heartrate)
    vel = list(velocity)
    n = len(hr)

    if n < Config.Metrics.MIN_STREAM_POINTS:
        return {
            "drift_weighted_pct": None,
            "drift_consistency": None,
            "is_significant": False,
            "severity": "stable",
            "quality": "low",
            "error": "Too few data points (<120)",
            "n_clusters": 0,
            "gvf": 0.0,
            "cluster_details": [],
            "diagnostic": {},
        }

    if time_offset is None:
        time_offset = list(range(n))

    hr, vel, time_offset, n, subsample_step = _subsample_streams(hr, vel, time_offset, max_points)

    # Scale duration thresholds to subsampled point spacing
    # (min_segment_duration is in seconds, but extract_contiguous_runs counts points)
    min_dur_pts = max(2, min_segment_duration // subsample_step)
    min_cluster_pts = max(10, min_cluster_size // subsample_step)

    cluster_labels, k_opt, gvf, k_results = _cluster_velocity(vel, n, max_k, gvf_threshold, min_cluster_pts)

    hr_filtered = _filter_hr_outliers(hr, cluster_labels, k_opt, outlier_iqr_mult)

    segments_by_cluster = []
    for c in range(k_opt):
        mask = [lbl == c for lbl in cluster_labels]
        segs = extract_contiguous_runs(mask, min_duration=min_dur_pts)
        segments_by_cluster.append(segs)

    cluster_drifts = []
    cluster_details = []
    for c in range(k_opt):
        segs = _resolve_segments(segments_by_cluster[c])
        if segs is None:
            continue
        result = _compute_cluster_drift(c, segs, hr_filtered, vel, cluster_labels, n, subsample_step)
        if result is None:
            continue
        drift_pct, weight, detail = result
        cluster_drifts.append((drift_pct, weight))
        cluster_details.append(detail)

    if len(cluster_drifts) == 0:
        return {
            "drift_weighted_pct": None,
            "drift_consistency": None,
            "is_significant": False,
            "severity": "stable",
            "quality": "low",
            "error": "No clusters with ≥2 segments",
            "n_clusters": k_opt,
            "gvf": round(gvf, 4),
            "cluster_details": cluster_details,
            "diagnostic": {"k_results": k_results},
        }

    drift_weighted_pct, drift_consistency = _aggregate_drift(cluster_drifts, drift_threshold_pct)
    quality = _quality_label(segments_by_cluster, subsample_step)
    severity, is_significant = _severity_and_significance(drift_weighted_pct, drift_consistency, drift_threshold_pct)

    return {
        "drift_weighted_pct": round(drift_weighted_pct, 2),
        "drift_consistency": round(drift_consistency, 2),
        "is_significant": bool(is_significant),
        "severity": severity,
        "quality": quality,
        "n_clusters": k_opt,
        "gvf": round(gvf, 4),
        "cluster_details": cluster_details,
        "diagnostic": {
            "k_results": [(int(k), round(float(g), 4), int(s)) for k, g, s in k_results],
            "n_total_points": n,
            "n_filtered_points": sum(1 for i in range(n) if hr_filtered[i] != hr[i]),
        },
    }
