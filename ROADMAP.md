# Roadmap

Decisions (2026-11-23):
- **Runs on:** your laptop/desktop. Local sync job → SQLite → MCP server over stdio (Claude Desktop / Claude Code).
- **Data:** official Garmin Personal API first. The unofficial `garminconnect` library is an isolated add-on for Garmin's advanced scores.
- **Goals:** race training, recovery/readiness, health trends, a full health snapshot, workout-metric explanations with how to improve, fitness age and next steps, workouts sent to the watch.
- **Sensors:** watch only. **Verified on real FIT files:** the FR955 records vertical oscillation, ground contact time, stride length, cadence, wrist power, HR and GPS from the wrist. No ground contact time balance. Beat-to-beat HRV only if HRV logging is switched on in the watch settings.

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
| 0.2 | ~~Unofficial login~~ **Done** on the Mac; 7-day sync, 0 errors | | done |
| 0.3 | ~~One run's FIT file~~ **Done** via the API: running dynamics present | | done |
| 0.4 | ~~Garmin account data export~~ **Done**: Feb 2024 → Nov 2026, 7,815 FIT files, downloaded into the dev session from Drive | | done |
| 0.5 | ~~Allow research sites~~ **Done** | | done |

## Status and audit (2026-11-23)

### Where things run
- **Development (this cloud session):** all coding, testing, research, importing your export and syncing via the official API. No Mac needed.
- **Your Mac:** runs the finished connector for Claude Desktop. Mac setup is handled by a **local Claude Code session** (Claude desktop app → Code → Local → folder `Garmin-tracking`), which can run Terminal commands itself. The cloud session can't, because the Mac reports the Remote Control folder as "not available" to cloud sessions.

### Audit: everything raised so far and its state
| Item | State |
|---|---|
| README + CHANGELOG updated every change | ongoing ✅ |
| Research: competitors, FR955 metrics, formulas, integrations | done ✅ |
| Verify research claims marked unverified / snippet / [bg] (sites were blocked) | **open → step A** |
| Confirm METRICS.md formulas against primary sources (⚠ items) | **open → step A** |
| Import full history from the Garmin export | **open → step B** |
| Backfill extras from the unofficial library (only 7 days on the Mac) | open → step F (Mac) |
| Tidy (normalised) tables from raw payloads | open → step C (Phase 2) |
| Move the 4 original tools onto the local database (design rule 1) | open → step C |
| One-call health snapshot | open → step C |
| Connect the MCP server to Claude Desktop on the Mac | open → step F |
| Scheduled sync on the Mac | open → step F |
| Rotate the Personal API key (it was pasted in chat) | deferred by you |
| Beat-to-beat HRV during activities (watch setting "Log HRV") | optional, your choice |
| Merge PR #1 into `main` | at the end of Phase 2 |
| Phases 3–7 (readiness, load, coaching, memory, workouts) | after Phase 2 |

### Next steps, in order
- **A. Verify research and formulas.** Re-check every unverified claim against full pages now that the sites are open; correct the notes, report and METRICS.md.
- **B. History importer:** `garmin-mcp-import <export folder>`. Loads the export (activities + FIT, sleep, health status, readiness, race predictions, endurance/hill, acute load, VO2max, acclimation, daily summaries, hydration, PRs, zones) into the same database. Tested on your real export here.
- **C. Phase 2:** tidy tables (daily, sleep, HRV, readiness, load...) built from all three sources (export, official API, unofficial), with a defined priority when they overlap; health snapshot tool; existing tools moved to the local database.
- **D.** Verify the numbers against Garmin Connect for a few sample days (I report them; you glance at your app).
- **E.** Merge to `main`.
- **F. Mac setup in one go** (done by a local Claude Code session using a script I write): pull, import your Downloads export, backfill extras, connect to Claude Desktop, schedule the sync.

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
