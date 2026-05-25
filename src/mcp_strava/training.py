"""Banister model, ACWR, and weekly training plan module."""

from mcp_strava.constants import Config, TRAINING_SPORTS
from mcp_strava.metrics import calc_efficiency_factor, calc_hr_recovery, calc_decoupling_with_gate
from mcp_strava.types import (BanisterResult, ProgressiveSignal, PlanDay, SimDay,
                              WeeklyPlan, CompletedDay, PostWeekendSim, SparklineBar)
from datetime import datetime, timedelta
from itertools import product

# Pre-computed SQL IN clause for training sports (from constants, safe)
_TRAINING_SPORTS_IN = ','.join(f"'{s}'" for s in TRAINING_SPORTS)

# ---------------------------------------------------------------------------
# EWMA / Banister core
# ---------------------------------------------------------------------------

def ewma(series_dict, tau, end_date=None):
    """Exponentially weighted moving average over a date series.
    series_dict: {date_str: value}, gaps filled with 0.
    tau: decay constant in days.
    Returns dict {date_str: ewma_value}.
    """
    if not series_dict:
        return {}
    all_dates = sorted(series_dict.keys())
    start = datetime.strptime(all_dates[0], '%Y-%m-%d')
    end = datetime.strptime(end_date or all_dates[-1], '%Y-%m-%d')
    if end < start:
        return {}
    alpha = 1 - pow(0.5, 1.0 / tau)
    result = {}
    ewma = 0
    d = start
    while d <= end:
        ds = d.strftime('%Y-%m-%d')
        val = series_dict.get(ds, 0)
        ewma = alpha * val + (1 - alpha) * ewma
        result[ds] = round(ewma, 1)
        d += timedelta(days=1)
    return result


def calc_banister(daily_trimp, today_str=None):
    """Fitness-Fatigue-Form model.
    Returns dict with fitness (42d EWMA), fatigue (7d EWMA), form (fitness - fatigue).
    """
    if not daily_trimp:
        return None
    end = today_str or max(daily_trimp.keys())
    fitness_ewma = ewma(daily_trimp, Config.Model.Banister.TAU_FITNESS, end)
    fatigue_ewma = ewma(daily_trimp, Config.Model.Banister.TAU_FATIGUE, end)
    fitness = fitness_ewma.get(end, 0)
    fatigue = fatigue_ewma.get(end, 0)
    form = round(fitness - fatigue, 1)
    return BanisterResult(
        fitness=round(fitness, 1),
        fatigue=round(fatigue, 1),
        form=form,
        form_zone=_form_zone(form),
    )


def calc_banister_series(daily_trimp, end_date=None):
    """Return full daily Banister series: list of {date, fitness, fatigue, form, trimp}.
    Single forward pass — more efficient than calling calc_banister() per date.
    Used by trends.py for multi-week analysis."""
    if not daily_trimp:
        return []
    end = end_date or max(daily_trimp.keys())
    end_dt = datetime.strptime(end, '%Y-%m-%d')
    all_dates = sorted(daily_trimp.keys())
    first_dt = datetime.strptime(all_dates[0], '%Y-%m-%d')
    warmup_start = first_dt - timedelta(days=Config.Model.BANISTER_WARMUP_DAYS)

    alpha_f = Config.Model.Banister.ALPHA_FITNESS
    alpha_fa = Config.Model.Banister.ALPHA_FATIGUE

    current = warmup_start
    f = 0.0
    fa = 0.0
    series = []
    while current <= end_dt:
        ds = current.strftime('%Y-%m-%d')
        t = daily_trimp.get(ds, 0)
        f = round(f + alpha_f * (t - f), 1)
        fa = round(fa + alpha_fa * (t - fa), 1)
        series.append({'date': ds, 'fitness': f, 'fatigue': fa, 'form': f - fa, 'trimp': t})
        current += timedelta(days=1)
    return series


# ---------------------------------------------------------------------------
# Form visualisation helpers
# ---------------------------------------------------------------------------

def _form_zone(form):
    """Classify form into stable, agent-friendly training zones."""
    if form < -5:
        return 'tired'
    if form < 10:
        return 'normal'
    return 'fresh'


def _form_marker(form):
    """Short visual form marker for sparklines."""
    if form < -5:  return '🟠'
    if form < 10:  return '🟢'
    return '🔵'


def _form_sparkline(history, width=30):
    """Centered-on-zero sparkline of form values.
    Shows scale from -30 to +20, zero line in the middle.
    Accepts SparklineBar objects (or dicts for backward compat).
    Returns list[SparklineBar].
    """
    if not history:
        return []
    lo, hi = -30, 20  # fixed scale: overtrained to peak
    result = []
    for entry in history:
        f = entry.form if hasattr(entry, 'form') else entry['form']
        # Zero position
        zero_pos = width * (-lo) / (hi - lo)
        val_pos = width * (f - lo) / (hi - lo)
        val_pos = max(0, min(width - 1, val_pos))
        zi = int(round(zero_pos))
        vi = int(round(val_pos))

        # Build bar with fill from zero to value
        bar = list('·' * width)
        if 0 <= zi < width:
            bar[zi] = '┃'

        # Fill between zero and value
        lo_i, hi_i = min(zi, vi), max(zi, vi)
        fill = '▓' if f >= 0 else '░'
        for i in range(lo_i, hi_i + 1):
            if i != zi and 0 <= i < width:
                bar[i] = fill
        bar[vi] = '█' if vi != zi else bar[vi]

        zone = _form_marker(f)
        result.append(SparklineBar(
            label=entry.get('label', '') if isinstance(entry, dict) else entry.label,
            bar=''.join(bar),
            form=f,
            zone=zone,
        ))
    return result


# ---------------------------------------------------------------------------
# Banister helpers

def _sim_one_day(f, fa, trimp, alpha_fitness, alpha_fatigue):
    """Advance Banister state by one day.

    Formula: f₂ = (1−α)·f + α·trimp  (algebraically ≡ f + α·(trimp−f)).
    Rounds to 1 decimal at each step — consistent with forward_simulate.
    """
    f2 = round((1 - alpha_fitness) * f + alpha_fitness * trimp, 1)
    fa2 = round((1 - alpha_fatigue) * fa + alpha_fatigue * trimp, 1)
    return f2, fa2, round(f2 - fa2, 1)


def _forward_simulate_with_weekdays(fitness, fatigue, daily_trimps, start_date,
                                     alpha_fitness, alpha_fatigue):
    """Simulate Banister forward with Russian weekday labels. Returns list[SimDay]."""
    sim_days = forward_simulate(fitness, fatigue, daily_trimps, start_date,
                                alpha_fitness, alpha_fatigue)
    for sd in sim_days:
        dt = datetime.strptime(sd.date, '%Y-%m-%d')
        sd.weekday = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][dt.weekday()]
    return sim_days


# ---------------------------------------------------------------------------
# Trend helper (used by calc_progressive_signal)
# ---------------------------------------------------------------------------

def trend(values):
    """Simple trend: compare avg of first half vs second half.

    Returns formatted string like '↑+15%' (rising >10%), '↓-20%' (falling >10%),
    '→0%' (stable). Callers that need direction logic should use startswith('↑')
    or startswith('↓') — the arrow prefix is the stable contract.
    Returns None if <4 values or zero denominator.

    When the first-half average is near zero (|avg1| < 5), uses absolute
    difference instead of percentage to avoid exaggerated signals like
    '↓-100%' from a tiny 3pp shift crossing zero.
    """
    if len(values) < 4:
        return None
    mid = len(values) // 2
    first = values[:mid]
    second = values[mid:]
    avg1 = sum(first) / len(first)
    avg2 = sum(second) / len(second)
    if avg1 == 0:
        return None

    # When avg1 is near zero, percentage is meaningless — use absolute diff.
    # Tiny shifts near zero (< 5pp) are noise → call them stable.
    # Larger shifts use a floor on the denominator to avoid division explosion.
    if abs(avg1) < 5:
        abs_diff = avg2 - avg1
        if abs(abs_diff) < 5:
            return '→0%'  # ~3pp shift near zero = noise
        pct = round(abs_diff / 5 * 100, 0)
    else:
        pct = round((avg2 - avg1) / abs(avg1) * 100, 0)
    if pct > 10:
        return f'↑{pct:+.0f}%'
    elif pct < -10:
        return f'↓{pct:+.0f}%'
    else:
        return f'→{pct:+.0f}%'


def forward_simulate(start_fitness, start_fatigue, trimps, start_date,
                     alpha_fitness, alpha_fatigue):
    """Simulate Banister forward from a given state. Pure function.

    Returns list of SimDay dataclass instances.
    Used by both calc_weekly_plan (forward planning) and cmd_backtest (historical replay).
    """
    f, fa = start_fitness, start_fatigue
    d = start_date
    results = []
    for t in trimps:
        f, fa, _ = _sim_one_day(f, fa, t, alpha_fitness, alpha_fatigue)
        results.append(SimDay(
            date=d.strftime('%Y-%m-%d'),
            trimp=t,
            fitness=f,
            fatigue=fa,
            form=round(f - fa, 1),
        ))
        d += timedelta(days=1)
    return results


# ---------------------------------------------------------------------------
# Progressive signal / load bonus
# ---------------------------------------------------------------------------

def calc_progressive_signal(conn, daily_trimp, today_str=None, enriched_activities=None):
    """Analyze training quality trends to determine if load can be increased.

    Looks at 21-day window of activities. Computes trends in:
    - Cardiac Cost (CC = 100 / EF): lower = heart works less per meter, fitness improving
    - HR Recovery: slower recovery = accumulating fatigue → blocks load_bonus
    - Cardiac Drift (Jenks-based): rising intra-activity drift → blocks load_bonus
      (Decoupling removed — almost always N/A due to pace variability. CC replaced it May 2026.)

    enriched_activities: optional list[EnrichedActivity] from daily_report.
        If provided, reads cc and cardiac_drift from pre-computed objects
        instead of querying streams again.
    """
    today = today_str or datetime.now().strftime('%Y-%m-%d')
    window_start = (datetime.strptime(today, '%Y-%m-%d') - timedelta(days=Config.Model.PROGRESSIVE_WINDOW)).strftime('%Y-%m-%d')

    rows = conn.execute(f"""
        SELECT id, date, sport_type FROM activities
        WHERE SUBSTR(date,1,10) >= ? AND SUBSTR(date,1,10) <= ?
          AND sport_type IN ({_TRAINING_SPORTS_IN})
        ORDER BY date
    """, (window_start, today)).fetchall()

    if len(rows) < 4:
        return ProgressiveSignal(load_bonus=0.0, signal='hold', ef_trend=None,
                cc_trend=None, reasons=['Мало данных для анализа прогрессии'])

    # Build lookup of pre-computed enriched data
    enriched_by_id = {}
    if enriched_activities:
        enriched_by_id = {a.id: a for a in enriched_activities}

    # Group CC values by sport_type (per-sport trends — don't mix Run and Hike!)
    from collections import defaultdict
    ccs_by_sport: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        sport = row['sport_type']
        enr = enriched_by_id.get(row['id'])
        if enr and enr.cc is not None:
            ccs_by_sport[sport].append(enr.cc)
        else:
            ef = calc_efficiency_factor(conn, row['id'])
            if ef is not None:
                ccs_by_sport[sport].append(100 / ef)

    reasons = []
    bonus = 0.0
    signal = 'hold'

    ef_trend_str = None
    cc_trend_str = None
    cc_trends: dict[str, Optional[str]] = {}

    # Per-sport CC trends: each sport contributes bonus weighted by its activity count.
    # Minimum 3 activities per sport for a valid trend.
    total_cc_activities = sum(len(v) for v in ccs_by_sport.values())
    for sport, ccs in sorted(ccs_by_sport.items()):
        if len(ccs) < 3:
            cc_trends[sport] = None
            continue
        sport_trend = trend(ccs)
        cc_trends[sport] = sport_trend
        sport_weight = len(ccs) / total_cc_activities

        if sport_trend and sport_trend.startswith('↓'):
            try:
                mag = abs(float(sport_trend.split('%')[0].replace('↓', '').replace('−', '-')))
            except (ValueError, IndexError):
                mag = 5
            if mag >= 12:
                bonus += 0.15 * sport_weight
                reasons.append(f'CC {sport} заметно падает ({sport_trend}) — сердце работает эффективнее')
            elif mag >= 7:
                bonus += 0.10 * sport_weight
                reasons.append(f'CC {sport} падает ({sport_trend}) — хорошая динамика')
            else:
                bonus += 0.05 * sport_weight
                reasons.append(f'CC {sport} немного падает ({sport_trend}) — позитивный сигнал')
        elif sport_trend and sport_trend.startswith('↑'):
            try:
                mag = abs(float(sport_trend.split('%')[0].replace('↑', '').replace('−', '-')))
            except (ValueError, IndexError):
                mag = 5
            if mag >= 12:
                bonus -= 0.15 * sport_weight
                reasons.append(f'CC {sport} заметно растёт ({sport_trend}) — нагрузка даётся тяжелее')
            elif mag >= 7:
                bonus -= 0.10 * sport_weight
                reasons.append(f'CC {sport} растёт ({sport_trend}) — нужно снизить нагрузку')
            else:
                bonus -= 0.05 * sport_weight
                reasons.append(f'CC {sport} немного растёт ({sport_trend}) — стоит последить')
        else:
            reasons.append(f'CC {sport} стабилен ({sport_trend})')

    # Build combined cc_trend string for backward compatibility.
    # If only one sport has a trend, use that. Otherwise describe both.
    valid_trends = {s: t for s, t in cc_trends.items() if t is not None}
    if len(valid_trends) == 1:
        sport, trend_str = next(iter(valid_trends.items()))
        cc_trend_str = f'{sport}: {trend_str}'
    elif len(valid_trends) >= 2:
        cc_trend_str = '; '.join(f'{s}: {t}' for s, t in sorted(valid_trends.items()))
    else:
        cc_trend_str = None

    if not cc_trends:
        reasons.append('CC: нет данных ни по одному типу')

    # HR Recovery trend: falling is BAD (slower recovery → accumulating fatigue).
    # Blocks positive load_bonus entirely when HRR is declining.
    hrrs = []
    for row in rows:
        hr_rec = calc_hr_recovery(conn, row['id'])
        if hr_rec is not None:
            hrrs.append(hr_rec.avg_rate)
    if len(hrrs) >= 3:
        hrr_trend = trend(hrrs)
        if hrr_trend and hrr_trend.startswith('↓'):
            reasons.append(f'Восстановление пульса замедляется ({hrr_trend}) — нагрузку не повышать')
            bonus = min(bonus, 0.0)  # block any positive bonus
        elif hrr_trend and hrr_trend.startswith('↑'):
            reasons.append(f'Восстановление пульса улучшается ({hrr_trend})')
    else:
        reasons.append('HRR: мало данных')

    # Cardiac Drift trend: rising drift is BAD (heart works harder late in
    # activity at same pace → declining endurance maintenance).
    # Uses pre-computed cardiac_drift from enriched activities.
    # Only training sports (Run, Hike, TrailRun) — Walk drift is noise.
    drifts = []
    if enriched_activities:
        for a in enriched_activities:
            if a.sport_type not in TRAINING_SPORTS:
                continue
            if a.cardiac_drift and a.cardiac_drift.drift_pct is not None:
                drifts.append(a.cardiac_drift.drift_pct)
    if len(drifts) >= 3:
        drift_trend = trend(drifts)
        # Only positive drift trend matters (negative = warmup, irrelevant)
        if drift_trend and drift_trend.startswith('↑'):
            try:
                # Check if the values themselves are positive (not just trending up from negative)
                recent_drifts = drifts[-3:]
                if sum(1 for d in recent_drifts if d > 0) >= 2:
                    mag = abs(float(drift_trend.split('%')[0].replace('↑', '').replace('−', '-')))
                else:
                    mag = 0
            except (ValueError, IndexError):
                mag = 0
            if mag > 0:
                if mag >= 10:
                    bonus -= 0.10
                    reasons.append(f'Кардиальный дрейф растёт ({drift_trend}) — сердце устаёт быстрее к концу тренировок')
                else:
                    bonus -= 0.05
                    reasons.append(f'Кардиальный дрейф немного растёт ({drift_trend})')
            else:
                reasons.append(f'Кардиальный дрейф в зоне разогрева — стабильно')
        elif drift_trend and drift_trend.startswith('↓'):
            reasons.append(f'Кардиальный дрейф снижается ({drift_trend}) — выносливость улучшается')
        else:
            reasons.append(f'Кардиальный дрейф стабилен ({drift_trend})')
    elif len(drifts) > 0:
        reasons.append('Дрейф: мало данных для тренда')

    # Clamp bonus to [-0.15, +0.20]
    bonus = max(-0.15, min(0.20, bonus))

    if bonus >= 0.05:
        signal = 'grow'
    elif bonus <= -0.05:
        signal = 'reduce'
    else:
        signal = 'hold'

    return ProgressiveSignal(
        load_bonus=round(bonus, 3),
        signal=signal,
        ef_trend=ef_trend_str,
        cc_trend=cc_trend_str,
        cc_trends=cc_trends,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Weekly plan
# ---------------------------------------------------------------------------

def calc_weekly_plan(daily_trimp, today_str=None, load_bonus=0.0):
    """Generate adaptive weekly training plan — bring form to +5..+15 by Saturday.

    Philosophy: one plan, two goals.
    Goal 1: Arrive at the weekend with energy surplus (form +5..+15).
    Goal 2: If training quality metrics are improving (EF ↑, decoupling ↓),
    gradually increase weekly TRIMP via load_bonus (progressive overload).
    If metrics are declining, reduce load to prevent overtraining.

    load_bonus: fraction to scale TRIMP templates. +0.10 = 10% more load.
    Computed by calc_progressive_signal() from 21-day quality trends.

    What happens on the weekend (0/1/2 hikes) doesn't matter for planning —
    actual data feeds back into next week's calculation automatically.
    """
    now = datetime.now()
    today = today_str or now.strftime('%Y-%m-%d')
    today_dt = datetime.strptime(today, '%Y-%m-%d')
    weekday = today_dt.weekday()  # 0=Mon..6=Sun

    # Days until next Saturday
    days_to_sat = (5 - weekday) % 7
    if days_to_sat == 0:
        days_to_sat = 7  # Today is Saturday — target next Saturday

    target_date = today_dt + timedelta(days=days_to_sat)
    monday = today_dt - timedelta(days=weekday)

    # Banister parameters
    alpha_fatigue = Config.Model.Banister.ALPHA_FATIGUE   # ≈ 0.094
    alpha_fitness = Config.Model.Banister.ALPHA_FITNESS  # ≈ 0.016

    banister = calc_banister(daily_trimp, today)
    if not banister:
        return None

    fitness = banister.fitness
    fatigue = banister.fatigue

    ACTIVITY_TEMPLATES = {
        'rest':       {'trimp': 0,   'label': 'отдых',               'emoji': '😴'},
        'walk':       {'trimp': 69,  'label': 'прогулка ~5км',       'emoji': '🚶'},
        'run':        {'trimp': 79,  'label': 'лёгкий бег ~5км',     'emoji': '🏃'},
        'run_medium': {'trimp': 150, 'label': 'средний бег ~8-10км', 'emoji': '🏃‍♂️'},
    }

    # Apply progressive overload: scale walk/run TRIMP by load_bonus
    # rest stays 0 (can't scale nothing). Cap at ±20%.
    if load_bonus != 0:
        for key in ('walk', 'run', 'run_medium'):
            base = ACTIVITY_TEMPLATES[key]['trimp']
            scaled = round(base * (1 + load_bonus))
            ACTIVITY_TEMPLATES[key] = dict(ACTIVITY_TEMPLATES[key], trimp=scaled)

    # Already completed days this week
    completed = []
    for d in range(7):
        day = monday + timedelta(days=d)
        ds = day.strftime('%Y-%m-%d')
        if ds > today:
            break
        trimp = daily_trimp.get(ds, 0)
        wd_names = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс']
        if trimp == 0:
            act_type = 'rest'
        elif trimp <= Config.Plan.TRIMP_EASY:
            # Within EASY range, distinguish walk-like (< 75) from run-like effort
            act_type = 'walk' if trimp < Config.Plan.TRIMP_WALK_RUN_BOUNDARY else 'run'
        elif trimp <= Config.Plan.TRIMP_MEDIUM:
            act_type = 'run'
        else:
            act_type = 'hard'
        completed.append(CompletedDay(
            date=ds, weekday=wd_names[d],
            trimp=trimp, type=act_type, is_past=True,
        ))

    # Optimize: find weekday plan that brings form to +5..+15 by Saturday
    act_keys = list(ACTIVITY_TEMPLATES.keys())

    # N days of planning = from tomorrow to Saturday inclusive
    # _forward_simulate_with_weekdays generates entries starting at today+1
    # With N = days_to_sat, the last entry is Saturday morning form
    n_days = days_to_sat

    best_plan = ()
    best_score = -1e9

    if n_days > 0:
        for combo in product(act_keys, repeat=n_days):
            trimps = [ACTIVITY_TEMPLATES[k]['trimp'] for k in combo]
            projected = _forward_simulate_with_weekdays(fitness, fatigue, trimps, today_dt + timedelta(days=1), alpha_fitness, alpha_fatigue)
            sat_form = projected[-1].form

            S = Config.Plan.Score
            score = 0
            # Primary: Saturday form in +5..+15
            if 5 <= sat_form <= 15:
                score += S.TARGET_HIT
            elif 0 <= sat_form < 5:
                score += S.NEAR_LOW
            elif 15 < sat_form <= 25:
                score += S.NEAR_HIGH
            elif -5 <= sat_form < 0:
                score += S.SLIGHTLY_TIRED
            elif sat_form > 25:
                score += S.TOO_FRESH
            else:
                score += S.MISS_PENALTY
            score -= abs(sat_form - 10) * S.DEVIATION_FACTOR

            # Maximize total load (preserve fitness)
            score += sum(trimps) * S.LOAD_BONUS

            # Progressive overload: when load_bonus > 0, extra reward for plans
            # that actually use the increased load (not just resting)
            if load_bonus > 0:
                active_trimp = sum(t for t, k in zip(trimps, combo) if k != 'rest')
                score += active_trimp * load_bonus * S.PROGRESSIVE_FACTOR
            elif load_bonus < 0:
                # Conservative: penalize plans that are too aggressive
                active_count = sum(1 for k in combo if k != 'rest')
                if active_count > n_days * S.AGGRESSIVE_THRESHOLD:
                    score -= S.AGGRESSIVE_PENALTY

            # Safety: penalize deep negative form during the week
            for p in projected:
                if p.form < -20:
                    score -= S.SAFETY_CRITICAL
                elif p.form < -15:
                    score -= S.SAFETY_WARNING

            # Mandatory rest: penalize plans with zero rest days (age 50+ needs ≥1)
            rest_days = sum(1 for k in combo if k == 'rest')
            if rest_days < 1:
                score -= S.NO_REST_PENALTY

            # Prefer variety
            score += len(set(combo)) * S.VARIETY_BONUS

            if score > best_score:
                best_score = score
                best_plan = combo

    # Build plan days directly as PlanDay dataclasses (no intermediate dicts)
    trimps = [ACTIVITY_TEMPLATES[k]['trimp'] for k in best_plan]
    sim_days = _forward_simulate_with_weekdays(fitness, fatigue, trimps, today_dt + timedelta(days=1), alpha_fitness, alpha_fatigue)

    plan_days = []
    for i, sd in enumerate(sim_days):
        k = best_plan[i] if i < len(best_plan) else 'rest'
        tmpl = ACTIVITY_TEMPLATES.get(k, ACTIVITY_TEMPLATES['rest'])
        plan_days.append(PlanDay(
            date=sd.date,
            weekday=sd.weekday,
            trimp=sd.trimp,
            activity=tmpl['label'],
            form=sd.form,
            form_zone=_form_zone(sd.form),
            is_rest=(sd.trimp == 0),
            is_target=False,
        ))

    # Saturday form = last planned day
    sat_form = plan_days[-1].form if plan_days else banister.form
    on_track = 5 <= sat_form <= 15

    # Mark Saturday as target
    if plan_days:
        plan_days[-1].is_target = True

    # Post-weekend projections: use sim_days (carries fitness/fatigue)
    sat_f = sim_days[-1].fitness if sim_days else fitness
    sat_fa = sim_days[-1].fatigue if sim_days else fatigue
    HIKE_TRIMP = Config.Plan.HIKE_TRIMP_TEMPLATE

    # 0 hikes: Monday form = Saturday form + 2 rest days
    f1, fa1, _ = _sim_one_day(sat_f, sat_fa, 0, alpha_fitness, alpha_fatigue)
    _, _, mon_form_0 = _sim_one_day(f1, fa1, 0, alpha_fitness, alpha_fatigue)

    # 1 hike (Saturday only)
    f1, fa1, _ = _sim_one_day(sat_f, sat_fa, HIKE_TRIMP, alpha_fitness, alpha_fatigue)
    f2, fa2, mon_form_1 = _sim_one_day(f1, fa1, 0, alpha_fitness, alpha_fatigue)

    # 2 hikes (Saturday + Sunday)
    f1, fa1, _ = _sim_one_day(sat_f, sat_fa, HIKE_TRIMP, alpha_fitness, alpha_fatigue)
    f2, fa2, mon_form_2 = _sim_one_day(f1, fa1, HIKE_TRIMP, alpha_fitness, alpha_fatigue)

    post_weekend = [
        PostWeekendSim(hikes=0, monday_form=mon_form_0, note='отдых'),
        PostWeekendSim(hikes=1, monday_form=mon_form_1, note='1 поход'),
        PostWeekendSim(hikes=2, monday_form=mon_form_2, note='2 похода'),
    ]

    # Sparkline: current → plan → Saturday
    sparkline_data = [SparklineBar(form=banister.form, label='сейчас')]
    for d in plan_days:
        lbl = d.weekday
        if d.is_target:
            lbl += '🎯'
        sparkline_data.append(SparklineBar(form=d.form, label=lbl))

    return WeeklyPlan(
        target_day=target_date.strftime('%Y-%m-%d'),
        target_weekday='Сб',
        days_to_target=days_to_sat,
        current_form=banister.form,
        current_form_zone=banister.form_zone,
        completed_days=completed,
        plan_days=plan_days,
        saturday_form=sat_form,
        on_track=on_track,
        post_weekend=post_weekend,
        sparkline=_form_sparkline(sparkline_data),
        load_bonus=load_bonus,
        activity_templates={k: v['trimp'] for k, v in ACTIVITY_TEMPLATES.items()},
    )
