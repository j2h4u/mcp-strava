# Metric Registry

This is the core metric inventory. `exposed_in` lists MCP tools that currently expose a metric; `core-only` means the metric is still a first-class core/report/analytics metric but is not currently emitted by an MCP tool.

## Aggregate Registry Contract

This section is drift-tested against `src/mcp_strava/application/metric_registry.py`. Aggregation semantics are defined in registry metadata and are not duplicated as alternate metric ids.

Supported aggregate modes: `sum`, `calendar_average`, `weighted_average`, `ratio_of_sums`, `quantile`, `last_state`, `distribution`, `kudos_count`.

Supported buckets: `day`, `week`, `month`, `year`, `all_time`. Week buckets use Monday start. Date ranges are half-open: `[start_day, end_day_exclusive)`.

Supported rolling windows: `7`, `14`, `28`, `42`, `90` days. The same set is materialized by the read model.

Rolling-window metrics with a duration in the metric id, such as `volume_7d`, are filtered to that declared `window_days` before bucket aggregation. Generic rolling medians default to the registry window unless the request supplies an allowed `window_days`.

Supported scopes: `global`, `per_sport`, `both`. Gear and equipment are not aggregate scopes or bundle dimensions.

Default quantiles for distribution context: `p25`, `median`, `p75`. Quantile metrics expose a sample-size field so low-sample buckets can be represented as facts.

Denominator and provenance terms currently used by aggregate metadata: `activity_count`, `activity_sample_count`, `active_day_count`, `calendar_day_count`, `calendar_days`, `cardiac_drift_significant`, `distance_m`, `effective_trimp`, `elapsed_time_s`, `elevation_gain_m`, `heartrate_sample_count`, `latest_day`, `model_day_count`, `moving_time_s`, `rest_day_count`, `rolling_sample_count`, `trimp`, `vertical_speed_duration_hours`, `vertical_speed_total_ascent_m`.

Registry aggregate bundles:

| bundle_id | metric_ids |
|---|---|
| `daily_brief` | `fitness`, `fatigue`, `form`, `form_zone`, `acwr`, `acwr_zone`, `weekly_trimp`, `total_trimp_14d`, `avg_trimp_per_day`, `active_days`, `rest_days`, `daily_avg_trimp_7d`, `rolling_median_cc`, `rolling_median_hr_recovery`, `kudos_count` |
| `weekly_digest` | `trimp`, `distance_km`, `moving_time_min`, `elapsed_time_min`, `elevation_m`, `active_days`, `weekly_trimp`, `volume_7d`, `avg_hr`, `max_hr`, `cardiac_cost`, `cardiac_cost_adjusted`, `cardiac_drift_pct`, `hrr_pct` |
| `monthly_digest` | `trimp`, `distance_km`, `moving_time_min`, `elevation_m`, `active_days`, `volume_28d`, `daily_avg_trimp_28d`, `daily_avg_trimp_90d`, `fitness`, `fatigue`, `form` |
| `period_comparison` | `trimp`, `distance_km`, `moving_time_min`, `elapsed_time_min`, `elevation_m`, `active_days`, `rest_days`, `fitness`, `fatigue`, `form`, `acwr`, `avg_hr`, `max_hr`, `hr_recovery_median_bpm_per_min`, `vertical_speed_m_per_h`, `cardiac_cost`, `cardiac_cost_adjusted`, `cardiac_drift_pct`, `hrr_pct`, `cardiac_drift_significant`, `time_in_hr_zones_min` |
| `sport_efficiency` | `avg_hr`, `hr_recovery_median_bpm_per_min`, `vertical_speed_m_per_h`, `cardiac_cost`, `cardiac_cost_adjusted`, `cardiac_drift_pct`, `hrr_pct`, `rolling_median_cc`, `rolling_median_cc_adj`, `rolling_median_hr_recovery`, `rolling_median_cardiac_drift_pct` |
| `historical_facts` | `sport_type`, `form_zone`, `acwr_zone`, `cardiac_drift_severity`, `cardiac_drift_quality`, `kudos_count`, `active_days`, `activity_streak_days`, `rest_streak_days`, `last_hike_days_ago` |

Aggregate rows carry bucket start/end, bucket width, `metric_id`, `unit`, `aggregate_mode`, denominator metadata, value, sample size, activity count, null/excluded count, completeness status, missing reasons, metric version status, materialized timestamp, mirror freshness, and read-model freshness.

Materialized analytic fact-table columns are also registered here in code as `dimension`, `metric`, `dependency`, or `provenance`; schema drift is tested against that registry before a new column can silently consume storage.

## Metric Inventory

| metric_id | unit | scope | sport_scope | comparison_mode | directionality | exposed_in | calculation |
|---|---|---|---|---|---|---|---|
| active_days | count | period | global | sum | higher_is_more | get_fitness_state, compare_periods | Count of days with activity_count > 0 in the 14-day rolling window. |
| activity_date | date | activity | both | none | neutral | list_workouts, get_workout_detail | Local activity day derived from the stored Strava activity start date. |
| activity_id | id | activity | both | none | neutral | list_workouts, get_workout_detail | Direct Strava activity id stored in activities.id. |
| activity_name | text | activity | both | none | neutral | list_workouts, get_workout_detail | Direct Strava activity name stored on the activity row. |
| activity_streak_days | count | period | global | last | higher_is_more | core-only | Count of consecutive recent days with at least one activity. |
| activity_template_trimp | trimp | projection | global | distribution | context | project_fitness_state | Scenario template TRIMP value, currently Config.Plan.TRIMP_EASY for the easy scenario. |
| acwr | ratio | model | global | last | context | get_fitness_state, compare_periods | Acute:chronic workload ratio stored as fatigue / fitness when fitness > 0. |
| acwr_history | ratio | period | global | trend | context | core-only | Daily ACWR time series with the fatigue and fitness inputs used for each point. |
| acwr_zone | category | model | global | none | context | get_fitness_state | Agent-friendly ACWR category: sweet_spot for 0.8-1.3, caution up to Config.Thresholds.ACWR_DANGER, danger above it, undertrained below 0.8. |
| avg_hr | bpm | activity | per_sport | avg | context | list_workouts, get_workout_detail, compare_periods | Strava summary_json.average_heartrate for the activity. |
| avg_trimp_per_day | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods | total_trimp_14d divided by 14. |
| banister_history | model_units | period | global | trend | context | core-only | Daily Banister time series of fitness, fatigue, form, form_zone, and TRIMP for recent/report windows. |
| by_sport_distance_km | km | period | both | distribution | higher_is_more | core-only | Period distance grouped by sport from mirrored activity distance_m divided by 1000. |
| by_sport_elevation_m | m | period | both | distribution | higher_is_more | core-only | Period elevation gain grouped by sport from mirrored elevation_gain_m. |
| by_sport_time_min | minutes | period | both | distribution | higher_is_more | core-only | Period moving time grouped by sport from mirrored moving_time_s divided by 60. |
| by_sport_trimp | trimp | period | both | distribution | context | core-only | Period TRIMP grouped by sport from enriched activity/report rows. |
| cardiac_cost | ratio | activity | per_sport | median | lower_is_better | get_workout_detail, compare_periods | Average stream heartrate divided by average stream velocity for points above Config.Thresholds.VEL_MOVING. |
| cardiac_cost_adjusted | ratio | activity | per_sport | median | lower_is_better | get_workout_detail, compare_periods | Elevation-adjusted cardiac cost = cardiac_cost - Config.Efficiency.CC_ELEV_COEFF * elevation_gain_m_per_km. |
| cardiac_drift_pct | percent | activity | per_sport | median | lower_is_better | get_workout_detail, compare_periods | Jenks-clusters moving stream velocity into pace bands, compares early vs late median HR inside bands, and returns weighted HR drift percent. |
| cardiac_drift_quality | category | activity | per_sport | distribution | context | get_workout_detail | Cardiac drift algorithm quality label based on clustered data duration: good, fair, or low. |
| cardiac_drift_severity | category | activity | per_sport | distribution | context | get_workout_detail | Cardiac drift severity label from the Jenks-based algorithm: stable, borderline, moderate, significant, or severe. |
| cardiac_drift_significant | count | activity | per_sport | sum | higher_is_worse | get_workout_detail, compare_periods | Boolean activity flag materialized as 1 when the cardiac drift algorithm marks the drift significant, otherwise 0. |
| daily_avg_trimp_28d | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods | 28-day rolling effective_trimp sum divided by 28. |
| daily_avg_trimp_7d | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods | 7-day rolling effective_trimp sum divided by 7. |
| daily_avg_trimp_90d | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods | 90-day rolling effective_trimp sum divided by 90. |
| daily_trimp | trimp | period | global | sum | higher_is_more | core-only | Daily effective TRIMP series from daily_load_facts, using observed TRIMP on complete HR days and 0 for rest or unknown days. |
| distance_km | km | activity | both | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods | Activity distance_m from the mirror divided by 1000. |
| efficiency_trend_pct | percent | period | per_sport | trend | lower_is_better | core-only | Percent change of per-sport rolling cardiac efficiency metrics, especially median cardiac cost. |
| elapsed_time_min | minutes | activity | both | sum | higher_is_more | get_workout_detail, compare_periods | Activity elapsed_time_s from the mirror divided by 60. |
| elevation_m | m | activity | both | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods | Activity total elevation gain in meters from the mirrored Strava activity. |
| fatigue | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods | Banister short-term fatigue EWMA of daily effective_trimp using Config.Model.Banister.TAU_FATIGUE. |
| fitness | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods | Banister long-term fitness EWMA of daily effective_trimp using Config.Model.Banister.TAU_FITNESS. |
| form | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods | Banister form = fitness - fatigue. |
| form_zone | category | model | global | none | context | get_fitness_state | Agent-friendly form category: tired when form < -5, normal when -5 <= form < 10, fresh when form >= 10. |
| gear_distance_km | km | activity | both | none | context | get_workout_detail | Total mirrored Strava gear distance in meters divided by 1000 when the detailed gear payload provides distance. |
| gear_id | id | activity | both | none | context | get_workout_detail | Strava gear id copied from the activity summary or detail payload when mirrored for an activity. |
| gear_name | text | activity | both | none | context | get_workout_detail | Gear or shoe display name copied from the detailed Strava gear payload when it is mirrored for an activity. |
| gear_primary | boolean | activity | both | none | context | get_workout_detail | Boolean primary-gear flag copied from the detailed Strava gear payload when Strava marks a shoe as primary. |
| hr_anomaly_count | count | activity | both | sum | higher_is_worse | get_workout_detail, compare_periods | Count of consecutive stream heartrate jumps greater than 30 bpm. |
| hr_recovery_avg_bpm_per_min | bpm_per_min | activity | per_sport | avg | higher_is_better | get_workout_detail, compare_periods | Arithmetic mean HR drop rate across detected rest pauses, in bpm per minute. |
| hr_recovery_best_bpm_per_min | bpm_per_min | activity | per_sport | max | higher_is_better | get_workout_detail, compare_periods | Maximum HR drop rate across detected rest pauses, in bpm per minute. |
| hr_recovery_median_bpm_per_min | bpm_per_min | activity | per_sport | median | higher_is_better | get_workout_detail, compare_periods | Median HR drop rate across detected rest pauses, in bpm per minute. |
| hr_recovery_pauses | count | activity | per_sport | sum | context | get_workout_detail, compare_periods | Count of detected rest pauses from HR recovery analysis; pauses are >= Config.Metrics.MIN_PAUSE_SEC with velocity < Config.Thresholds.VEL_STOP. |
| hr_recovery_total_rest_sec | seconds | activity | per_sport | sum | context | get_workout_detail, compare_periods | Total seconds across detected HR recovery rest pauses. |
| hr_recovery_worst_bpm_per_min | bpm_per_min | activity | per_sport | min | higher_is_worse | get_workout_detail, compare_periods | Minimum HR drop rate across detected rest pauses, in bpm per minute. |
| hrr_pct | percent | activity | per_sport | median | lower_is_easier | get_workout_detail, compare_periods | Median activity heartrate normalized to heart-rate reserve: (median_hr - Config.Athlete.HR_REST) / (observed_hr_max - HR_REST) * 100. |
| kudos_count | count | activity | both | none | context | list_workouts, get_workout_detail | Strava summary_json.kudos_count for the activity, defaulting to 0 when Strava omitted it. |
| kudos_names | text_list | activity | both | none | context | get_workout_detail | Names stored from the Strava kudos endpoint for the activity, grouped by activity_id and formatted from firstname and lastname. |
| last_hike_days_ago | count | period | global | last | lower_is_recent | core-only | Days since the latest mirrored Hike activity. |
| load_trend_pct | percent | period | global | trend | higher_is_more | core-only | Percent change of rolling daily TRIMP load between the current window and the previous equally sized window. |
| max_hr | bpm | activity | per_sport | max | higher_is_more | list_workouts, get_workout_detail, compare_periods | Strava summary_json.max_heartrate rounded to an integer bpm. |
| moving_time_min | minutes | activity | both | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods | Activity moving_time_s from the mirror divided by 60. |
| post_weekend_monday_form | model_units | projection | global | distribution | higher_is_more | project_fitness_state | When target_date is Friday-Sunday, forward-simulates rest days after target_date and reports the following Monday form. |
| progressive_cc_trends | percent | model | per_sport | trend | lower_is_better | core-only | Per-sport cardiac-cost trend bundle used by the progressive signal calculation. |
| progressive_load_bonus | ratio | model | global | last | higher_is_more | core-only | Progressive-overload scalar from 21-day quality trends; positive when quality improves, negative when fatigue signals worsen. |
| projected_daily_trimp | trimp | projection | global | distribution | context | project_fitness_state | Scenario input TRIMP for each projected day: rest=0, easy=Config.Plan.TRIMP_EASY, maintain=recent weekday pattern, custom=user input. |
| projected_fatigue | model_units | projection | global | last | higher_is_more | project_fitness_state | Forward-simulated Banister fatigue from current baseline and projected_daily_trimp. |
| projected_fitness | model_units | projection | global | last | higher_is_more | project_fitness_state | Forward-simulated Banister fitness from current baseline and projected_daily_trimp. |
| projected_form | model_units | projection | global | last | higher_is_more | project_fitness_state | Forward-simulated projected_fitness - projected_fatigue. |
| rest_days | count | period | global | sum | higher_is_more | get_fitness_state, compare_periods | Count of days with activity_count = 0 in the 14-day rolling window. |
| rest_streak_days | count | period | global | last | higher_is_more | core-only | Count of consecutive recent days without activity. |
| rolling_median_cardiac_drift_pct | percent | period | per_sport | median | lower_is_better | get_fitness_state, compare_periods | Rolling median cardiac_drift_pct from materialized activity_metric_facts for the selected window. |
| rolling_median_cc | ratio | period | per_sport | median | lower_is_better | get_fitness_state, compare_periods | Rolling median cardiac_cost from materialized activity_metric_facts for the selected window. |
| rolling_median_cc_adj | ratio | period | per_sport | median | lower_is_better | get_fitness_state, compare_periods | Rolling median cardiac_cost_adjusted from materialized activity_metric_facts for the selected window. |
| rolling_median_epkm | m_per_km | period | per_sport | median | context | core-only | Rolling median elevation gain per kilometer from per-activity analytics rows. |
| rolling_median_hr_recovery | bpm_per_min | period | per_sport | median | higher_is_better | get_fitness_state, compare_periods | Rolling median hr_recovery_median_bpm_per_min from materialized activity_metric_facts for the selected window. |
| run_90d_median_cc_trend_pct | percent | period | per_sport | trend | lower_is_better | core-only | Percent change of 90-day running median cardiac cost versus the previous 90-day running window. |
| sport_type | category | activity | both | distribution | neutral | list_workouts, get_workout_detail | Direct Strava sport_type stored on the activity row. |
| start_time | time | activity | both | none | neutral | get_workout_detail | HH:MM extracted from summary_json.start_date_local when Strava provided it. |
| target_date_form | model_units | projection | global | last | higher_is_more | project_fitness_state | The final projected_form value on the requested target_date for a scenario. |
| time_in_hr_zones_min | minutes | activity | both | distribution | context | get_workout_detail, compare_periods | Counts stream heartrate samples in the five configured HR zones and divides seconds by 60. |
| total_trimp_14d | trimp | period | global | sum | higher_is_more | get_fitness_state, compare_periods | Sum of effective_trimp over the 14-day rolling window ending at the query day. |
| trimp | trimp | activity | global | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods | Per-activity TRIMP = sum(seconds in configured HR zones * Config.Zones.COEFF) / 60 using mirrored heartrate samples. |
| vertical_ascent_m | m | activity | both | sum | higher_is_more | get_workout_detail, compare_periods | Sum of positive altitude deltas from the altitude stream. |
| vertical_duration_h | hours | activity | both | sum | higher_is_more | get_workout_detail, compare_periods | Elapsed stream duration used for vertical speed, computed from the last stream time_offset / 3600. |
| vertical_speed_m_per_h | m_per_hour | activity | per_sport | median | higher_is_more | get_workout_detail, compare_periods | Positive altitude gain from altitude stream divided by elapsed stream duration in hours. |
| volume_28d | count | period | global | sum | higher_is_more | get_fitness_state, compare_periods | Activity count over the 28-day rolling window. |
| volume_7d | count | period | global | sum | higher_is_more | get_fitness_state, compare_periods | Activity count over the 7-day rolling window. |
| weekly_trimp | trimp | period | global | sum | higher_is_more | get_fitness_state, compare_periods | Sum of effective_trimp over the 7-day rolling window ending at the query day. |

## Interpretation Caveats

- `cardiac_cost`, adjusted cardiac cost, cardiac drift, HR recovery, and heart-rate reserve metrics are sport-sensitive. Compare them per sport unless the agent explicitly explains why cross-sport comparison is acceptable.
- Traditional decoupling can be unavailable because pace variability makes the signal invalid; this is a metric-quality fact, not necessarily a missing mirror-data failure.
- Cardiac drift severity and quality labels describe the algorithm's activity-level signal quality. They are not medical diagnoses.
- Safety warnings are factual training-data flags. They must not be presented as medical advice.
- Temperature, subjective effort, sleep, resting heart rate, illness, and other external factors are not part of this mirror unless a metric explicitly says so.

## Excluded Interpretations

- `recommendation.action`: preserved metrics -> form, weekly_trimp, active_days
- `recommendation.confidence`: preserved metrics -> active_days, rest_days
- `recommendation.intensity`: preserved metrics -> form, weekly_trimp, active_days
- `safety_warnings.text`: preserved metrics -> time_in_hr_zones_min, hr_anomaly_count, cardiac_drift_significant
- `weekly_plan.on_track`: preserved metrics -> target_date_form, form
- `weekly_plan.plan_days.activity`: preserved metrics -> projected_daily_trimp, activity_template_trimp
