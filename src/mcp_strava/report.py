"""Daily training report — 14-day panorama + recommendation."""

from datetime import datetime, timedelta

from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.constants import Config, RUNNING_SPORTS
from mcp_strava.db import DbConn
from mcp_strava.metrics import enrich_activity, check_z5_minutes, check_hr_anomalies
from mcp_strava.training import (
    calc_banister, ewma,
    calc_progressive_signal, calc_weekly_plan
)
from mcp_strava.types import DailyReport, Recommendation, BanisterPoint, AcwrPoint, BySportBreakdown


def daily_report():
    """Compute the full daily training report.
    
    Returns DailyReport with: yesterday detail, 14-day panorama, trends, Banister,
    ACWR, progressive signal, weekly plan, recommendation.
    """
    with DbConn() as conn:
        repo = SQLiteRepository.from_connection(conn)
        now_local = datetime.now()
        today = now_local.strftime('%Y-%m-%d')
        yesterday = (now_local - timedelta(days=1)).strftime('%Y-%m-%d')
        window_start = (now_local - timedelta(days=14)).strftime('%Y-%m-%d')

        # 14-day activities (window_start through yesterday — today is incomplete)
        acts_14d = repo.activity_rows_between(window_start, yesterday)

        # Enrich all activities with metrics
        all_acts = []
        for row in acts_14d:
            all_acts.append(enrich_activity(conn, row))

        # Yesterday's activities (subset)
        yesterday_acts = [a for a in all_acts if a.date == yesterday]

        # Group by date for daily totals
        daily = {}
        for a in all_acts:
            d = a.date
            daily.setdefault(d, {'trimp': 0, 'activities': []})
            daily[d]['trimp'] += a.trimp
            daily[d]['activities'].append(a)

        # Full date range for 14-day window
        all_dates = set()
        d = datetime.strptime(window_start, '%Y-%m-%d')
        end = datetime.strptime(today, '%Y-%m-%d')
        while d < end:
            all_dates.add(d.strftime('%Y-%m-%d'))
            d += timedelta(days=1)
        active_days = len(set(a.date for a in all_acts) & all_dates)
        rest_days = len(all_dates) - active_days

        # 14-day trends removed (May 2026, coach review #9).
        # Decoupling, EF, HRR trends over 4-6 points are statistical noise.
        # Kept: Banister form, ACWR, and progressive signal for quality tracking.

        total_trimp_14d = round(sum(a.trimp for a in all_acts), 1)
        avg_trimp_per_day = round(total_trimp_14d / len(all_dates), 1) if all_dates else 0

        # By sport_type summary
        by_sport: dict[str, BySportBreakdown] = {}
        for a in all_acts:
            s = a.sport_type
            if s not in by_sport:
                by_sport[s] = BySportBreakdown()
            bs = by_sport[s]
            bs.count += 1
            bs.trimp += a.trimp
            bs.distance_km += a.distance_km
            bs.time_min += a.moving_time_min
            bs.elevation_m += a.elevation_m or 0

        # Banister model
        first_training_day = repo.first_activity_day(sport_filter="training")
        daily_trimp = (
            repo.effective_trimp_history(first_training_day, today, sport_filter="training")
            if first_training_day
            else {}
        )
        banister = calc_banister(daily_trimp, today)

        # ACWR
        ctl_ewma = ewma(daily_trimp, 28, today)
        ctl_val = ctl_ewma.get(today, 0)
        atl_val = banister.fatigue if banister else 0
        acwr = round(atl_val / ctl_val, 2) if ctl_val > 0 else None
        acwr_zone = 'sweet_spot' if acwr and 0.8 <= acwr <= 1.3 else \
                    'caution' if acwr and 1.3 < acwr <= Config.Thresholds.ACWR_DANGER else \
                    'danger' if acwr and acwr > Config.Thresholds.ACWR_DANGER else \
                    'undertrained' if acwr and acwr < 0.8 else 'unknown'

        # ACWR history + Banister history (7 days back)
        # NOTE: calc_banister() is called 14 times here — each does a full EWMA pass
        # over daily_trimp. For ~500 days this is negligible (<100ms); if daily_trimp
        # grows to 10k+ days, precompute the full Banister/EWMA series once.
        acwr_history = []
        banister_history = []
        for delta in range(7, 0, -1):
            past_day = (now_local - timedelta(days=delta)).strftime('%Y-%m-%d')
            past_ban = calc_banister(daily_trimp, past_day)
            # ACWR
            past_ctl = ctl_ewma.get(past_day, 0)
            past_atl = past_ban.fatigue if past_ban else 0
            past_acwr = round(past_atl / past_ctl, 2) if past_ctl > 0 else None
            if past_acwr is not None:
                acwr_history.append(AcwrPoint(date=past_day, acwr=past_acwr, atl=past_atl, ctl=past_ctl))
            # Banister
            if past_ban:
                banister_history.append(BanisterPoint(
                    date=past_day,
                    form=past_ban.form,
                    fatigue=past_ban.fatigue,
                ))

        # Build report
        report = DailyReport(
            today=today,
            yesterday=yesterday,
            window_days=14,
            window_start=window_start,
            yesterday_activities=yesterday_acts,
            yesterday_trimp=round(sum(a.trimp for a in yesterday_acts), 1),
            activities_14d=all_acts,
            daily_trimp_14d={d: v['trimp'] for d, v in daily.items()},
            total_trimp_14d=total_trimp_14d,
            avg_trimp_per_day=avg_trimp_per_day,
            active_days=active_days,
            rest_days=rest_days,
            by_sport=by_sport,
            banister=banister,
            banister_history=banister_history,
            weekly_trimp=round(sum(
                daily.get(d.strftime('%Y-%m-%d'), {}).get('trimp', 0)
                for d in [(now_local - timedelta(days=i)) for i in range(7)]
            ), 1),
            acwr=acwr,
            acwr_zone=acwr_zone,
            acwr_atl=atl_val,
            acwr_ctl=ctl_val,
            acwr_history=acwr_history,
        )

        # Z5 safety check: warn if any activity had >5 min in Z5 (HR≥177)
        for a in yesterday_acts:
            z5_sec, z5_warn = check_z5_minutes(conn, a.id)
            if z5_warn:
                report.safety_warnings.append(z5_warn)

            # HR anomaly check: inter-point jumps >30 bpm (sports medicine review #12)
            anom_count, anom_warn = check_hr_anomalies(conn, a.id)
            if anom_warn:
                report.safety_warnings.append(anom_warn)

            # Cardiac drift: significant/severe drift on yesterday's activity
            # is a fatigue signal — warn only with sufficient data quality
            if a.cardiac_drift and a.cardiac_drift.is_significant:
                if a.cardiac_drift.quality in ('good', 'fair'):
                    sev = a.cardiac_drift.severity
                    if sev in ('significant', 'severe'):
                        report.safety_warnings.append(
                            f"⚠️ Сильный кардиальный дрейф на вчерашней тренировке "
                            f"({a.sport_type}) — сердце работало тяжелее при том же "
                            f"темпе. Признак накопленной усталости или обезвоживания. "
                            f"Рекомендуется день восстановления."
                        )
                    elif sev == 'moderate':
                        report.safety_warnings.append(
                            f"Умеренный кардиальный дрейф на вчерашней тренировке "
                            f"({a.sport_type}) — следи за гидратацией и сном."
                        )

        # Hike safety: warn if two consecutive hiking days exceed 800 TRIMP total
        # (sports medicine review #16). Temperature >28°C check pending Open-Meteo API.
        day_before_yesterday = (now_local - timedelta(days=2)).strftime('%Y-%m-%d')
        yesterday_hikes = [a for a in all_acts if a.date == yesterday and a.sport_type == 'Hike']
        day_before_hikes = [a for a in all_acts if a.date == day_before_yesterday and a.sport_type == 'Hike']
        if yesterday_hikes and day_before_hikes:
            total_hike_trimp = sum(a.trimp for a in yesterday_hikes + day_before_hikes)
            if total_hike_trimp > 800:
                report.safety_warnings.append(
                    f"⚠️ Два похода подряд ({day_before_yesterday} и {yesterday}) — "
                    f"суммарно {total_hike_trimp:.0f} TRIMP. "
                    "Повышенный риск обезвоживания, рабдомиолиза, перегрева. "
                    "Рекомендуется день отдыха."
                )

        # Orthopaedic safety: running volume 10% rule (sports medicine review #14)
        # Running produces 2.5-3× body weight impact per step. Masters athletes
        # should limit weekly km increase to 10% to avoid stress fractures.
        today_dt = datetime.strptime(today, '%Y-%m-%d').date()
        week_start = today_dt - timedelta(days=today_dt.weekday())
        this_km = repo.total_distance_km_between(week_start.isoformat(), today, RUNNING_SPORTS)
        prev_km = repo.total_distance_km_between(
            (week_start - timedelta(days=7)).isoformat(),
            (week_start - timedelta(days=1)).isoformat(),
            RUNNING_SPORTS,
        )
        if prev_km > 0 and this_km > 0:
            pct_increase = round((this_km / prev_km - 1) * 100, 0)
            if pct_increase > 15:
                report.safety_warnings.append(
                    f"⚠️ Беговой объём вырос на {pct_increase:.0f}% за неделю "
                    f"({prev_km:.0f} → {this_km:.0f} км). Резкий скачок — риск "
                    "стресс-перелома, шинсплинта. Вернись к прошлонедельному объёму."
                )
            elif pct_increase > 10:
                report.safety_warnings.append(
                    f"Беговой объём вырос на {pct_increase:.0f}% за неделю "
                    f"({prev_km:.0f} → {this_km:.0f} км). На верхней границе нормы — "
                    "на следующей неделе не повышай."
                )

        # Recommendation
        report.recommendation = _generate_recommendation(report)

        # Progressive signal — pass enriched activities for cc + drift reuse
        progressive = calc_progressive_signal(conn, daily_trimp, today,
                                              enriched_activities=all_acts)
        report.progressive_signal = progressive

        # Weekly plan
        report.weekly_plan = calc_weekly_plan(daily_trimp, today, load_bonus=progressive.load_bonus)

        return report


def _generate_recommendation(report):
    """Generate training recommendation based on 14-day panorama.

    Pure predicates → merge with priority: rest > easy > train.
    Intensity is resolved independently (max of all signals, capped).
    """
    ban = report.banister
    if not ban:
        return Recommendation(action='train', intensity='normal',
                             reasons=['No Banister data'], confidence='low')

    form = ban.form
    form_zone = ban.form_zone
    weekly_trimp = report.weekly_trimp
    active_days = report.active_days
    rest_days = report.rest_days
    yesterday_trimp = report.yesterday_trimp

    ratio = active_days / (active_days + rest_days) if (active_days + rest_days) > 0 else 0

    # ── Pure predicate functions (no mutation) ──

    def _form_signal():
        """Form zone → (action, intensity, reason). Simplified 3-zone (May 2026)."""
        if form_zone == 'tired':
            if form < -15:
                return ('rest', 'low', f"Форма {form:+.0f} — телу нужна пауза")
            return ('easy', 'low', f"Форма {form:+.0f} — лёгкая усталость")
        if form_zone == 'fresh':
            return ('train', 'high', f"Форма {form:+.0f} — свежий, можно нагрузку")
        return ('train', 'normal', '')

    def _load_signal():
        """Weekly TRIMP → (action_mod, intensity_mod, reason)."""
        if weekly_trimp > 800:
            return ('easy', 'normal', f"Объём за неделю высокий ({weekly_trimp:.0f} TRIMP) — осторожнее")
        if weekly_trimp < 200:
            return ('train', 'high', "Объём низкий — можно добавить")
        return ('train', 'normal', '')

    def _ratio_signal():
        """Activity/rest ratio → (action_mod, reason)."""
        if ratio > 0.85:
            return ('easy', 'normal', "Слишком много активных дней — нужен отдых")
        return ('train', 'normal', '')

    # ── Collect all signals ──

    signals = [
        _form_signal(),
        _load_signal(),
        _ratio_signal(),
    ]

    # Action: priority merge (rest > easy > train)
    action_rank = {'rest': 0, 'easy': 1, 'train': 2}
    action = 'train'
    for sig_action, _, _ in signals:
        if action_rank.get(sig_action, 2) < action_rank[action]:
            action = sig_action

    # Intensity: max of all (rest overrides to low)
    if action == 'rest':
        intensity = 'low'
    else:
        intensity_rank = {'low': 0, 'normal': 1, 'high': 2}
        intensity = 'normal'
        for _, sig_intensity, _ in signals:
            if intensity_rank.get(sig_intensity, 1) > intensity_rank[intensity]:
                intensity = sig_intensity

    # Post-processing caps (order-independent, applied after merge)
    # Yesterday load cap: downgrade intensity if yesterday was heavy
    if yesterday_trimp > Config.Plan.TRIMP_HEAVY_DAY and intensity == 'high':
        intensity = 'normal'
        reasons_cap = ["Вчера была большая нагрузка — сегодня нормально"]
    else:
        reasons_cap = []

    # Reasons: collect all non-empty
    reasons = []
    for _, _, reason in signals:
        if reason:
            reasons.append(reason)
    reasons.extend(reasons_cap)

    return Recommendation(action=action, intensity=intensity, reasons=reasons,
                         confidence=_confidence(active_days + rest_days))


def _confidence(total_days: int) -> str:
    """Confidence level based on data completeness."""
    if total_days < 7:
        return 'low'
    elif total_days < 14:
        return 'medium'
    return 'high'
