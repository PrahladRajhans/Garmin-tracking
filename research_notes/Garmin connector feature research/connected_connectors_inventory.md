# Connected connectors: full tool inventory
Source: live tool listings in this Claude session (2026-11-22). Tool behaviour inferred from names + server instructions; not called (AthleteData plan inactive).

## Fitness AI Connector (Garmin only, 18 tools)
| Group | Tools |
|---|---|
| Account | get_user_profile, get_help, manage_subscription, delete_account, acknowledge_garmin_source |
| Activities | get_activities (per-activity `device` field), get_activity_details, get_activity_fit_file, refetch_activity_detail, set_activity_visibility |
| Health | get_health_summary, get_body_composition, get_cycle_data (women's health), get_trends |
| Workouts (write) | create_workout, list_workouts, delete_workout |
| Sync | refresh_data |
Rules it enforces: "📊 Data from Garmin" header + footer "Insights derived in part from Garmin device-sourced data", device name per activity, no implied Garmin endorsement (GCDP official-API terms). Timezone from profile for "today". No derived analytics beyond trends.

## AthleteData (multi-source, ~250 tools)
**Cross-source / merged (dedupe duplicate sessions):** get_daily_metrics, get_sleep, get_activity_detail, get_activity_stream, get_dedupe_clusters, get_data_coverage, get_connection_status, get_blood_pressure, get_glucose

**Analytics (the value layer):**
| Tool | Insight |
|---|---|
| get_pmc_status | CTL/ATL/TSB fitness-fatigue-form |
| get_readiness_today | daily readiness |
| get_load_flag, get_load_balance | load spike / balance flags |
| get_intensity_distribution | zone distribution (polarized etc.) |
| get_efficiency_trend | efficiency factor / decoupling trend |
| get_pace_curve, get_power_curve | best-effort duration curves |
| get_race_prediction, get_performance_estimates | race times, thresholds |
| get_training_trends, get_sleep_trend, get_analytics_summary | trends |
| get_anomalies | outlier detection |
| analyze_dose_response, analyze_pattern | training → outcome correlations |
| reality_check_goal | goal feasibility |

**Memory / settings:** get_athlete_context, athlete_preference_update, coaching_note_create/get/delete, set_ftp, set_thresholds, set_units

**Garmin-specific (18):** garmin_get_activities, _activity, _activity_details, _activity_file, list_activity_files, _body_composition, _daily_summaries, _health_snapshot, _heart_rate, _hrv, _move_iq, _pulse_ox, _respiration, _skin_temps, _sleep, _stress, _user_metrics, garmin_refetch_day

**Watch write-back:** push_workout_to_watch, update_workout_on_watch, list_workouts_on_watch, delete_workout_from_watch, get_planned_workouts

**Other providers (read, some write):** Apple Health (workouts, run stream, HRV, RHR, sleep, vitals, VO2max, body comp), Oura (17), Whoop (5), Withings (8), Google Health (4), Wahoo, Peloton, Concept2, Hevy (18, incl. routines write), intervals.icu (13, incl. workout upsert), TrainingPeaks (13, write), Terra, Eight Sleep, Renpho, Xiaomi, BodySpec, MyWhoosh push

**Context:** weather (forecast + historical), geocode, race search/results, food log + nutrition targets, calendars (Google/Apple/Outlook), Google Sheets, ClassPass / Urban Sports Club booking, athlete files

## What to copy vs skip (for us, single FR955 user)
- Copy: Garmin raw tools, PMC, readiness, load flag, intensity distribution, efficiency/decoupling, pace curve, race prediction, anomalies, dose-response, athlete memory, data coverage, refresh/refetch-day, weather context.
- Skip: multi-provider dedupe (one device), bookings, nutrition (unless wanted), 250-tool sprawl.
- Note: `garmin_get_skin_temps` is useless on FR955 (no sensor).
