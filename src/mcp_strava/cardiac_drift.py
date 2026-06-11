"""
Intra-Activity Cardiac Drift Detection
======================================
Jenks Natural Breaks clustering of pace, then early-vs-late HR comparison
within each pace cluster. The Jenks DP is numpy-vectorized.
"""

import math
from typing import cast

import numpy as np

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
    if k < 2:
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
            if gvf_gain < gvf_gain_min and k >= 3:
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
        if len(mask) < 4:
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
# MAIN ALGORITHM
# ═══════════════════════════════════════════════════════════════════════


def cardiac_drift(
    heartrate,
    velocity,
    time_offset=None,
    min_cluster_size=30,
    min_segment_duration=60,
    drift_threshold_pct=5.0,
    outlier_iqr_mult=2.5,
    max_k=6,
    gvf_threshold=0.85,
    max_points=600,
):
    """Intra-activity cardiac drift via Jenks pace clustering.

    Args:
        heartrate: iterable of HR values (bpm)
        velocity: iterable of velocity values (m/s)
        max_points: subsample evenly if N exceeds this (keeps Jenks O(n²) fast).
            Default 600 → ~250K SS entries, ~1.5M DP ops → sub-second pure Python.
        All other params: see docstring in numpy version.

    Returns:
        dict with drift_weighted_pct, is_significant, severity, etc.
    """
    # Convert to lists
    hr = list(heartrate)
    vel = list(velocity)
    n = len(hr)

    if n < 120:
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

    # Subsample evenly if too many points (keep Jenks O(n²) fast)
    subsample_step = 1
    if max_points and n > max_points:
        subsample_step = max(n // max_points, 1)
        idxs = list(range(0, n, subsample_step))[:max_points]
        hr = [hr[i] for i in idxs]
        vel = [vel[i] for i in idxs]
        time_offset = [time_offset[i] for i in idxs]
        n = len(hr)

    # Scale duration thresholds to subsampled point spacing
    # (min_segment_duration is in seconds, but extract_contiguous_runs counts points)
    min_dur_pts = max(2, min_segment_duration // subsample_step)
    min_cluster_pts = max(10, min_cluster_size // subsample_step)

    # ── Step 1: Cluster velocity with auto-Jenks ──
    # Build sorted index
    vel_with_idx = [(vel[i], i) for i in range(n)]
    vel_with_idx.sort(key=lambda x: x[0])
    sorted_idx = [item[1] for item in vel_with_idx]
    vel_sorted = [item[0] for item in vel_with_idx]

    boundaries, k_opt, gvf, k_results = auto_jenks(
        vel_sorted, max_k=max_k, gvf_threshold=gvf_threshold, gvf_gain_min=0.03, min_cluster_size=min_cluster_pts
    )

    # Map sorted indices back to original timeline
    cluster_labels = [0] * n
    for c_idx in range(k_opt):
        start = boundaries[c_idx]
        end = boundaries[c_idx + 1]
        for idx in sorted_idx[start:end]:
            cluster_labels[idx] = c_idx

    # ── Step 2: Filter HR outliers ──
    hr_filtered = _filter_hr_outliers(hr, cluster_labels, k_opt, outlier_iqr_mult)

    # ── Step 3: Temporal segments per cluster ──
    segments_by_cluster = []
    for c in range(k_opt):
        mask = [lbl == c for lbl in cluster_labels]
        segs = extract_contiguous_runs(mask, min_duration=min_dur_pts)
        segments_by_cluster.append(segs)

    # ── Step 4: Drift per cluster ──
    cluster_drifts = []
    cluster_details = []

    for c in range(k_opt):
        segs = segments_by_cluster[c]
        if len(segs) == 0:
            continue

        # Fallback: if only 1 contiguous segment, split it in half
        if len(segs) == 1:
            s, e, dur = segs[0]
            mid = s + dur // 2
            segs = [(s, mid, dur // 2), (mid, e, dur - dur // 2)]

        if len(segs) < 2:
            continue

        mid = max(1, len(segs) // 2)
        early_segs = segs[:mid]
        late_segs = segs[mid:]

        early_indices = [i for s, e, _ in early_segs for i in range(s, e)]
        late_indices = [i for s, e, _ in late_segs for i in range(s, e)]

        early_hr_vals = sorted(hr_filtered[i] for i in early_indices)
        late_hr_vals = sorted(hr_filtered[i] for i in late_indices)

        # Quality gate: need enough points in each half for reliable median
        if len(early_hr_vals) < 5 or len(late_hr_vals) < 5:
            continue

        # Quality gate: minimum effective duration per cluster
        # (duration is in subsampled points, convert to original seconds)
        cluster_duration_s = sum(e - s for s, e, _ in segs) * subsample_step
        if cluster_duration_s < 120:  # at least 2 minutes of data
            continue

        early_hr = _median(early_hr_vals)
        late_hr = _median(late_hr_vals)

        if early_hr <= 0:
            continue

        drift_pct = (late_hr - early_hr) / early_hr * 100.0
        vel_mask = [cluster_labels[i] == c for i in range(n)]
        cluster_vel = [vel[i] for i, m in enumerate(vel_mask) if m]
        weight = sum(vel_mask)

        cluster_drifts.append((drift_pct, weight))
        cluster_details.append(
            {
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
        )

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

    # ── Step 5: Aggregate ──
    drifts = [d for d, _ in cluster_drifts]
    weights = [w for _, w in cluster_drifts]
    total_w = sum(weights)
    drift_weighted_pct = sum(d * w for d, w in zip(drifts, weights, strict=False)) / total_w if total_w > 0 else 0
    drift_consistency = sum(1 for d in drifts if d > 0) / len(drifts)

    # ── Step 6: Build result ──
    # Quality level: based on total effective duration across all valid clusters
    total_dur_s = sum(sum(e - s for s, e, _ in segs) for segs in segments_by_cluster) * subsample_step
    if total_dur_s >= 600:
        quality = "good"  # ≥10 min of clustered data
    elif total_dur_s >= 300:
        quality = "fair"  # ≥5 min
    else:
        quality = "low"  # <5 min — too noisy

    # Severity: only positive drift matters for fatigue detection.
    # Negative drift = warmup effect (HR settles from cold start to steady state).
    if drift_weighted_pct <= 0:
        severity = "stable"
        is_significant = False
    else:
        ad = drift_weighted_pct
        if ad < 3:
            severity = "stable"
        elif ad < 5:
            severity = "borderline"
        elif ad < 8:
            severity = "moderate"
        elif ad < 12:
            severity = "significant"
        else:
            severity = "severe"
        is_significant = (ad >= drift_threshold_pct) and (drift_consistency >= 0.6)

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
