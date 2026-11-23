# Fitbit (Google Health), Whoop, Bevel: features to borrow + re-verification of [S] claims

Date: 2026-11-23. Fetched with curl via session proxy. Tags: **[R]** = read on the cited page this session;
**[S]** = search-snippet only; **[M]** = from memory / earlier knowledge, not confirmed this session.
whoop.com and support.whoop.com were blocked (Cloudflare / JS shell), so Whoop rows are [S] unless noted.
New relative to `insights_and_dashboards.md`, `analytics_platforms.md`, `connected_connectors_inventory.md`.

## 0. Context change (2026)
| Fact | Tag | Source |
|---|---|---|
| Fitbit app is now the **Google Health app**; Fitbit Premium → **Google Health Premium** (~$9.99/mo); coach branded **Google Health Coach** | [R]/[S] | https://support.google.com/fitbit/answer/14236710 (page title "Google Health Help Center"); https://store.google.com/magazine/personal_health_coach [S] |
| Coach (Gemini) = multi-agent: conversation agent + **data-science agent** (fetches data, writes code) + domain-expert agent (fitness plans); contextualises vs **personal baselines and population stats**; evaluated with SHARP (safety, helpfulness, accuracy, relevance, personalisation) | [R] | https://research.google/blog/how-we-are-building-the-personal-health-coach/ |
| Mar 2026: +15% sleep-staging accuracy; new transparent Sleep Score; medical records link; CGM via Health Connect ("how did that workout / pizza affect glucose") | [R] | https://blog.google/products-and-platforms/devices/fitbit/fitbit-personal-health-coach-updates-2026/ |

## 1. Google Fitbit / Pixel Watch
| Feature | How calculated (published?) | Presentation | Tag / source | FR955 replicate? |
|---|---|---|---|---|
| **Readiness score** (0–100, Low→High) | 3 inputs only: **Sleep (past week pattern)**, **HRV**, **RHR (sustained multi-day rise)**, each vs personal baseline. Needs 7 nights for baseline; ~1 month for accurate one. No weights published. (Older Fitbit version also used activity — no longer listed) | number + label; morning on watch | [R] https://support.google.com/fitbit/answer/14236710 | **Yes**: overnight HRV, RHR, 7-d sleep from Garmin |
| **Sleep Score (2026 redesign)** | 6 components: **sleep duration** (more = better), **time to sound sleep** (until deep/REM/steady light with calm HR), **sound sleep** (total steady sleep), **restlessness** (brief stirs), **full awakenings** (>5 min; <2 good), **interruptions** (total wake >5 min incl. between sessions). Scored vs targets by **age, gender, time in bed**. Bands: 90–100 Excellent, 80–89 Good, 60–79 Fair, <60 Poor; most users 72–83 | score + "Sleep duration"/"Sleep quality" chips drill into components | [R] https://support.google.com/fitbit/answer/14236513 | **Partial/yes**: duration, awake periods, stage timestamps from Garmin sleep; "sound sleep" needs HR stability (have sleep HR series); restlessness ≈ Garmin restless moments |
| Sleep Profile (monthly "animal" chronotype, 10 metrics) | not published | monthly card with animal archetype | [M] (could not fetch; not found in search) | Yes: monthly cluster of bedtime, consistency, duration, deep%, wake count |
| Cardio Fitness Score (VO2max est., range bands by age/sex) | resting-HR-based est. unless GPS runs; not published | range bar with Poor→Excellent, age/sex norms | [M] (help page 14236706 now 404) | Have Garmin VO2max; add norm range bar |
| Active Zone Minutes (1× in fat-burn, 2× cardio/peak; HRR-based zones; goal 150/wk) | published rule | weekly ring, double credit visual | [M] | **Yes**: from HR zones per minute |
| HRV, breathing rate, SpO2, skin-temp variation → **Health Metrics** dashboard | each shown vs **personal range** band (outside-range flag) | one row per metric, dot inside/outside shaded band, 7/30/90 d | [M]; metrics list [S] store.google.com | **Yes** (HRV, resp, SpO2, RHR); skin temp: FR955 has no skin temp → no |
| Stress Management Score (1–100: responsiveness EDA/HRV, exertion balance, sleep patterns) | partial description only | score + 3 components | [M] | Partial: Garmin stress + load balance + sleep; no EDA |
| Google Health Coach | Gemini, data-science agent runs analyses on user time series; adaptive weekly plans; asks follow-ups | chat + proactive cards | [R] research.google | Have MCP + Claude; adopt "verify data availability → pick metrics → contrast days → baseline vs population" recipe |

## 2. Whoop (4.0 / 5.0 / MG)
| Feature | Calculation (published?) | Presentation | Tag / source | FR955 replicate? |
|---|---|---|---|---|
| **Recovery** 0–100% | inputs HRV (largest weight), RHR, sleep performance, respiratory rate (added later); SpO2/skin temp listed on some pages (conflicting). HRV from last SWS episode of night. Weights unpublished | green 67–100 / yellow 34–66 / red 0–33 dial [M bands] | [S] https://whoop.com/thelocker/how-does-whoop-recovery-work-101 , https://www.whoop.com/ca/en/thelocker/adding-respiratory-rate-to-recovery , https://www.community.whoop.com/t/what-is-the-recovery-score-and-how-is-it-calculated/107 | **Yes** (HRV, RHR, sleep, resp from Garmin) |
| **Strain** 0–21 log scale | cardiovascular (HR-zone time) + muscular load; logarithmic, cannot exceed 21; combination undocumented | dial; daily target strain from recovery | [S] https://the5krunner.com/2022/05/24/whoop-strain-everything/ , https://the5krunner.com/2025/09/06/whoop-strain-20-2-heres-how-i-did-it-and-so-what/ | **Yes**: log-transform of daily TRIMP; target band from readiness |
| Sleep Performance / Need / Debt | need = baseline + strain add-on + debt + nap credit [M] | % of need bar; "hours to bed" planner | [M] | **Yes**: sleep-need model from our data |
| Stress Monitor 0–3 | HRV + HR vs personal baseline | live 0–3 gauge | [S] https://www.whoop.com/de/en/the-data/ ; reviewer doubts accuracy [S] https://buttondown.com/bodysciencereview/archive/whoop-40-review-2026-is-the-subscription-worth-it/ | Have Garmin stress 0–100 |
| **Healthspan / Whoop Age / Pace of Aging** | 9 inputs: sleep duration, sleep consistency, steps, HR-zone time, strength activity, VO2max, RHR, lean body mass (+1); vs expert reference values; Age = 6 mo data; Pace (−1× to 3×) = last 30 d, weekly update | age vs chronological; per-input "+/− years" bars | [S] https://www.whoop.com/thelocker/Healthspan-Data-Meets-Longevity , https://www.whoop.com/us/en/thelocker/podcast-323-the-9-metrics-that-make-up-your-healthspan-with-emily-capodilupo/ | **Partial**: all but lean mass (needs scale); "pace of aging" 30 d vs 6 mo is easy |
| Journal + Monthly/Weekly Performance Assessment | behaviour yes/no → effect on recovery (pts), significance tiers | ranked bar list | already in insights_and_dashboards.md [S] | Phase 8.5 |
| Strength Trainer + passive MSK | sets×reps×weight muscular load; 2026 auto MSK from wrist motion (unvalidated) | muscle map | [S] https://www.wareable.com/fitness-trackers/whoop-launches-strength-trainer , https://the5krunner.com/2026/02/28/new-whoop-strength-trainer-update/ | Partial: FR955 strength sets/reps (weights if entered) → volume per muscle group |
| Whoop Coach (GPT-based) | chat on own data | chat | [S] thin coverage | Have |

## 3. Bevel (iOS, Apple Health / Garmin via Health)
| Feature | Calculation (as published) | Presentation | Tag / source | FR955 replicate? |
|---|---|---|---|---|
| **Recovery** 1–100% | once each morning; inputs **Sleep Score, HRV (RMSSD, sleep-only, standardised), RHR, wrist temp, resp rate, SpO2**; HRV for Recovery ≠ daytime HRV for Stress | % ring | [R] https://help.bevel.health/en/articles/11258177 , https://help.bevel.health/en/articles/11251073 | Yes (minus temp) |
| **Sleep Score** % | Time Asleep, REM, Deep, **Heart Rate Dip** (% wake avg HR → sleep HR), Sleep Efficiency, Continuity; plus Sleep Needed / Debt / **Sleep Bank** | % + contributors | [R] 11251073 | **Yes**; HR dip is new & cheap |
| **Strain** 0–100% (can exceed) | active (workouts) + **passive** (background HR) strain; time in personalised HR zones × duration; **logarithmic**, per-activity values not additive (diminishing return) | ring + per-activity chips | [R] https://help.bevel.health/en/articles/11257857 | Yes |
| **Target Strain** | recent recoveries vs strain baseline → higher/lower target | target arc on strain ring | [R] 11257857 | Yes |
| Cardio Load | **TRIMP**-based; separate "Cardio Status" (incl. overtraining label) | chart | [R] 11257857 | Have (PMC) |
| **Stress** 1–100 | HR vs HRV imbalance + movement filter + time of day; physiological only | day timeline | [R] https://help.bevel.health/en/articles/11258369 | Have Garmin stress |
| **Energy Bank** 1–100 | charges in sleep/mindfulness, drains with stress/activity; starts from recovery; **non-linear** (slows near 1 and 100); **carries over days**; ~30 d calibration | battery line through day | [R] 11258369 | ≈ Garmin Body Battery (have) |
| Activity Status (Active/Sick/Injured/On Break) | context label suppresses recommendations | chip | [R] 11251073 | **Yes, add** (ties to tags) |
| Health Monitor | RR, RHR, HRV, SpO2, temp, sleep vs baseline | one panel | [R] 11251073 | Yes |
| Biological Age (+confidence level), Journal, nutrition score, glucose, Bevel Intelligence (proactive check-ins, daily summaries, plans) | not published | cards/chat | [R] https://www.bevel.health/ ; 11251073 | Partial |

## 4. Re-verification of insights_and_dashboards.md [S]/[unverified] claims
| Claim | Result | Source [R] |
|---|---|---|
| intervals.icu Fitness/Fatigue/Form, configurable time constants, multiple load models (power/HR/pace/RPE), annotations | **Confirmed** | https://www.intervals.icu/features/fitness-chart/ |
| intervals.icu Form as % of Fitness | **Confirmed**: Form% = (Fitness−Fatigue)×100/Fitness; −30% is the green/red zone edge in forum example | https://forum.intervals.icu/t/fitness-page-a-guide-to-getting-started/17702 |
| intervals.icu uses today's values vs others yesterday | Not stated on pages read; TrainingPeaks side confirmed (below) | — |
| TrainingPeaks PMC [unverified] | **Confirmed**: ATL 7-d EWMA, CTL 42-d EWMA, **Form = yesterday's CTL − yesterday's ATL**; rule of thumb Form slightly negative to +25 for racing; too high = lost fitness | https://www.trainingpeaks.com/learn/articles/what-is-the-performance-management-chart/ |
| Oura balance contributors "14 d vs 3 mo" | **Correction**: 14-d weighted avg (past **2–5 d weighted more**) vs **2-month** long-term avg. Bands 85–100 Optimal, 70–84 Good, 60–69 Fair, **0–59 "Pay Attention"**; crown icon at ≥85; overnight inputs: lowest RHR + its timing, temp, sleep, previous-day activity | https://support.ouraring.com/hc/en-us/articles/360025589793-Readiness-Score |
| Runalyze Marathon shape 6 mo, ⅔ weekly km / ⅓ long runs | **Confirmed with correction**: weekly km over **6 months**, long runs over **last 10 weeks**; long-run scaling starts at **13 km**; required shape 5K 7%, 10K 17%, 15K 28%, **HM 43%** (not 42.5%), M 100%, 50K 123%; target table VO2max 50 → ~85 km/wk, ~30 km long run | https://runalyze.com/help/article/88 , https://runalyze.com/glossary/marathon-shape |
| HRV4Training SWC/7-d rule | Not re-verified (hrv4training.com blog fetch returned shell/empty) | — |
| Whoop MPA items | Still [S] (whoop.com blocked) | — |

## 5. Prioritised features for Phase 8 / Phase 9
| # | Feature | Phase | Inputs (FR955) | Why / presentation idea |
|---|---|---|---|---|
| 1 | **Personal-range bands** for HRV, RHR, resp, SpO2, sleep HR (Fitbit Health Metrics style) | 9.3 | Garmin daily | one row per metric; dot inside/outside shaded 30-d band; "x of 5 outside range" headline |
| 2 | Readiness gauge with **contributor chips** (Sleep 7-d, HRV, RHR-trend) + Oura-style 14-d-weighted vs 60-d balance | 8/9.1 | HRV, RHR, sleep | Oura bands 85/70/60 + crown ≥85 |
| 3 | **Sleep score drill-down** (Fitbit 6 components + Bevel HR dip) | 9.3 | sleep stages, sleep HR | component bars with target ticks |
| 4 | **Heart Rate Dip** metric | 8 | day vs sleep HR | cheap, new; trend line |
| 5 | **Daily strain (log TRIMP) + Target Strain band** from readiness | 8/9.1 | TRIMP, readiness | ring with target arc; active vs passive split |
| 6 | **Sleep need / debt / bank** with "go to bed by" | 8 | sleep, load | bar of % of need; debt running total |
| 7 | **Activity status** (Active/Sick/Injured/Break/Travel) suppressing advice + excluded from baselines | 8.5 | user tag | chip on daily brief |
| 8 | Behaviour impact list (Whoop MPA) | 8.5 | tags + readiness | ranked ± points bars, significance tiers |
| 9 | **Form % of fitness** with zone colours | 9.2 | PMC | intervals.icu zones (−30% edge) |
| 10 | Runalyze marathon-shape corrections (10-wk long runs, 13 km, HM 43%) | 8.8 | runs | gauge per race distance |
| 11 | **Pace of aging** (30-d vs 6-mo healthspan inputs) | 8.14 | VO2max, RHR, sleep consistency, steps, zone time, strength | "+/− years" contributor bars; wellness-only label |
| 12 | Active Zone Minutes weekly (1×/2× credit) | 9.5 | HR zones | weekly ring vs 150 |
| 13 | VO2max norm range bar by age/sex | 9.4 | Garmin VO2max | Poor→Superior band |
| 14 | Monthly sleep profile card (chronotype cluster) | 8.1 | bed/wake times | monthly card, no animals needed |
| 15 | Strength volume per muscle group | 9.5 | FR955 strength sets | body map heat |
| 16 | Coach recipe: availability check → metric choice → contrast days → baseline + population → answer | 8.13 | MCP | embed in daily brief generator |
| 17 | Score-band labels matching vendors (Optimal/Good/Fair/Pay attention) not raw numbers only | 9 | all | consistent colour system |
| 18 | Calibration state ("needs 7 nights / 30 d") shown on every score | 9 | counts | grey "calibrating" badge |
