# Metrics Contract

MCP tools expose prepared metrics and model facts only. Human-facing interpretation stays downstream in intelligent agents.

Each registry entry includes a calculation contract so agents can understand how a metric is produced without reading implementation code.

| metric_id | unit | scope | sport_scope | comparison_mode | directionality | exposed_in | calculation |
|---|---|---|---|---|---|---|---|
| active_days | count | period | global | sum | higher_is_more | get_fitness_state, compare_periods | Count of days with activity_count > 0 in the 14-day rolling window. |
| activity_date | date | activity | both | none | neutral | list_workouts, get_workout_detail | Local activity day derived from the stored Strava activity start date. |
| activity_id | id | activity | both | none | neutral | list_workouts, get_workout_detail | Direct Strava activity id stored in activities.id. |
| activity_name | text | activity | both | none | neutral | list_workouts, get_workout_detail | Direct Strava activity name stored on the activity row. |
| activity_streak_days | count | period | global | last | higher_is_more | get_fitness_state, compare_periods | Reserved count of consecutive recent active days; current get_fitness_state returns null. |
| activity_template_trimp | trimp | projection | global | distribution | context | project_fitness_state | Scenario template TRIMP value, currently Config.Plan.TRIMP_EASY for the easy scenario. |
| acwr | ratio | model | global | last | context | get_fitness_state, compare_periods | Acute:chronic workload ratio stored as fatigue / fitness when fitness > 0. |
| acwr_history | ratio | period | global | trend | context | get_fitness_state, compare_periods | Daily time series of acwr values from training_model_daily facts. |
| acwr_zone | category | model | global | distribution | context | get_fitness_state, compare_periods | ACWR category derived from acwr thresholds in report logic; currently not materialized as a v5 read-model column. |
| atl | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods | Alias for Banister fatigue in the v5 read model. |
| avg_hr | bpm | activity | per_sport | avg | context | list_workouts, get_workout_detail, compare_periods | Strava summary_json.average_heartrate for the activity. |
| avg_trimp_per_day | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods | total_trimp_14d divided by 14. |
| banister_history | model_units | period | global | trend | context | get_fitness_state, compare_periods | Daily time series of Banister fitness, fatigue, form, and TRIMP from the materialized training_model_daily facts. |
| by_sport_distance_km | km | period | both | distribution | higher_is_more | get_fitness_state, compare_periods | Distribution of mirrored distance_m grouped by sport over a period and divided by 1000; currently not materialized for v5 get_fitness_state. |
| by_sport_elevation_m | m | period | both | distribution | higher_is_more | get_fitness_state, compare_periods | Distribution of mirrored elevation_gain_m grouped by sport over a period; currently not materialized for v5 get_fitness_state. |
| by_sport_time_min | minutes | period | both | distribution | higher_is_more | get_fitness_state, compare_periods | Distribution of mirrored moving_time_s grouped by sport over a period and divided by 60; currently not materialized for v5 get_fitness_state. |
| by_sport_trimp | trimp | period | both | distribution | context | get_fitness_state, compare_periods | Distribution of TRIMP grouped by sport over a period; currently not materialized for v5 get_fitness_state. |
| cardiac_cost | ratio | activity | per_sport | median | lower_is_better | get_workout_detail, compare_periods | Average stream heartrate divided by average stream velocity for points above Config.Thresholds.VEL_MOVING. |
| cardiac_cost_adjusted | ratio | activity | per_sport | median | lower_is_better | get_workout_detail, compare_periods | Currently materialized as the same value as cardiac_cost in the v5 read model; legacy analytics used cardiac_cost - Config.Efficiency.CC_ELEV_COEFF * elevation_m_per_km. |
| cardiac_drift_pct | percent | activity | per_sport | median | lower_is_better | get_workout_detail, compare_periods | Jenks-clusters moving stream velocity into pace bands, compares early vs late median HR inside bands, and returns weighted HR drift percent. |
| cardiac_drift_quality | category | activity | per_sport | distribution | context | get_workout_detail, compare_periods | Quality label emitted by the cardiac drift algorithm; the v5 read model currently does not persist it, so MCP payloads return null. |
| cardiac_drift_severity | category | activity | per_sport | distribution | context | get_workout_detail, compare_periods | Severity label emitted by the Jenks-based cardiac drift algorithm for the activity. |
| cardiac_drift_significant | count | activity | per_sport | sum | higher_is_worse | get_workout_detail, compare_periods | Current comparison payload maps materialized cardiac_drift_pct to 1 when drift_pct >= 5.0, otherwise 0. |
| ctl | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods | Alias for Banister fitness in the v5 read model. |
| daily_avg_trimp_28d | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods | 28-day rolling effective_trimp sum divided by 28. |
| daily_avg_trimp_7d | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods | 7-day rolling effective_trimp sum divided by 7. |
| daily_avg_trimp_90d | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods | 90-day rolling effective_trimp sum divided by 90. |
| daily_trimp | trimp | period | global | sum | higher_is_more | get_fitness_state, compare_periods | Daily effective_trimp from daily_load_facts, built from per-activity TRIMP and zero-filled rest or missing-HR days. |
| distance_km | km | activity | both | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods | Activity distance_m from the mirror divided by 1000. |
| efficiency_trend_pct | percent | period | per_sport | trend | lower_is_better | get_fitness_state, compare_periods | Reserved trend of per-sport efficiency metrics such as cardiac cost; currently skipped for period comparison. |
| elapsed_time_min | minutes | activity | both | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods | Activity elapsed_time_s from the mirror divided by 60. |
| elevation_m | m | activity | both | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods | Activity total elevation gain in meters from the mirrored Strava activity. |
| fatigue | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods, project_fitness_state | Banister short-term fatigue EWMA of daily effective_trimp using Config.Model.Banister.TAU_FATIGUE. |
| fitness | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods, project_fitness_state | Banister long-term fitness EWMA of daily effective_trimp using Config.Model.Banister.TAU_FITNESS. |
| form | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods, project_fitness_state | Banister form = fitness - fatigue. |
| form_zone | category | model | global | distribution | context | get_fitness_state, project_fitness_state | Categorizes form as tired when form < -5, normal when -5 <= form < 10, and fresh when form >= 10. |
| hr_anomaly_count | count | activity | both | sum | higher_is_worse | get_workout_detail, compare_periods | Count of consecutive stream heartrate jumps greater than 30 bpm. |
| hr_recovery_avg_bpm_per_min | bpm_per_min | activity | per_sport | avg | higher_is_better | get_workout_detail, compare_periods | Arithmetic mean HR drop rate across detected rest pauses, in bpm per minute. |
| hr_recovery_best_bpm_per_min | bpm_per_min | activity | per_sport | max | higher_is_better | get_workout_detail, compare_periods | Maximum HR drop rate across detected rest pauses, in bpm per minute. |
| hr_recovery_median_bpm_per_min | bpm_per_min | activity | per_sport | median | higher_is_better | get_workout_detail, compare_periods | Median HR drop rate across detected rest pauses, in bpm per minute. |
| hr_recovery_pauses | count | activity | per_sport | sum | context | get_workout_detail, compare_periods | Detected pause count from HR recovery analysis; pauses are >= Config.Metrics.MIN_PAUSE_SEC with velocity < Config.Thresholds.VEL_STOP. The v5 read model currently does not persist this count, so MCP payloads return null. |
| hr_recovery_total_rest_sec | seconds | activity | per_sport | sum | context | get_workout_detail, compare_periods | Total seconds across HR recovery pauses; pause detection matches hr_recovery_pauses. The v5 read model currently does not persist this total, so MCP payloads return null. |
| hr_recovery_worst_bpm_per_min | bpm_per_min | activity | per_sport | min | higher_is_worse | get_workout_detail, compare_periods | Minimum HR drop rate across detected rest pauses, in bpm per minute. |
| hrr_pct | percent | activity | per_sport | median | lower_is_easier | get_workout_detail, compare_periods | Median activity heartrate normalized to heart-rate reserve: (median_hr - Config.Athlete.HR_REST) / (observed_hr_max - HR_REST) * 100. |
| last_hike_days_ago | count | period | global | last | lower_is_recent | get_fitness_state, compare_periods | Reserved days since the latest Hike activity; current get_fitness_state returns null. |
| load_trend_pct | percent | period | global | trend | higher_is_more | get_fitness_state, compare_periods | Trend percent over rolling effective_trimp; currently backed by the 28-day effective_trimp fact in get_fitness_state. |
| max_hr | bpm | activity | per_sport | max | higher_is_more | list_workouts, get_workout_detail, compare_periods | Strava summary_json.max_heartrate rounded to an integer bpm. |
| moving_time_min | minutes | activity | both | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods | Activity moving_time_s from the mirror divided by 60. |
| post_weekend_monday_form | model_units | projection | global | distribution | higher_is_more | project_fitness_state | When target_date is Friday-Sunday, forward-simulates rest days after target_date and reports the following Monday form. |
| progressive_cc_trends | percent | model | per_sport | trend | lower_is_better | get_fitness_state, project_fitness_state | Reserved per-sport cardiac-cost trend bundle from progressive signal analysis; current MCP payloads return null. |
| progressive_load_bonus | ratio | model | global | last | higher_is_more | get_fitness_state, project_fitness_state | Reserved progressive-overload scalar from 21-day quality trends; current MCP payloads return null. |
| projected_daily_trimp | trimp | projection | global | distribution | context | project_fitness_state | Scenario input TRIMP for each projected day: rest=0, easy=Config.Plan.TRIMP_EASY, maintain=recent weekday pattern, custom=user input. |
| projected_fatigue | model_units | projection | global | last | higher_is_more | project_fitness_state | Forward-simulated Banister fatigue from current baseline and projected_daily_trimp. |
| projected_fitness | model_units | projection | global | last | higher_is_more | project_fitness_state | Forward-simulated Banister fitness from current baseline and projected_daily_trimp. |
| projected_form | model_units | projection | global | last | higher_is_more | project_fitness_state | Forward-simulated projected_fitness - projected_fatigue. |
| rest_days | count | period | global | sum | higher_is_more | get_fitness_state, compare_periods | Count of days with activity_count = 0 in the 14-day rolling window. |
| rest_streak_days | count | period | global | last | higher_is_more | get_fitness_state, compare_periods | Reserved count of consecutive recent rest days; current get_fitness_state returns null. |
| rolling_median_cc | ratio | period | per_sport | median | lower_is_better | get_fitness_state, compare_periods | Reserved 90-day rolling median cardiac_cost; the v5 materializer currently writes null. |
| rolling_median_cc_adj | ratio | period | per_sport | median | lower_is_better | get_fitness_state, compare_periods | Reserved 90-day rolling median adjusted_cardiac_cost; the v5 materializer currently writes null. |
| rolling_median_epkm | m | period | per_sport | median | context | get_fitness_state, compare_periods | Reserved rolling median elevation gain per kilometer; currently not materialized in v5 read-model payloads. |
| run_90d_median_cc_trend_pct | percent | period | per_sport | trend | lower_is_better | get_fitness_state, compare_periods | Reserved trend of 90-day running median cardiac cost; currently skipped for period comparison. |
| sport_type | category | activity | both | distribution | neutral | list_workouts, get_workout_detail, compare_periods | Direct Strava sport_type stored on the activity row. |
| start_time | time | activity | both | none | neutral | list_workouts, get_workout_detail | HH:MM extracted from summary_json.start_date_local when Strava provided it. |
| target_date_form | model_units | projection | global | last | higher_is_more | project_fitness_state | The final projected_form value on the requested target_date for a scenario. |
| time_in_hr_zones_min | minutes | activity | both | distribution | context | get_workout_detail, compare_periods | Counts stream heartrate samples in the five configured HR zones and divides seconds by 60. |
| total_trimp_14d | trimp | period | global | sum | higher_is_more | get_fitness_state, compare_periods | Sum of effective_trimp over the 14-day rolling window ending at the query day. |
| trimp | trimp | activity | global | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods | Per-activity TRIMP = sum(seconds in configured HR zones * Config.Zones.COEFF) / 60 using mirrored heartrate samples. |
| vertical_ascent_m | m | activity | both | sum | higher_is_more | get_workout_detail, compare_periods | Sum of positive altitude deltas from the altitude stream. |
| vertical_duration_h | hours | activity | both | sum | higher_is_more | get_workout_detail, compare_periods | Elapsed stream duration used for vertical speed, computed from the last stream time_offset / 3600. |
| vertical_speed_m_per_h | m_per_hour | activity | per_sport | median | higher_is_more | get_workout_detail, compare_periods | Positive altitude gain from altitude stream divided by elapsed stream duration in hours. |
| volume_28d | count | period | both | sum | higher_is_more | get_fitness_state, compare_periods | Activity count over the 28-day rolling window. |
| volume_7d | count | period | both | sum | higher_is_more | get_fitness_state, compare_periods | Activity count over the 7-day rolling window. |
| weekly_trimp | trimp | period | global | sum | higher_is_more | get_fitness_state, compare_periods | Sum of effective_trimp over the 7-day rolling window ending at the query day. |
| z5_seconds | seconds | activity | both | sum | higher_is_more | get_workout_detail, compare_periods | Count of stream heartrate samples at or above the configured Z5 lower bound. |

## Excluded interpretation fields

- `recommendation.action`: preserved metrics -> form, weekly_trimp, active_days
- `recommendation.confidence`: preserved metrics -> active_days, rest_days
- `recommendation.intensity`: preserved metrics -> form, weekly_trimp, daily_trimp
- `safety_warnings.text`: preserved metrics -> z5_seconds, hr_anomaly_count, cardiac_drift_significant
- `weekly_plan.on_track`: preserved metrics -> target_date_form, form
- `weekly_plan.plan_days.activity`: preserved metrics -> projected_daily_trimp, activity_template_trimp
