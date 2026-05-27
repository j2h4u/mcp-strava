"""Banister model and forward training-load projection."""

from datetime import datetime, timedelta
from mcp_strava.constants import Config
from mcp_strava.types import BanisterResult, SimDay

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
    Used by DuckDB read-model materialization and period analytics."""
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


def _form_zone(form):
    """Classify form into stable, agent-friendly training zones."""
    if form < -5:
        return 'tired'
    if form < 10:
        return 'normal'
    return 'fresh'


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


def forward_simulate(start_fitness, start_fatigue, trimps, start_date,
                     alpha_fitness, alpha_fatigue):
    """Simulate Banister forward from a given state. Pure function.

    Returns list of SimDay dataclass instances.
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
