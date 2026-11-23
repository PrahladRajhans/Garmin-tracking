# Roadmap

Decisions (2026-11-23):
- **Runs on:** your laptop/desktop. Local sync job → SQLite → MCP server over stdio (Claude Desktop / Claude Code).
- **Data:** official Garmin Personal API first. The unofficial `garminconnect` library is an isolated add-on for Garmin's advanced scores.
- **Goals:** race training, recovery/readiness, health trends, a full health snapshot, workout-metric explanations with how to improve, fitness age and next steps, workouts sent to the watch.
- **Sensors:** watch only. So no ground contact time balance, and probably no vertical oscillation or ground contact time either (verify in Phase 0). We do get cadence, stride length, wrist power, HR and GPS.

Design rules:
1. Claude never calls Garmin live; every tool reads SQLite. Sync runs on a schedule or on `refresh`.
2. Keep Garmin's own scores and our open calculations in separate fields, never one series.
3. Every derived number returns its inputs and a one-line "what this tells you".
4. Few tools (target ≤ 25), each returning compact summaries rather than raw dumps.
5. Each phase ships usable, tests green, and updates CHANGELOG + README.

---

## Phase 0: Verify before building (1 short session)
| # | Task | Why | Needs you |
|---|---|---|---|
| 0.1 | ~~Apply for a Garmin Personal API key~~ **Done.** Endpoints confirmed via Garmin's official client: no readiness, training status, race predictor or endurance/hill score, so the unofficial add-on stays | Confirms the official path | done |
| 0.2 | Run v0.1.0 login on your machine | Checks whether the unofficial library logs in today | ✅ run `python -m garmin_mcp.login` |
| 0.3 | Export one recent run's FIT file | Shows which fields a watch-only FR955 records | ✅ download "Export Original" from Connect |
| 0.4 | Request the Garmin account data export | Backfills history beyond the API's limits (takes days to arrive) | ✅ Garmin account → Data management |
| 0.5 | Allow the blocked research sites | Lets me verify the unverified claims | ✅ environment settings |

## Phase 1: Data foundation (v0.2)
- SQLite schema: activities, laps, FIT samples, daily summary, sleep, HRV, body, sync_log, thresholds (dated).
- Source adapters behind one interface: `personal_api` (primary), `garminconnect` (augment), `fit_file`, `export_zip`.
- Sync command: incremental by date, retries with backoff, never re-downloads stored data, logs each run.
- Scheduling: an OS scheduler (cron / launchd / Task Scheduler) runs the sync every 2–4 h, plus a `refresh` tool.
- Backfill from the export ZIP and FIT files.
- **Done when:** a year of activities and daily health is in SQLite, and a second sync run fetches only new data.

## Phase 2: Core MCP tools and health snapshot (v0.3)
Tools: `health_snapshot`, `daily_summary`, `sleep`, `hrv`, `activities`, `activity_detail` (laps, splits, zones, dynamics), `trends(metric, range)`, `data_coverage`, `refresh`.
- `health_snapshot` = one call giving today plus the 7/28-day picture: sleep, HRV status, RHR, stress, Body Battery, load, VO2max, Garmin readiness and training status.
- **Done when:** "How am I doing?" can be answered from one tool call.

## Phase 3: Recovery and readiness (v0.4)
- HRV: ln RMSSD, 7-day rolling mean vs a 60-day baseline band (Plews / HRV4Training).
- RHR and sleep vs baseline. Our readiness score shows per-input z-scores next to Garmin's Training Readiness.
- Anomaly flags (illness-like pattern: HRV down, RHR up, respiration up).
- Tools: `readiness_today`, `recovery_trend`, `anomalies`.

## Phase 4: Training load and race performance (v0.5)
- Per-activity load: TRIMP (HR), rTSS (pace/GAP), and Garmin's load stored next to them.
- Fitness/fatigue/form chart (CTL/ATL/TSB), ramp rate, monotony and strain, intensity distribution (Seiler 3-zone).
- Pace-duration curve, critical speed, race prediction (VDOT + Riegel + CS) shown next to Garmin's race predictor.
- Tools: `training_load`, `intensity_distribution`, `pace_curve`, `race_prediction`.

## Phase 5: Workout metric coaching (v0.6)
- Per run: efficiency factor, aerobic decoupling (Pa:HR), cadence and stride vs pace, HR drift, splits consistency, power, Training Effect.
- A metrics glossary (each metric: what it means, good range, how to improve), stored as data and returned with results.
- Fitness age: Garmin's value plus an open estimate from VO2max age norms, and which levers (VO2max, RHR, activity, BMI) would move it.
- Tools: `explain_activity`, `metric_glossary`, `fitness_age`.

## Phase 6: Memory and planning (v0.7)
- Athlete profile: goals, target race, thresholds, preferences, injury notes. Coaching notes log.
- `reality_check_goal`: target race time vs current fitness.
- Tools: `athlete_context`, `update_athlete_context`, `goal_check`.

## Phase 7: Workouts to the watch (v0.8)
- Structured workout builder (warm-up, intervals by pace/HR, cool-down).
- Delivery, in this order: (a) unofficial Garmin Connect workout upload, then sync to the watch; (b) fallback FIT workout file copied over USB. The official Training API is business-only.
- Tools: `create_workout`, `list_workouts`, `delete_workout`.

## Later / optional
Weather context for runs, Apple Health import, intervals.icu as a second source, Grafana dashboard, remote MCP hosting.

## Explicitly not building
Skin temperature/ECG (the FR955 has neither sensor). ACWR as "injury risk". Strava as a source (its API terms ban AI use). Multi-provider dedupe.
