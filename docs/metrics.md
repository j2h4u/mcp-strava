# Metrics Contract

MCP tools expose prepared metrics and model facts only. Human-facing interpretation stays downstream in intelligent agents.

| metric_id | unit | scope | sport_scope | comparison_mode | directionality | exposed_in |
|---|---|---|---|---|---|---|
| active_days | count | period | global | sum | higher_is_more | get_fitness_state, compare_periods |
| activity_date | date | activity | both | none | neutral | list_workouts, get_workout_detail |
| activity_id | id | activity | both | none | neutral | list_workouts, get_workout_detail |
| activity_name | text | activity | both | none | neutral | list_workouts, get_workout_detail |
| activity_streak_days | count | period | global | last | higher_is_more | get_fitness_state, compare_periods |
| activity_template_trimp | trimp | projection | global | distribution | context | project_fitness_state |
| acwr | ratio | model | global | last | context | get_fitness_state, compare_periods |
| acwr_history | ratio | period | global | trend | context | get_fitness_state, compare_periods |
| acwr_zone | category | model | global | distribution | context | get_fitness_state, compare_periods |
| atl | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods |
| avg_hr | bpm | activity | per_sport | avg | context | list_workouts, get_workout_detail, compare_periods |
| avg_trimp_per_day | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods |
| banister_history | model_units | period | global | trend | context | get_fitness_state, compare_periods |
| by_sport_distance_km | km | period | both | distribution | higher_is_more | get_fitness_state, compare_periods |
| by_sport_elevation_m | m | period | both | distribution | higher_is_more | get_fitness_state, compare_periods |
| by_sport_time_min | minutes | period | both | distribution | higher_is_more | get_fitness_state, compare_periods |
| by_sport_trimp | trimp | period | both | distribution | context | get_fitness_state, compare_periods |
| cardiac_cost | ratio | activity | per_sport | median | lower_is_better | get_workout_detail, compare_periods |
| cardiac_cost_adjusted | ratio | activity | per_sport | median | lower_is_better | get_workout_detail, compare_periods |
| cardiac_drift_pct | percent | activity | per_sport | median | lower_is_better | get_workout_detail, compare_periods |
| cardiac_drift_quality | category | activity | per_sport | distribution | context | get_workout_detail, compare_periods |
| cardiac_drift_severity | category | activity | per_sport | distribution | context | get_workout_detail, compare_periods |
| cardiac_drift_significant | count | activity | per_sport | sum | higher_is_worse | get_workout_detail, compare_periods |
| ctl | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods |
| daily_avg_trimp_28d | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods |
| daily_avg_trimp_7d | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods |
| daily_avg_trimp_90d | trimp | period | global | avg | higher_is_more | get_fitness_state, compare_periods |
| daily_trimp | trimp | period | global | sum | higher_is_more | get_fitness_state, compare_periods |
| distance_km | km | activity | both | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods |
| efficiency_trend_pct | percent | period | per_sport | trend | lower_is_better | get_fitness_state, compare_periods |
| elapsed_time_min | minutes | activity | both | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods |
| elevation_m | m | activity | both | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods |
| fatigue | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods, project_fitness_state |
| fitness | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods, project_fitness_state |
| form | model_units | model | global | last | higher_is_more | get_fitness_state, compare_periods, project_fitness_state |
| form_zone | category | model | global | distribution | context | get_fitness_state, project_fitness_state |
| hr_anomaly_count | count | activity | both | sum | higher_is_worse | get_workout_detail, compare_periods |
| hr_recovery_avg_bpm_per_min | bpm_per_min | activity | per_sport | avg | higher_is_better | get_workout_detail, compare_periods |
| hr_recovery_best_bpm_per_min | bpm_per_min | activity | per_sport | max | higher_is_better | get_workout_detail, compare_periods |
| hr_recovery_median_bpm_per_min | bpm_per_min | activity | per_sport | median | higher_is_better | get_workout_detail, compare_periods |
| hr_recovery_pauses | count | activity | per_sport | sum | context | get_workout_detail, compare_periods |
| hr_recovery_total_rest_sec | seconds | activity | per_sport | sum | context | get_workout_detail, compare_periods |
| hr_recovery_worst_bpm_per_min | bpm_per_min | activity | per_sport | min | higher_is_worse | get_workout_detail, compare_periods |
| hrr_pct | percent | activity | per_sport | median | lower_is_easier | get_workout_detail, compare_periods |
| last_hike_days_ago | count | period | global | last | lower_is_recent | get_fitness_state, compare_periods |
| load_trend_pct | percent | period | global | trend | higher_is_more | get_fitness_state, compare_periods |
| max_hr | bpm | activity | per_sport | max | higher_is_more | list_workouts, get_workout_detail, compare_periods |
| moving_time_min | minutes | activity | both | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods |
| post_weekend_monday_form | model_units | projection | global | distribution | higher_is_more | project_fitness_state |
| progressive_cc_trends | percent | model | per_sport | trend | lower_is_better | get_fitness_state, project_fitness_state |
| progressive_load_bonus | ratio | model | global | last | higher_is_more | get_fitness_state, project_fitness_state |
| projected_daily_trimp | trimp | projection | global | distribution | context | project_fitness_state |
| projected_fatigue | model_units | projection | global | last | higher_is_more | project_fitness_state |
| projected_fitness | model_units | projection | global | last | higher_is_more | project_fitness_state |
| projected_form | model_units | projection | global | last | higher_is_more | project_fitness_state |
| rest_days | count | period | global | sum | higher_is_more | get_fitness_state, compare_periods |
| rest_streak_days | count | period | global | last | higher_is_more | get_fitness_state, compare_periods |
| rolling_median_cc | ratio | period | per_sport | median | lower_is_better | get_fitness_state, compare_periods |
| rolling_median_cc_adj | ratio | period | per_sport | median | lower_is_better | get_fitness_state, compare_periods |
| rolling_median_epkm | m | period | per_sport | median | context | get_fitness_state, compare_periods |
| run_90d_median_cc_trend_pct | percent | period | per_sport | trend | lower_is_better | get_fitness_state, compare_periods |
| sport_type | category | activity | both | distribution | neutral | list_workouts, get_workout_detail, compare_periods |
| start_time | time | activity | both | none | neutral | list_workouts, get_workout_detail |
| target_date_form | model_units | projection | global | last | higher_is_more | project_fitness_state |
| time_in_hr_zones_min | minutes | activity | both | distribution | context | get_workout_detail, compare_periods |
| total_trimp_14d | trimp | period | global | sum | higher_is_more | get_fitness_state, compare_periods |
| trimp | trimp | activity | global | sum | higher_is_more | list_workouts, get_workout_detail, compare_periods |
| vertical_ascent_m | m | activity | both | sum | higher_is_more | get_workout_detail, compare_periods |
| vertical_duration_h | hours | activity | both | sum | higher_is_more | get_workout_detail, compare_periods |
| vertical_speed_m_per_h | m_per_hour | activity | per_sport | median | higher_is_more | get_workout_detail, compare_periods |
| volume_28d | count | period | both | sum | higher_is_more | get_fitness_state, compare_periods |
| volume_7d | count | period | both | sum | higher_is_more | get_fitness_state, compare_periods |
| weekly_trimp | trimp | period | global | sum | higher_is_more | get_fitness_state, compare_periods |
| z5_seconds | seconds | activity | both | sum | higher_is_more | get_workout_detail, compare_periods |

## Excluded interpretation fields

- `recommendation.action`: preserved metrics -> form, weekly_trimp, active_days
- `recommendation.confidence`: preserved metrics -> active_days, rest_days
- `recommendation.intensity`: preserved metrics -> form, weekly_trimp, daily_trimp
- `safety_warnings.text`: preserved metrics -> z5_seconds, hr_anomaly_count, cardiac_drift_significant
- `weekly_plan.on_track`: preserved metrics -> target_date_form, form
- `weekly_plan.plan_days.activity`: preserved metrics -> projected_daily_trimp, activity_template_trimp
