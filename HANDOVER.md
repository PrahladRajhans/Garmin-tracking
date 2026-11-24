# Handover: Garmin-tracking (state at v0.25.0, 2026-11-24)

Read this first if you are a person or an AI (ChatGPT, Claude) picking up the project. It explains why the project exists, what has been built, where every formula and decision lives, how ours differs from Garmin and the apps it competes with, and what is left. Each claim points to a file, a function, or a section heading.

---

## Latest changes for reviewers

- **v0.25.0:** WHOOP-inspired local journal and weekly plan, wake follow-up and Sunday review,
  distance-aligned route replay, and Ollama compatibility and fictional benchmarks. See
  [governance](docs/OLLAMA.md) and [roadmap](ROADMAP.md#paid-coaching-research-and-local-delivery).

- Coaching records the last published daily decision and adds an evidence-led post-run review.
  Sleep now has nightly stage timelines where recorded, time-in-stage totals, period summaries,
  and a weekly bedtime proposal. See [the roadmap](ROADMAP.md#coaching-and-sleep-follow-up).


- **v0.24.0:** local Ollama work now starts from the existing archive when enabled or rebuilt.
  Skipped fetches retry pending items and the saved HTML carries a stamp for checked results.
  The model prioritizes an eligible Today follow-up and selects compact IDs for checked
  summaries. Recovery and Training have their own entry points into the evidence. See
  [Ollama coverage and checks](docs/OLLAMA.md) and the [remaining acceptance plan](ROADMAP.md).
- **v0.24.0 UI:** persistent phone tabs, sticky desktop navigation, direct neighboring day
  links, and tighter ordering of current readings, long-range charts, and optional estimates.
  The independent review found and verified fixes for worker contention and findings displaced by
  a cadence cue. See the [dashboard review](docs/UI_REVIEW.md).
- **v0.21.0 (Claude, PR #25):** `trials.py` follows up on experiments, the dashboard keeps
  high-resolution details for recent runs, and `weather_fetch.py` retrieves opt-in Open-Meteo
  readings. See the [release entry](CHANGELOG.md#0210---2026-11-24).
- **v0.22.0:** `narrator.py` supplies optional local prose from small JSON packets. Python
  still owns every calculation, verdict and action. Sync publishes the normal dashboard first.
  The worker verifies cloud is disabled, requests local-only inference, applies the lexical and
  whole-sentence checks, and caches the results. A matching snapshot can receive the cached prose
  in the Mac and iCloud copies. See [validator rules](METRICS.md#optional-local-narration-v0220),
  [Mac setup](MAC_SETUP.md#local-ai-narrator-optional), and `tests/test_narrator.py`.
- **Acceptance:** synthetic phone, tablet and laptop layouts show recovery, today's action and
  the weekly plan above the fold in both themes. Remaining checks on the owner's Mac and iPhone
  include actual model latency, the five-second impression with real data, the private link and
  the product review's 600 KB target.
- **v0.23.0:** chart drawings now fit the available card width. VO₂max follows the same
  responsive layout using a compact reference band. The version stamp prompts the Mac
  updater to rebuild older snapshots even when a scheduled run skips fetching Garmin.
  Run evidence now opens within one page, and the latest timelines offer multiple overlays.
  Training links to recent workout summaries, which can receive checked local narration.
  See [chart layout](DASHBOARD_PLAN.md#chart-sizing-v0230) and [Ollama governance](docs/OLLAMA.md).
- **Outdoor conditions (v0.23.0):** `environment_review.outdoor_patterns` reuses stored outdoor
  condition windows and local matched effort, and joins Garmin sleep/HRV/resting HR only after
  checking the following sleep interval. Review the Training card and its paired evidence,
  plus `tests/test_environment_review.py`. On the owner's Mac, check how many contrasts
  survive the coverage rules before drawing conclusions about personal recovery.

## 1. The goal

**Get every piece of Garmin Forerunner 955 data, with full history, into one private place, and turn it into insights that are correct, transparent and simple to read. Deliver them two ways: through Claude (MCP tools) and through a glanceable dashboard. Match or beat the paid connectors and wellness apps, for free.**

## 2. The story

1. **The problem.** The user wears a Forerunner 955 and wanted an AI to answer questions about their health and training.
   - The options were paid: Fitness AI Connector and AthleteData, both cloud MCP connectors.
   - Or they were closed apps: Whoop, Oura, Fitbit, Bevel, Strava Athlete Intelligence, Garmin Active Intelligence.
   - None of them show *how* a number is calculated, and none let you check it.
2. **Research first** (`research_notes/Garmin connector feature research/`).
   - What each connector and app offers: `ai_connectors.md`, `fitbit_whoop_bevel.md`, `analytics_platforms.md`.
   - Everything the FR955 records: `fr955_metrics.md`.
   - How Garmin computes its own insights: `garmin_insights_reference.md`.
   - Published formulas: `metric_formulas.md`, `running_and_sport_metrics.md`, `running_form_benchmarks.md`.
   - Dashboard practice: `insights_and_dashboards.md`.
   - Verification of Garmin labels: `VERIFICATION_LOG.md`.
   - Summary and decisions: `FINDINGS.md`.
3. **Data first, analytics second** (Phases 1–2).
   - Pull from three sources: the official Personal API, the unofficial `garminconnect` library, and the account export for history.
   - Store raw responses verbatim, then normalise into tidy tables.
   - Audit units against Garmin, which found and fixed a string of bugs (`CHANGELOG.md` 0.3.1).
4. **Transparent analytics** (Phases 3–8): recovery, training load, performance, run coaching, goals, workouts to the watch, and an insight engine with proper statistics.
5. **Glanceable layer** (Phases 9–12): Whoop-style daily scores, a multi-page dashboard, sleep and running breakdowns, long-term signals.
6. **Runs itself on the user's Mac.**
   - launchd syncs every 3 hours behind a gate.
   - The code updates itself from `main` on every sync.
   - Settings come from `config/athlete.json`.

## 3. Why build it rather than buy it
| Reason | What it means in the code |
|---|---|
| **Transparency** | Every derived number has a written formula (`METRICS.md`) and its inputs are returned with it, e.g. `recovery.readiness` returns each component z-score |
| **Correctness** | Numbers are sense-checked against Garmin's own values and physics (`loads.sense_checks`, `scores.sense_checks`, `garmin-mcp-verify` → `verify.py`) |
| **Honesty about thin data** | `calibrating`, `signals_used`, `available: false` + `reason` instead of a guess |
| **Privacy** | Data stays in SQLite on the Mac; nothing leaves unless the user opts in |
| **Cost** | Free; uses the user's own Garmin access |
| **Personal** | Baselines, ranges and "your usual at this pace" are from *your* history, not population averages |

## 4. User context
- Male, 29, 76.5 kg.
- FR955, wrist heart rate only (no chest strap). Max HR not tested.
- Asia/Kolkata time zone.
- Right knee a little weak. Cadence is interpreted against the athlete’s own pace-matched history.
- No goal race: general fitness, marathon some day.
- Syncs the phone about twice a day, morning and night.
- Wants plain language, no jargon on screen, and one consolidated plan (`ROADMAP.md`).
- Settings are stored in `config/athlete.json`.

## 5. Map of documents
| Document | What it holds |
|---|---|
| `README.md` | Install, tools table, sync, dashboard, configuration |
| `ARCHITECTURE.md` | Data flow diagram, module map, principles |
| `AGENTS.md` | Rules for AI contributors (also in `CLAUDE.md`) |
| `ROADMAP.md` | The single plan: phases, versions, needs from user, backlog, dropped items with reasons |
| `METRICS.md` | Every formula, by version section, plus the sense-check table and HRmax policy |
| `DASHBOARD_PLAN.md` | §1 platform decision, §2 what we copied from which app, §4 design rules, §6 UI map, §7 design system, §8 hosting |
| `CHANGELOG.md` | What changed per version, with real-data findings |
| `MAC_SETUP.md` | One-time Mac setup and launchd schedule |
| `docs/screenshots/` | Current dashboard (phone light, desktop dark) |

## 6. References: where every calculation lives
Paths are under `src/garmin_mcp/`. "M §" means the section of `METRICS.md`.

### Recovery and sleep
| What | Code | Formula / rule | Source | Spec |
|---|---|---|---|---|
| HRV status | `recovery.hrv_status` | 7-day mean of ln RMSSD vs 60-day mean ± 0.5 SD | Plews/Buchheit-style smallest worthwhile change | M § v0.4.0 |
| Seven-day plan | `training_plan.week` | Prior four weekly run volumes and current recovery/status guide an easy starting plan | Conservative planning heuristic | M § v0.18.0 |
| Our readiness | `recovery.readiness` | Mean of signed z-scores clipped ±3: HRV +, sleep +, resting HR −, respiration − | Heuristic (documented) | M § v0.4.0 |
| Illness flag | `recovery.illness_flag` | ≥ 2 of {HRV z < −1, RHR z > +1, resp z > +1} on 2 days | Heuristic | M § v0.4.0 |
| Training suggestion | `recovery.suggestion` | Rule table; paused if the day is tagged sick/injured/break | — | M § v0.4.0, v0.12.0 |
| Activity status | `health.status_days`, used in `recovery.load_series` | Tagged days are left out of baselines | Bevel | M § v0.12.0 |
| Recovery % | `scores.daily_scores`, `scores.phi` | 100·Φ(readiness z) with ≥3 signals; green ≥ 67, yellow 34–66, red ≤ 33 | Whoop bands | M § v0.11.0 |
| Sleep % | `scores.daily_scores` | Hours ÷ Garmin sleep need (8 h planning fallback); < 3 h = incomplete | Whoop | M § v0.11.0 |
| Sleep debt, bedtime | `recovery.sleep_status`, `scores.bedtime_suggestion` | Σ shortfall over 7 valid nights; bedtime = median wake − need − min(60, debt/7) | Garmin sleep coach / Whoop | M § v0.4.0, v0.11.0 |
| Sleep breakdown | `health.sleep_breakdown` | Garmin `sleepScores` parts with ratings and optimal ranges | Garmin, Fitbit | M § v0.12.0 |
| Heart-rate difference | `health.heart_rate_dip` | (recorded awake mean − sleep mean) ÷ awake mean; UTC, known sleep windows excluded; no health cutoff | Descriptive; prior BP-derived cutoff removed | M § v0.13.3 |

### Load and fitness
| What | Code | Formula / rule | Source | Spec |
|---|---|---|---|---|
| Strain 0–21 | `scores.strain_from_trimp` | min(21, 6.3·ln(1 + TRIMP/20)) | Whoop scale; our calibration | M § v0.11.0 |
| TRIMP | `loads.banister_trimp` | Per second, men 0.64·e^(1.92x) | Banister 1991 | M § v0.5.0 |
| Fitness / fatigue (CTL/ATL/TSB) | `loads.ewma`, `loads.rebuild` | λ = 1 − e^(−1/N), N = 42 / 7; TSB = yesterday's values | Banister / Coggan PMC | M § v0.5.0 |
| HRmax, LTHR, resting HR | `loads.thresholds` | max(repeatable peak ±3 bpm, Tanaka 208 − 0.7·age); LTHR = best 20-min run HR | Tanaka 2001, Friel | M § HRmax policy |

### Performance and running
| What | Code | Formula / rule | Source | Spec |
|---|---|---|---|---|
| Effective VO2max | `loads.effective_vo2max` | Daniels VO2(speed) ÷ Swain %VO2max(%HRmax) | Daniels; Swain 1994; Runalyze | M § v0.5.0 |
| VO2max reference bar | `norms.reference`, `norms.comparison`, `dashboard.vo2_reference` | Exact seven FRIEND percentile thresholds for recorded sex and age decade; separate estimate markers, no percentile interpolation | Kaminsky et al. 2015, primary Table 3 | M § v0.14.0 |
| Critical speed | `loads.critical_speed` | 2-parameter fit, 3–20 min efforts; flagged submaximal unless 50 ≤ D′ ≤ 400 m | Monod & Scherrer | M § v0.5.0 |
| Race predictions | `loads.race_predictions` | Effective VO2max/VDOT, best-effort VDOT, Riegel 1.06, Garmin's, side by side | Daniels, Riegel | M § v0.5.0 |
| Run metrics | `coaching.run_metrics` | Time-weighted speed/HR and equal moving-time efficiency halves, cadence ×2, vertical ratio, interpolated elapsed km splits | Friel, TrainingPeaks | M § v0.6.0 |
| Running form bands | `running.GAUGES`, `running.rate` | Garmin 5-colour bands (cadence, ground contact, vertical oscillation, vertical ratio) | Garmin manual (`running_form_benchmarks.md`) | M § v0.12.0 |
| Pace-matched form | `running.personal_lines`, `running.running_breakdown` | Least squares of each metric vs speed, within the observed speed range | Moore 2016 | M § v0.12.0, v0.17.0 |
| Matched effort | `run_evidence.matched_effort` | Moving HR minus the median of 3–8 earlier steady efforts of the same type, similar pace, duration and climb | Within-athlete descriptive comparison | M § v0.17.0 |
| Readiness benchmark | `readiness_benchmark.benchmark` | Prior-timestamped Garmin score vs matched HR difference; Spearman on ≥20 days | Study design inspired by Gneta | M § v0.17.0 |
| Workout conditions | `conditions.for_activity`, `conditions.for_samples` | Garmin snapshot plus separate UTC source windows, with units and AQI standard | Environmental feasibility note and endpoint evidence | M § v0.17.0 |
| What to work on | `running.suggestions` | Optional measured cadence trial with a knee note; personal form, pacing and effort comparisons | Heiderscheit 2011, Lenhart 2014, Willy 2016 | M § v0.12.0 |
| Running effectiveness | `running.running_breakdown` | speed ÷ (W/kg) | Coggan / WKO (Palladino) | M § v0.12.0 |
| Marathon shape | `health.marathon_shape` | Runalyze: weekly target V^1.135, long-run target 12·ln(V/4) | Runalyze source code | M § v0.12.0 |

### Long-term signals and patterns
| What | Code | Formula / rule | Source | Spec |
|---|---|---|---|---|
| Pace of ageing | `health.pace_of_ageing` | Theil-Sen slope of fitness age × 365; needs ≥ 90-day span | Whoop scale | M § v0.12.0 |
| Shifts | `health.detect_shift`, `health.shifts` | Best two-segment split ≥ 1 SD, ≥ 14 days each side | Simple changepoint | M § v0.12.0 |
| Monthly report | `health.monthly_report` | Month vs previous month with observation counts and one HRV reading per day | Fitbit/Whoop; source precedence as in recovery | M § v0.12.0, v0.14.3 |
| Relationships | `engine.relationship`, `engine.relationships`, `engine.bh_adjust` | Baseline-adjusted Pearson r, 7-day block bootstrap CI, Benjamini-Hochberg q < 0.10, abs(r) ≥ 0.15; measured false-positive rate 1.7 % | Standard statistics | M § v0.9.0 |
| Constant signals | `engine.relationship` | Returns unavailable with a reason instead of indexing an empty bootstrap result | No change to formulas or statistical thresholds | M § v0.13.1 |
| Trends, ranges | `engine.trends`, `engine.theil_sen`, `engine.personal_ranges` | Theil-Sen with bootstrap CI; current-day Garmin bands or preceding 60-day ± 1 SD with minimum observations; no stale values | Fitbit "in your range" | M § v0.9.0, Personal-range freshness v0.14.1 |
| Correlations explorer | `engine.pair_points`, `engine.explore`; page `dashboard.page_patterns` | Same statistics as relationships, with paired dates, sample size, evidence rule and visible fit only for qualifying pairs | — | M § v0.13.0 |
| Test-run tracking | `running.test_runs` | Steady outdoor runs within ±10 % of their median distance, on at least three dates; efficiency factor Theil-Sen trend | Friel EF | M § v0.13.0 |
| Recovery weighting study | `scores.weight_study` | Each signal and composite vs next-night ln-HRV z and vs Garmin readiness; change weights only if better on both by > 0.05 r | — | M § v0.13.0 |
| Goal verdict | `goals.goal_check` | Median of prediction methods vs target | — | M § v0.6.0 |

**Sense checks on real data** (M § Sense checks; `CHANGELOG.md` per version):
- Our acute load vs Garmin's: r = 0.81.
- Per-run TRIMP vs Garmin load: r = 0.92.
- Recovery % vs Garmin readiness: r = 0.35.
- Sleep % vs Garmin sleep score: r = 0.85.
- Running form vs Garmin session averages: within 0–1.2 %.
- HR-zone time vs Garmin's: 0–1 % on runs.

## 7. Dashboard references
- **Code:** `dashboard.py`.
  - `collect` gathers the data; the `page_*` functions build each page.
  - Chart kit: `dial`, `line_chart`, `bar_chart`, `gauge`, `both` (separate phone and desktop drawings).
  - `CSS` holds the design tokens.
- **Design:** `DASHBOARD_PLAN.md` §6 is the page map, §7 the type scale, spacing, shapes, icons, line weights and colour, §8 hosting.
- **Colour:** palette and rules from the dataviz skill. Categorical blue `#2a78d6` and orange `#eb6834` (dark: `#3987e5`, `#d95926`) passed its validator in both modes. Status colours are reserved for state and always shown with a word.
- **How it works:**
  - Pages switch with CSS `:target` (`body:has(.page:target) #today:not(:target)`).
  - Tooltips use SVG `<title>`.
  - Rebuilt after every sync (`sync.py`) and copied to iCloud Drive.
- **Tests:** `tests/test_dashboard.py`.
- **Optional hosting (v0.13.1):** `publish.publish_if_enabled` uploads only the HTML and fixed
  privacy headers after checking Access on the production and wildcard-preview hostnames.
  Called after local builds by sync, the dashboard CLI, and the MCP build tool. Disabled by
  default. Account setup, pricing confirmation, and live phone validation remain pending;
  see `MAC_SETUP.md` and the hosting research note.

## 8. What is different, and exactly how
### Ours vs Garmin
| Topic | Garmin | Ours | Where |
|---|---|---|---|
| Max HR | Model value about 209 | 188: repeatable observed peak or Tanaka; a 193 treadmill spike rejected | M § HRmax policy |
| Readiness | Proprietary score | z-scores of 4 signals vs your baselines, all shown; Garmin's beside it | `recovery.readiness` |
| VO2max | 51.4 (Firstbeat) | Effective VO2max about 40 at HRmax 188 (about 48 at 209) | M § Open question |
| HR zones | Garmin settings | Our thresholds; upper bounds exclusive, matching Garmin's FIT zone times | M § v0.5.0 |
| Load model | Acute and chronic load, proprietary | Banister TRIMP + exponential CTL/ATL | M § v0.5.0 |
| Running form | Colour gauges vs everyone | Same gauges **plus** you vs your usual at the same pace | `running.py` |

### Ours vs other methods and apps
| Topic | Others | Ours | Where |
|---|---|---|---|
| CTL/ATL smoothing | TrainingPeaks λ = 1/N | λ = 1 − e^(−1/N) (true exponential); numbers differ slightly | M § v0.5.0 |
| Recovery / strain | Whoop proprietary | Whoop *scale and bands* only; formulas are ours and published | M § v0.11.0 |
| Readiness bands | Oura 85/70/60 | Dropped in favour of Whoop's 3 colours | `ROADMAP.md` dropped list |
| Correlations | Whoop/Bevel show associations without uncertainty | Bootstrap CIs, false-discovery control and paired-day evidence | M § v0.9.0 |
| Connectors | Fitness AI Connector, AthleteData: cloud, paid | Local, free, formulas visible | `research_notes/.../ai_connectors.md` |

## 9. Known issues and open questions
The dashboard now shows the ranked engine findings on Today. An older snapshot asks for a
sync before giving current training guidance. The appearance switch and direct chart cursor
need a browser that runs scripts. Device testing still includes iPhone Files and Safari.
**Validation status:** CI and browser evidence use synthetic data. The Mac archive still needs
verification. The read-only `garmin-mcp-verify --run-timing` report compares paired watch and
stream timing/HR values by year. Monthly coverage exposes gaps and the Patterns policy stays
exploratory. Historical coefficients below are dated observations.
1. **Max HR is uncertain** (188 vs 209). It moves zones, TRIMP, effective VO2max and race predictions. Fix: user's hard-effort test, then `update_athlete_setting("hr_max_override", value)`.
2. **Recovery % disagrees with Garmin readiness on some days** (overall r = 0.36; on 22 Nov ours was 34 %, Garmin's 90). *Studied in v0.13 (`recovery_weight_study`):*
   - Sleep drives Garmin's score (r = 0.47) but barely predicts next-night HRV (0.07).
   - Breathing and resting HR predict next-night HRV (0.31, 0.26).
   - No reweighting wins on both outcomes, so equal weights stay. The disagreement is a difference in what each score measures, not a bug.
   - Re-run the study after about 3 months of new data.
3. **Effective VO2max sense check is flagged** (about 40 vs Garmin's 51.4). Mostly the max HR question.
4. **Wrist running power** reads higher than Stryd, so running effectiveness (0.71) is only for tracking yourself over time.
5. **Little running data** (about 1 km/week lately, 19 runs with FIT data). Half and marathon predictions are unreliable and Marathon shape is about 1 %. This is accurate, not a bug.
6. **Fitness-age history** covers about 30 days, so pace of ageing is hidden until it spans 90.
7. **Garmin sleep part scores** (Duration, Awakenings, …) come as ratings only, without values, from the Personal API.
8. **iCloud copy** (`dashboard.build`) has not been tested on the Mac. It writes to `~/Library/Mobile Documents/com~apple~CloudDocs/Garmin/`.
9. **Private phone hosting:** optional publishing code is tested with stand-ins, not a live
   account. No health data was uploaded. Cloudflare's preview Access switch alone does not
   protect the production address. The helper requires both apps and refuses conflicting
   paths, bypasses, custom domains, and policies that allow anyone beyond the configured email.
10. **Fresh database (resolved v0.14.1):** all seven dashboard pages now show a waiting state
    until data is available; no fake scores or reassuring advice are generated.
11. **Review update:** network access is restored; PR #8 passed both CI jobs and was merged.
    The primary FRIEND paper is now accessible and its Table 3 bar is implemented in v0.14.0.
    Local checks still do not establish Mac/iPhone/live Garmin health.
12. **Sync/update reliability (v0.13.2):** the gate uses `meta.last_full_sync` plus
    `sync_retry_required`; endpoint timestamps no longer imply completion. Dates are local.
    Pagination/chunk loops are guarded. Failed dependency installs stop sync and are retried
    using per-checkout `pending-install-*.json` markers in the data folder. See `docs/OPERATIONS.md`.
13. **Accuracy review (v0.13.3):** shared 8-hour planning fallback, baseline sufficiency,
    unavailable advice, UTC/known-sleep HR comparison and input validation corrected. Weight
    studies now include HRV-only days, use matched composite comparison days, and handle zero
    correlations correctly. Historical study results above predate these corrections; rerun
    on real data before using them to propose a weight change. Actual weights remain equal.

## 10. What is left (pick up here)

The request audit in `docs/PROGRESS_AUDIT.md` tracks completed UI work and remaining
validation. Use ROADMAP for order. Start by verifying the signal comparisons against
the scheduled Mac checkout and rebuild. A review reported that v0.17.0 built successfully
on a copy of the real archive, while the scheduled Mac checkout had fallen behind.
Confirm both the footer’s code version and an advancing complete-sync timestamp.
v0.18.0 adds an easy weekly starting plan, a sourced cadence trial, a three-signal score
gate and a lighter archive view. Detailed daily readings older than 30 days stay available
through MCP. The next coaching step is to record a trial and compare the later experience. v0.17.0 adds
matched effort evidence, a retrospective Garmin readiness benchmark and an optional local
weather/AQI window import. Automatic geolocation, station/model comparison and sleep
exposure remain open. Use README to import or remove windows and METRICS to review the
selection and timing rules.
The next checks are the Mac archive, iPhone interaction, then private phone hosting. Code for the VO₂max bar,
pacing and monthly drill-downs, and evidence-first Patterns is on the GitHub delivery track.
The table below describes the rest of the work. ROADMAP owns ordering and status.

| # | Item | Where | Done when |
|---|---|---|---|
| ✅ | Correlations explorer, test-run tracking, recovery weighting study | Done in v0.13.0 | See CHANGELOG 0.13.0 |
| A (first) | **Activate private phone hosting** | `publish.py`, `MAC_SETUP.md` | Account/free-plan check, both Access apps, local token, anonymous denial, owner OTP, phone links, next scheduled upload all verified |
| 1 | **Add more pairs to the explorer** if useful: e.g. alcohol/travel tags → HRV is already in `tag_impact`; respiration → HRV | `engine.PAIRS` | New pairs pass the same FDR rule |
| 2 | **Test runs with more data**: validate comparable efforts on the archive, then assess route matching | `run_evidence.py`, `fit_records`, `running.test_runs` | Check individual matches, coverage and GPS path similarity. Shared endpoints alone do not establish the same route. |
| 3 | **Race readiness and taper** (8.12): once a goal race is set | `goals.py` + `health.marathon_shape` + fitness/form | Only when the user sets a race |
| ✅ 4 | **VO2max range bar by age and sex** (10.8) | Body page, v0.14.0 | Exact FRIEND 2015 Table 3 values, full citation, separate estimates and caveats; live profile/data verification remains on Mac |
| 5 | **Re-run the recovery weighting study** every ~3 months (`recovery_weight_study`) | `scores.weight_study` | Weights change only by its rule |
| 6 | **Max HR test → recalculate** | `athlete` setting | User runs the test; check that the effective VO2max flag clears |
| 7 | **Dashboard on phone**: Cloudflare candidate implemented but inactive; iCloud and manual private Artifact remain alternatives | `dashboard.build`, `publish.py` | User confirms private access and working links on the phone |
| 8 | **v1.0.0**: everything running unattended on the Mac for 2 weeks with no sync errors | `sync_log`, `garmin-mcp-verify` | `ROADMAP.md` D.1 closed |
| Later, only if the user asks | intervals.icu source (R32), Apple Health import (R33), multi-device dedupe (R34) | `sources/` | — |

The user's continuation order is A private phone hosting → B primary-source VO2max table/bar
→ C design review and small improvements → D documentation alongside every change. This
release series implements A's publishing helper and B's exact reference bar. C's review and
small improvements are recorded in `docs/UI_REVIEW.md` (v0.14.1). A's live account/device
activation remains pending. Browser checks use synthetic data. See `docs/CONTINUATION_REVIEW.md` for evidence and
known documentation drift. `ROADMAP.md` remains the only plan.

**Deliberately not building** (`ROADMAP.md`, "Explicitly not building" and the dropped-items table):
- **Never building:**
  - Skin temperature and ECG: the FR955 has no sensor.
  - ACWR as an injury-risk score.
  - Strava as a source.
  - Our own Body Battery or stress score.
  - A Grafana view.
  - Oura readiness bands.
  - A FIT workout encoder.
- **Not building now:**
  - Banister performance-model fit: needs more data.
  - A separate Active Zone Minutes view: Garmin's intensity minutes already cover it.
  - Our own fitness age: Garmin's is used.

## 11. How to work on it
- **Setup:** `pip install -e .[dev]` (Python ≥ 3.12). Then `pytest` and `ruff check .`. CI runs on 3.12 and 3.13.
- **Commands:** `garmin-mcp` (server), `garmin-mcp-sync [--force]`, `garmin-mcp-import <zip>`, `garmin-mcp-verify`, `garmin-mcp-dashboard`.
- **Rules:** `AGENTS.md`. Changelog entry every change, sense-check against real data, never commit credentials, plain language on screen.
- **Data:** not in the repo. It lives in the user's data folder on the Mac (`config.data_dir()`).

## Review handoff: v0.14.1

PRs #8–11 landed through passing Python 3.12/3.13 CI. The dashboard follow-up fixes stale
personal ranges, empty data, chart accessibility and atomic/private file output. Full-sync
provenance also includes derived-load success. See `docs/UI_REVIEW.md` and `docs/OPERATIONS.md`.
Do not treat historical recovery-study figures as rerun results. The owner's real database,
Mac/iCloud behavior, watch writes, untested maximum HR and live hosting still require their
respective checks. MCP results go to the user's chosen AI provider; hosted HTML goes to Cloudflare.

The v0.14.2 Running drill-down separates our recorded moving and elapsed times from Garmin's
FIT session timer and elapsed times. See METRICS for gaps, coverage and split interpolation.
Tests exercise older stored FIT rows and known timing cases. Comparison with the owner's
actual Garmin history still belongs to the Mac rollout in ROADMAP.

In v0.15.0 the health snapshot, trends and relationships share the same valid nightly HRV
source merge as recovery and monthly history. Underlying readiness weights and association
thresholds are unchanged. Training shows a seven-day overview with the sleep-night count.
The screenshot and input checks are in `docs/UI_REVIEW.md`.

The v0.15.1 environmental research is linked in ROADMAP. Source coverage and sleep exposure
limits are open. No weather or air-quality collection change is enabled.

### Review handoff for v0.17.0

Follow the same run through `coaching.run_analysis`, `running.running_breakdown` and its
dashboard comparison page. Check that future activities, markedly different sessions and
missing ascent/heart rate are excluded. Check raw Garmin readiness's recorded time before
the run and that AQI stops at the exclusive end of its imported interval. The synthetic
regressions are in `tests/test_run_evidence.py`. For the live follow-up see
[MAC_SETUP](MAC_SETUP.md#archive-timing-comparison) and [ROADMAP](ROADMAP.md).

### Handoff for Claude after v0.19.0

Read the [product review](docs/PRODUCT_REVIEW_2026-11.md), then the release and the
[roadmap](ROADMAP.md). Today leads with an action, actual readings, an easy week and up
to three findings. Sleep shortfall, Garmin Detraining with recorded kilometres,
personal recovery changes, and a qualifying cadence cue have paths to their evidence.
Recovery history moved to a collapsed detail. Run comparisons use separate tracks on
one elapsed clock. Git can now be current while data are unchanged without leaving
HTML on an older release; the footer reports each timestamp separately.

Start locally by opening the scheduled dashboard and comparing its build/version to
the iCloud copy. Time the owner’s five-second test with their actual iPhone and archive.
Next, build the cadence experiment follow-up with a user-entered comfort note and a
comparable later run. Test any sleep or training takeaway on later records before
strengthening its wording. Keep uploading workouts a separate approval. Then reduce
the remaining file weight and measure Files/Safari load time. The 600 KB review target
was not reached in this pass. Keep all active work in ROADMAP; audit logs record past
decisions and do not define a second plan.

### Environmental follow-up in v0.20.0

Run detail can now compare measured temperature, humidity or AQI and moving heart
rate on the same set of earlier similar runs. Sleep compares actual measured bedroom
conditions with duration and optional morning self-reports. Use the local import
commands in README, methods in METRICS, and the roadmap for remaining retrieval,
location and replication work. Verify coverage on the Mac before interpreting the
comparisons. The owner offered signed-in Garmin Connect for a read-only review;
the current cloud tools could not attach to that tab. The source ledger records
the public screens that were inspected and their limits.
