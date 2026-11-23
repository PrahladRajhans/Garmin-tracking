# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `docs/CHATGPT_HANDOVER_PROMPT.md`: a ready-to-paste handover prompt for ChatGPT. It covers the vision, reading order, system summary, pitfalls, and the next tasks: private dashboard hosting, a VO2max norm bar from a cited table, and a design review.

## [0.14.0] - 2026-11-23

- Added the Body-page VO₂max reference bar from the retrieved primary FRIEND 2015 **Table 3**.
  Separate grey Garmin and hollow blue effective markers, exact reference values, age/sex group,
  source and untested-HRmax caveat. No exact personal percentile or physiological equivalence
  of the estimates is claimed.
- `norms.py` contains the 84 measured FRIEND values for published age decades 20–79 and sex
  groups. Missing profile data/out-of-range ages are explicit; no assumptions or extrapolation.
- Research notes contain the exact implemented table, full citation and all 24 numeric source
  rows (including unused Cooper rows) extracted directly to CSV. All 84 code values are checked
  against that transcription. Primary data came from 7,783 US treadmill CPX tests; it is not a
  personal target or a claim of representativeness for an Indian user.
- Validation: 106 local tests and Ruff pass. Age boundaries, missing profiles/data, separate
  markers and caveats are covered. Race/taper, live phone deployment and further source review
  remain pending; no new MCP tool or norm-based fitness-age estimate was added.

## [0.13.3] - 2026-11-23

Accuracy and input-validation review (step 2).

- Unified sleep score/debt/bedtime fallback at 8 hours, explicitly a planning assumption,
  not AASM's adult minimum or a measured personal need. Debt returns its per-night inputs;
  no valid nights means unavailable debt rather than zero. Sleep z-scores require 14 prior
  valid nights; resting-HR/respiration z-scores correctly require 21 prior values.
- Calibrating recovery no longer produces "planned training is fine". Missing Garmin
  readiness is described as unavailable rather than "None". Illness/low-readiness rules remain.
- Day/sleep HR comparison interprets normalized timestamps as UTC, excludes known sleep
  windows and invalid negative samples, and removes the unsupported 10% health cutoff.
  Run drift advice now acknowledges alternative causes. Fitness-age trend wording no longer
  presents it as biological ageing.
- Recovery-weight study retains HRV-only days, compares composites on matched days per outcome,
  and treats zero correlation as zero. Weights and the >0.05 improvement-on-both-outcomes rule
  remain unchanged; historical real-data figures have not been recomputed.
- Malformed workouts return validation problems, including nonpositive/nonfinite time/distance,
  bad targets, ambiguous targets, and excessive nesting/step counts. Invalid numeric, pace
  and timezone athlete overrides are rejected before saving/rebuilding.
- Primary AASM sleep consensus and Python datetime behavior were checked; the research ledger
  distinguishes retrieved evidence, practitioner heuristics and pending full-paper validation.
- Validation: 102 local tests and Ruff pass, including UTC window comparisons, baseline limits,
  debt provenance, paired study days, zero correlations and malformed/cyclic workout inputs.

## [0.13.2] - 2026-11-23

Operations and loop review (step 1 of the owner-requested review).

- The 11-hour gate now records a completed, error-free run of every requested source, not
  an individual successful request. A failed/interrupted run remains marked for retry even
  when an older completed sync is recent. First run after this change performs a full sync.
- Sync dates, refresh windows and the activity probe use the athlete's local date, after
  settings seeding. Invalid day counts and non-positive range chunk sizes fail explicitly;
  negative chunks could previously move backward forever.
- Official API pagination rejects repeated pages and has a 1,000-request cap, failing rather
  than accepting truncated history. Page fingerprints retain hashes rather than whole responses.
  Unofficial-library pagination was inspected and already has its own request cap.
- Failed dependency installation now stops re-execution/sync, preserves a per-checkout retry
  marker outside the repo, and retries on the next run even without a new commit. A pending
  install also blocks sync if the subsequent Git fetch fails.
- CI now includes `codex/**` and `chatgpt/**` pushes in addition to PRs/main/Claude branches.
- GitHub API access is restored. PR #8 passed CI on Python 3.12 and 3.13 and was merged
  through GitHub; no direct push to main was used.
- Added regression tests for completion/retry state, local dates, invalid chunks, pagination
  limits and failed-install recovery. No live Garmin calls were made during validation.
- Validation: 93 local tests and Ruff pass; CI is required before merge.

## [0.13.1] - 2026-11-23

Continuation: prepare private phone hosting while preserving the existing dashboard and analytics.

### Added
- Optional `publish.py` helper, called after local builds by sync, the dashboard CLI and the
  existing MCP `build_dashboard` tool. Disabled by default. Requires a dedicated Cloudflare Pages
  Direct Upload project, production and wildcard-preview Access apps, one exact-email Allow policy
  each, and anonymous login redirects before uploading. Rejects overlapping paths, bypasses,
  destination overrides, and custom domains. Stages only HTML and fixed privacy headers.
- `python -m garmin_mcp.publish --check` checks configuration without uploading. Publishing errors
  are reported separately from the local build. Tokens stay in the environment/ignored local `.env`.
- Regression coverage for refused uploads, private configuration, staging, error redaction,
  pagination, disabled/check-only modes, and sync retaining its local dashboard after upload failure.
- `docs/CONTINUATION_REVIEW.md`: code map, verified evolution, documentation drift and validation limits.
  Hosting comparison and primary-source evidence in `research_notes/.../private_dashboard_hosting.md`.

### Fixed
- Constant baseline-adjusted signals crashed `engine.relationship` by indexing an empty bootstrap
  list, preventing dashboard collection. Now unavailable with a reason; no correlation or confidence
  interval is invented. Baselines, sample requirements, bootstrap and FDR rules are unchanged.
- Mac setup now pulls `main` with `--ff-only`, replacing an obsolete feature branch.
- Internal package version now matches the project version (previously still 0.11.0).
- README/dashboard hosting docs now distinguish the default data path, conditional iCloud copy,
  unverified phone behavior, manual snapshots and optional hosting. Roadmap deployment status no
  longer waits on the manual update already marked complete.

### Validation and remaining work
- Baseline: 59 tests and Ruff passed. Final local suite: 84 tests and Ruff passed on Python 3.12.14.
- Rendered dashboard HTML is byte-identical to main's renderer for the same synthetic input.
  Chromium checked 48 page/width/theme states at 390/768/1200 px, light/dark: correct fragment
  navigation, no document overflow, broken fragment links, page errors or scripts.
- MCP stdio initialization, 43 tools, and synthetic `data_coverage`/`build_dashboard` calls checked.
- No live deployment, Garmin access, health-data upload or Mac/iCloud/phone verification. Access
  pricing/seat eligibility still needs confirmation; Pages file/build limits and the two-app
  Access requirement were verified from Cloudflare's official documentation source.
- VO2max norms remain blocked on primary-table retrieval; no values/formulas invented. Full visual
  design review and improvements remain pending. Existing empty-database dashboard failure recorded.
- GitHub API access is blocked by cloud network policy; PR, CI and merge remain unverified.
  See ROADMAP A–D for the remaining work. No new MCP tool was added (still 43).

## [0.13.0] - 2026-11-23

Phase 13: correlations explorer, test-run tracking, recovery weighting study. 43 tools.

### Added
- **Patterns page is now an explorer:**
  - Every tested pair is ranked by strength, each with a scatter of baseline-adjusted days (0 = your usual), the fitted line, and a "how sure" meter from the 95 % CI and false-discovery control.
  - Exact r, CI and n are behind "Details".
  - Code: `engine.pair_points`, `engine.explore`, `dashboard.scatter`, `dashboard._sure`. Tool: `explore_relationships`.
- **Test-run tracking** (roadmap 8.11): `running.test_runs` and tool `test_runs`.
  - Steady runs within ±10 % of your usual distance, or named "test"/"calibration".
  - Efficiency factor trend (Theil-Sen, % per 90 days).
  - Card on the Running page.
- **Recovery weighting study:** `scores.weight_study` and tool `recovery_weight_study`. Each Recovery % signal is checked against next-night HRV and against Garmin readiness, and alternative weightings are compared. The weights change only if a variant wins on both by > 0.05 r.

### Findings (real data, 180 days)
- **Every signal earns its place:**
  - HRV 7-day → next-night HRV r = 0.42.
  - Breathing → next-night HRV r = 0.31.
  - Resting HR → next-night HRV r = 0.26.
  - Sleep → next-night HRV r = 0.07, but → Garmin readiness r = 0.47.
- **Equal weights kept.** Current composite: r = 0.36 with next-night HRV and 0.36 with Garmin. "Without breathing" is better on Garmin (0.41) but worse on HRV (0.33). "HRV + RHR" is the reverse.
- **Why ours and Garmin's disagree:** Garmin leans on sleep, ours weighs physiology. Documented in HANDOVER §9.
- **Test runs:** 3 comparable ~5.2 km runs, efficiency +1.8 % per 90 days (too few runs to trust yet; labelled).
- **Strongest patterns:**
  - Sleep → Garmin readiness r = 0.50 ("very sure").
  - Daytime stress → next-night HRV r = −0.26.
  - Later bedtime → shorter sleep r = −0.25.

### Added
- `HANDOVER.md`: goal, story, why, a reference table for every calculation (code → formula → source → METRICS section), dashboard references, exact differences from Garmin and other apps, known issues, and the ordered list of what's left, so another person or AI can continue.

## [0.12.0] - 2026-11-23

Phase 11 (dashboard v2) and Phase 12 (health and running analytics). 40 tools.

### Added
- **Dashboard v2** (`dashboard.py`, rebuilt): one self-contained HTML file with 7 linked pages plus one page per run (Today, Sleep, Recovery, Training, Running, Run detail, Body, Patterns).
  - No JavaScript and no CDN; pages switch with CSS `:target`, so it works offline, from iCloud Drive or as a private Artifact.
  - Three-dial hero, "Why" rows against your personal range, 14-day recovery bars, drill-down tiles.
  - Inline-SVG charts with native tooltips, one axis per chart, separate phone and desktop drawings so text stays 10–16 px.
  - Garmin colour gauges for running form with a hollow marker for "your usual at this pace".
  - Design system written down in `DASHBOARD_PLAN.md` §6–8 (type scale, 4 px spacing grid, radii, icon and line sizes). Palette validated light + dark with the dataviz validator.
  - Copied to `iCloud Drive/Garmin/dashboard.html` after each build when iCloud Drive exists.
- **`health.py`** + tools `sleep_breakdown`, `long_term_health`, `monthly_report`:
  - Sleep breakdown: Garmin sub-scores with ratings and optimal ranges.
  - Heart-rate dip: day vs night HR, ≥ 10 % = healthy dip.
  - Pace of ageing: fitness-age trend in years per year; needs ≥ 90 days of history.
  - Marathon shape: Runalyze formula, read from Runalyze source.
  - Shift detection in resting HR / HRV / sleep (two-segment mean shift, ≥ 1 SD, ≥ 14 days each side).
  - Month-vs-month report.
- **Activity status:** days tagged `sick` / `injured` / `break` / `illness` (via `add_tag`) are left out of recovery baselines and pause training advice.
- **`running.py`** + tools `running_breakdown`, `running_form_history`:
  - Garmin colour bands for cadence, ground contact, vertical oscillation and vertical ratio (verified against Garmin's manual).
  - Your own cadence-vs-speed and stride-vs-speed lines, with each run shown versus your usual at the same pace.
  - Running effectiveness (speed ÷ W/kg).
  - Pacing and HR drift.
  - 1–3 evidence-based things to work on, e.g. cadence +5 % for knee load (Heiderscheit 2011, Willy 2016).
- **Sync gate** (`sync.py`): the 3-hourly job does a full sync only if ≥ 11 h have passed since the last one, or if today's activity list shows a new activity. Otherwise it is a single cheap call. This matches syncing the phone morning and night. `--force` skips the gate.
- Research note `running_form_benchmarks.md` (Garmin bands, Runalyze shape source, RE definition, cadence/knee studies).
- Repo onboarding for people and other AI assistants: `ARCHITECTURE.md`, `AGENTS.md`, README overview and repo map.

### Fixed
- Pace of ageing was 3.1 from 30 days of data (a 0.3-year wobble × 12). Now needs ≥ 90 days of span and uses Whoop's scale (1.0 = calendar pace).
- Bedtime chart used UTC timestamps; now local time (Asia/Kolkata) via the engine's timezone.

### Findings (real data, 23 Nov)
- Latest run: cadence 167 spm (green), ground contact 273 ms (green), vertical ratio 8.7 % (orange, borderline). HR drift 7.8 % → aerobic base is the limiter.
- Marathon shape 1 %: 1.1 km a week vs about 65 km needed at your fitness. Accurate, not a bug.
- Lasting shifts since June: resting HR −2.4 bpm, HRV +4.9 ms (both better).

## [0.11.0] - 2026-11-23

Phase 10a: glanceable daily scores, self-update, CI, dashboard plan.

### Added
- `scores.py` + tool `daily_scores` (35 tools):
  - Recovery % = Φ(our readiness z), with Whoop-style bands and the number of signals used.
  - Sleep % = hours / need, with 7-day debt.
  - Strain 0–21 on a log scale of TRIMP, with a target band set by the recovery colour.
  - Suggested bedtime from your usual wake time in Asia/Kolkata.
- Sense checks for the new scores, in `garmin-mcp-verify`:
  - Recovery % vs Garmin readiness r = 0.35.
  - Sleep % vs Garmin sleep score r = 0.85.
  - Bands spread (35 % green, 22 % red), strain within 0–21.
- `DASHBOARD_PLAN.md`: platform comparison (local web page chosen), Whoop/Oura/Fitbit-inspired layout, design rules from the dataviz skill, build steps (Phase 11).
- Self-update from `main` on every sync, settings seeding from `config/athlete.json`, GitHub CI (see entries below).

### Fixed
- Strain calibration: the first anchor (TRIMP 250 = 21) put a 27-min easy run at 16.1. Now `6.3·ln(1 + TRIMP/20)`: easy run ≈ 9, hard 2 h ≈ 16, cap 21. Pinned by tests.

### Findings
- Sleep timing verified against Garmin's local timestamps: typical sleep ~02:30–05:30 IST, wake ~08:00–11:00 IST, about 6.3 h vs ~8.5 h need. This is the main thing holding recovery back.
- Max HR is the key open question. Data supports 188, but Garmin's model implies ~209: with 209, effective VO2max (≈ 48) matches Garmin's 51 and its "aerobic base" labels fit. The sense check stays flagged until a hard-effort test settles it.

### Changed
- ROADMAP: Phase 10 split (10a done); Phase 11 dashboard v2; Phase 12 remaining items; full backlog; dropped items flagged with reasons.

### Added
- **Self-update** (`autoupdate.py`): every scheduled sync fast-forwards the Mac checkout to the latest tested `main`, reinstalls only when the code changed, and re-runs on the new code. Skipped on local changes; disable with `GARMIN_AUTO_UPDATE=0` or `--no-update`. Ends manual "git pull" steps.
- **Settings seeding:** `config/athlete.json` (private repo, no secrets) is applied to any machine's database for keys not yet set: timezone, goals, knee limitation.
- **GitHub CI** (`.github/workflows/ci.yml`): ruff + pytest on Python 3.12 and 3.13 for every push and PR.

## [0.10.0] - 2026-11-23

Phase 9: dashboard.

### Added
- `dashboard.py` + `garmin-mcp-dashboard` + tool `build_dashboard`: one static HTML file (data embedded, Chart.js 4.4.1 from cdnjs), mobile-friendly, light/dark. Rebuilt automatically after every sync.
  - Panels: today (our readiness and Garmin's), vitals vs personal range, insight feed, HRV with normal band, fitness/fatigue/form with Garmin acute load, sleep, resting HR, race predictions, pace curve, recent runs with form metrics, week, 90-day trends, patterns, 26-week load calendar, swims, strength.
  - Garmin values carry a "G" badge.
  - Checked in a headless browser at 1200 px and 390 px: no script errors, no horizontal scroll.

## [0.9.0] - 2026-11-23

Phase 8: analytics and insight engine.

### Added
- `engine.py` + tools `insight_feed`, `relationships`, `trends_and_patterns`, `records_and_calendar`, `add_tag`, `tag_impact` (34 tools total):
  - Level 1: calendar, personal-best timeline, streaks, Theil-Sen trends with confidence intervals.
  - Level 2: baseline-adjusted relationships (14 pairs) with block-bootstrap CIs and Benjamini–Hochberg control; weekday patterns; personal ranges (Fitbit/Oura style); tag impact (Whoop style).
  - Level 3: HRV-guided advice, load and long-run jump flags, form as % of fitness (intervals.icu).
- Calibration: false-positive rate measured at 1.7 % on 60 no-effect datasets (target ≤ 5 %); a test now checks it.
- On your data, four relationships pass the bar:
  - Sleep → Garmin readiness (r = 0.50).
  - Daytime stress → next-night HRV (r = −0.26).
  - Bedtime → sleep duration (r = −0.25).
  - Sleep → resting HR (r = −0.16).
  - 90-day trends: HRV rising (+2.0 ms per 30 days), fitness rising.
- Research: `fitbit_whoop_bevel.md` (Google Health/Fitbit, Whoop, Bevel, with Oura/Runalyze corrections). ROADMAP gains Phase 10 from it.

### Fixed
- Form % of fitness is suppressed below CTL 20. At CTL 7.8 a single run read as "−54 %, high fatigue", which is misleading.
- Dashboard sleep chart excludes incomplete (< 3 h) records.

### Notes
- Settings saved this round (timezone, knee, goals) exist in the development database only; tell Claude Desktop once on the Mac (ROADMAP "Needs from you" #6).

### Changed
- **HRmax policy:** max(repeatable activity peak, Tanaka 208 − 0.7·age), so a one-off optical spike can't set it. On your data:
  - The single 193 bpm treadmill peak (10 Dec 2025) rose 41 bpm in about 60 s at easy pace and dropped 25 bpm in 20 s at the same speed, so it is flagged as a probable spike.
  - Your repeatable peak is 177 bpm (7 runs); the Tanaka estimate for age 29 is 188.
  - Result: HRmax 188 bpm. Garmin's own setting rose from 193 to 211 over time with no matching recorded HR, so it is an internal estimate.
- "Today" follows a saved `timezone` athlete setting when `GARMIN_TZ` is not set.
- Workout templates add cautions when `injuries_or_limits` mentions the knee.

## [0.8.0] - 2026-11-23

Phase 7: workouts to the watch (ROADMAP 7.1).

### Added
- `workouts.py` + tools `workout_templates`, `create_workout`, `garmin_workouts`:
  - Structured running workouts from a small JSON spec (warmup, interval, recovery, cooldown, repeats; targets by pace, HR range or HR zone).
  - Built with python-garminconnect's own workout models.
  - Validated before anything is sent: paces 2:30–12:00/km, HR targets at or below your max HR, known step types.
  - Optional upload to Garmin Connect, scheduling, list and delete (unofficial login, Mac only).
  - Templates use your HR thresholds: easy, tempo, VO2 intervals, and a calibration test that fixes the "no all-out efforts" gap.
- Tests with a stand-in Garmin client (39 total). 27 MCP tools.

### Fixed
- `thresholds` no longer fails on a fresh database before the tidy tables are built.

### Notes
- A FIT workout file encoder was not built: after upload, Garmin Connect provides the workout file itself, which is more reliable than our own encoder.

## [0.7.0] - 2026-11-23

Phase 6: memory, goals, provenance (ROADMAP 6.1–6.4).

### Added
- `athlete.py`: settings, goals and notes, with explicit placeholders for inputs not yet given (tested max HR, LTHR, threshold pace, goal race, weekly km target, timezone, injuries). Overrides feed thresholds and all calculations. Tools `athlete_context`, `update_athlete_setting`, `add_athlete_note`.
- `goals.py` + tool `goal_check`:
  - Required pace and VDOT compared with predictions from several methods and Garmin's.
  - Verdict based on the **median** prediction, never the most optimistic one.
  - Cautions when methods disagree (> 10 %) or volume is below the usual range for the distance.
- Provenance block on every tool result (data date, last sync, source priority, `garmin_*` convention).
- `GARMIN_TZ` sets what "today" means.
- `ROADMAP.md`: Phase 8 (insight engine, levels 1–3) and Phase 9 (dashboard) added from the new research note; inputs table with placeholders; table of problems caused by incomplete information.

## [0.6.0] - 2026-11-23

Phase 5: workout coaching (ROADMAP 5.1–5.8).

### Added
- `coaching.py` + tools `run_analysis`, `running_form_trends`, `activity_stream`, `sport_trends`, `metric_glossary`, `fitness_age`:
  - 5.1 Efficiency factor (graded speed / HR) and aerobic decoupling (Pa:HR) for steady runs.
  - 5.2 Running form (cadence, step length, ground contact, vertical oscillation/ratio, power) compared with your norm **at matched pace** (±15 s/km, widening to ±30); monthly trends within your usual pace band.
  - 5.3 Facts for an activity recap (decoupling, splits, efficiency and form vs norm, heat, Garmin TE label).
  - 5.4 Downsampled activity stream.
  - 5.5 Personal heat effect: bpm per °C from your own runs.
  - 5.6 Metric glossary (meaning, typical range, unit, how to improve).
  - 5.7 Fitness age with Garmin's own levers and potential ages.
  - 5.8 Swim and strength trends.
- Sense check: our stream-derived running form vs Garmin's FIT session averages. Vertical ratio 0.22 %, ground contact 0.0 %, step length 0.03 %, cadence 1.2 % (median, 17 runs).
- `research_notes/.../insights_and_dashboards.md`: insight levels 1–3 with statistical rules, what others do and how, dashboard design, 24-item backlog.
- Tests (36 total).

### Fixed
- Goal verdict no longer picks the most optimistic prediction. Found while testing: a 50:00 10K looked "on track" despite a 26 % method spread and ~2 km/week volume.

## [0.5.0] - 2026-11-23

Phase 4: training load & performance (ROADMAP 4.1–4.11).

### Added
- `loads.py`:
  - 4.1 thresholds with Garmin's beside ours: HRmax (observed), resting HR (60-day median), LTHR (best 20-min run HR); sex from the watch profile.
  - 4.2 per-activity Banister TRIMP for every sport, plus rTSS (runs, only with a maximal critical speed).
  - 4.3 CTL/ATL/TSB and ramp rate.
  - 4.4 Seiler 3-zone time and Treff polarisation index.
  - 4.5 monotony and strain.
  - 4.6 pace-duration curve and critical speed with a submaximal-effort flag.
  - 4.7 race predictions by several methods beside Garmin's, including effective VO2max (Swain 1994) for submaximal training data, plus a low-volume warning.
- 4.8 `weekly_review`: last 7 days vs the previous 4 weeks.
- 4.10 Swim and strength analytics: FIT pool lengths (pace/100 m, strokes, SWOLF by stroke) and strength sets (exercise, reps, volume). New FIT tables: `fit_lengths`, `fit_sets`, `fit_zones` (Garmin's own zone times), `fit_profile`. `fit.reparse_all` re-reads stored FIT files without downloading.
- 4.11 Sense checks: our numbers vs Garmin's and physics (load correlation, VO2max, cadence × stride = speed, HR-zone times, thresholds). New tool `sense_checks`; also printed by `garmin-mcp-verify`.
- MCP tools `training_load`, `performance`, `weekly_review`, `sense_checks` (14 tools total).
- 4.9 Formula constants pinned by unit tests (33 tests total).
- `research_notes/.../running_and_sport_metrics.md`: running metric definitions and interactions, swim/strength metrics, Garmin Active Intelligence and Strava Athlete Intelligence notes (for later phases).

### Fixed
- HR-zone boundaries follow Garmin's exclusive upper bound; recomputed zone times now match Garmin's to 0–1 % on runs (was 8 %).

### Findings from the sense checks
- Garmin's max-HR setting (209) is 16 bpm above any HR recorded (193) and its LTHR (185) is above any sustained run HR (166). The observed values are used, and both are flagged.
- Best-effort predictions reflect training pace, because no recent run was all-out; effective VO2max predictions bracket Garmin's.

## [0.4.0] - 2026-11-23

Phase 3: recovery & readiness (ROADMAP items 3.1–3.6).

### Added
- `recovery.py` + MCP tools `readiness_today`, `recovery_trend`, `daily_brief`:
  - 3.1 HRV state: 7-day ln HRV vs 60-day normal band (± 0.5 SD), CV.
  - 3.2 Resting HR and respiration z-scores; sleep vs 28-day norm, 7-day sleep debt, bedtime consistency.
  - 3.3 Transparent readiness from component z-scores, shown next to Garmin's readiness.
  - 3.4 Illness/strain flag.
  - 3.5 Daily brief (morning-report style) with a rule-based suggestion and its reason.
- 3.6 Verified: 7-day rolling ln RMSSD with smallest worthwhile change (AIS guide, Plews et al.). The 60-day baseline is documented as our own choice.
- Tests for Phase 3 (28 total).

### Fixed
- Sleep records under 3 h (for example a 14-minute record) are flagged as incomplete and excluded from the sleep norm and debt, instead of raising a "short sleep" flag. The snapshot names the night each flag refers to.

## [0.3.1] - 2026-11-23

Data-quality pass (serves every phase: correct inputs).

### Added
- `garmin-mcp-verify`: cross-source agreement (every overlapping field), plausible physical ranges per column and unit, FIT running-form averages, fill rates. Exit code 1 on any problem. On the real data: all checks pass.
- Regression tests for units and timestamp formats (24 total).

### Fixed
- **Floors:** the Personal API's `floorsAscended.value` is a floor count; we stored it as metres. Now uses `distanceInMeters`. Daily distance now also comes from the same block.
- **Sleep start/end:** export timestamps (`2026-10-25T00:08:45.0`) and API timestamps now share one format (`2026-10-25 00:08:45`, UTC).
- **Lap cadence:** laps now report steps/min (×2 of FIT one-foot cadence) like the activity average.

### Notes on earlier gaps (for the record)
- **SpO2 and Body Battery (fixed in 0.3.0):** values were never wrong, they were *missing*. The export stores them under different names (`averageSpo2Value`; a `bodyBatteryStatList` of HIGHEST/LOWEST), so before 0.3.0 only the 30 API days had them. Coverage went from 30 to 445 (SpO2) and 705 (Body Battery) days.
- **Resting HR (fixed in 0.3.0):** the export's `restingHeartRate` is a 7-day value; the day's own is `currentDayRestingHeartRate`.
- **Known upstream differences:** daily min/max HR and sleep average HR differ by 1–3 bpm between Garmin's own sources on some days (Garmin recomputes). The official API value is used.

### Changed
- `ROADMAP.md` rewritten as the single main plan: every item from the research backlog (R1–R34), METRICS.md and earlier plans mapped to a phase and version; side-quest rule added.

## [0.3.0] - 2026-11-23

Phase 2: tidy tables and health snapshot.

### Added
- `normalize.py`: tidy per-day tables (`daily`, `sleep`, `hrv`, `health_status`, `readiness`, `training`, `race_predictions`, `scores`, `fitness_age`) built from all three sources, merged field by field (official API > unofficial > export). Rebuilt automatically after every sync and import.
- `insights.py` + MCP tools `health_snapshot`, `daily_summary`, `activities`, `activity_detail`, `trend`. Flags: short sleep, HRV below baseline band, resting HR ≥5 bpm over the 60-day mean, Garmin readiness LOW/POOR, adverse training status, intensity minutes under 150/week, missing last-night sleep.
- `data_coverage` now reports the tidy tables.
- `MAC_SETUP.md`: one instruction for a local Claude Code session to set everything up on the Mac.
- Tests for normalisation and insights (22 total).

### Changed
- All tools now read the local database (the four original live-calling tools were replaced).

### Fixed
- Export daily summaries: resting HR now uses the day's own value (`currentDayRestingHeartRate`); `restingHeartRate` there is a 7-day figure. Found by cross-checking against the Personal API: now 29/29 days agree, as do steps, calories, intensity minutes, stress, Body Battery and all sleep fields.
- Garmin's `-1` "no data" values for stress and Body Battery no longer leak into the tables.


### Added
- `garmin-mcp-import`: imports the Garmin account data export (ZIP or folder). Verified on a real export: 116 activities with FIT files (May 2024 → Nov 2026), ~900 days of daily summaries, readiness, training status, race predictions, endurance/hill score and acute load, 382 nights of sleep, 286 days of health status. Export units (ms, cm, speed ×10) converted to API units and cross-checked against API data (exact match).
- Tests for the importer (18 total).

### Added
- Research verification pass: Garmin score bands, wrist running dynamics, LT chest-strap requirement (see VERIFICATION_LOG.md).
- Official Garmin Personal API source, built on Garmin's own `garmin-connect-personal-api-python` client: 6 daily datasets, 8 windowed datasets (fetched in 28-day chunks for the API's history caps), activities with pagination, original FIT download, automatic token renewal on 401.
- `--source both` (now the default): official API first, then only the extras the official API lacks from the unofficial library. Either source failing is reported without blocking the other.
- Tests for the Personal API source (14 total).

### Fixed
- Sync now waits and retries on HTTP 429. Garmin's Personal API allows ~100 requests per window and returns `retryInSeconds`; previously the run aborted. Waits are counted in `rate_limit_waits`.
- `--coverage` now lists windowed datasets (Body Battery, stress, steps, VO2max, etc.).

### Verified on real data (2026-11-23)
- Official Personal API: 30 days synced, 0 errors. Unofficial extras: 7 days, 0 errors.
- A watch-only FR955 records vertical oscillation, ground contact time and stride length in FIT records (previously assumed to need a chest strap). Beat-to-beat HRV is not recorded (HRV logging is off on the watch).

### Changed
- Python 3.12+ required (official Garmin client requirement).
- README: key setup via a private key file, source modes, what each source covers.

## [0.2.0] - 2026-11-23

Phase 1: data foundation.

### Added
- Local SQLite store (`~/.garmin-mcp/garmin.db`): raw responses kept verbatim, typed tables for activities, FIT records, laps, sessions, beat-to-beat HRV, sync log.
- Incremental sync engine and `garmin-mcp-sync` CLI: skips stored days (refreshes last 2), isolates failing endpoints, aborts after repeated failures, polite delay between calls.
- Source adapters: `garminconnect` (16 daily datasets, 6 windowed, 5 per-activity details + original FIT), `personal_api` placeholder until the endpoints are verified.
- FIT parsing with Garmin's official `garmin-fit-sdk`.
- MCP tools `refresh_data` and `data_coverage`.
- `METRICS.md`: per-metric decisions comparing Garmin's method, the scientific method, and ours.
- Tests for sync rules and FIT parsing (11 total).


### Added
- `ROADMAP.md`: decisions (local laptop, official API first + unofficial add-on, watch-only sensors) and 8-phase build plan.
- `research_notes/Garmin connector feature research/`: findings log for connector design (FR955 metrics, AI connectors, analytics platforms, metric formulas).
- `reports/Garmin connector feature research.md`: synthesized findings, FR955 data inventory, architecture recommendation, phased feature backlog.
- `connected_connectors_inventory.md`: full tool inventory of Fitness AI Connector and AthleteData.
- `github_and_garmin_resources.md` (GitHub libraries + Garmin official options), `garmin_insights_reference.md` (Garmin insight calculations vs open equivalents), `FINDINGS.md` (quick-read index).

## [0.1.0] - 2026-11-22

### Added
- Python package `garmin_mcp` with an MCP server (MCP Python SDK 2.x, stdio transport).
- Tools: `get_daily_summary`, `get_sleep`, `get_heart_rate`, `get_recent_activities`.
- Token-based auth via `garminconnect` 0.3.x; one-time `python -m garmin_mcp.login` with MFA support.
- `garmin-mcp` console script, `.env.example`, `.gitignore`.
- Unit tests (pytest) and lint config (ruff).
- README with setup, Claude Desktop / Claude Code config, and tool reference.
- This changelog.
