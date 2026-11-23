# Insights & dashboards research (beyond v0.5.0)

Date: 2026-11-23. Builds on ROADMAP.md (Phases 3–4 done: HRV SWC band, z-score readiness, illness flag, TRIMP/rTSS, CTL/ATL/TSB, monotony, pace curve, CS, eVO2max, race predictions) and running_and_sport_metrics.md (form metrics). Not repeated here.

**Fetch status:** WebFetch of vendor sites failed (DNS blocked in this session: intervals.icu forum, trainingpeaks.com, hrv4training.com, support.ouraring.com, runalyze.com, whoop.com). WebSearch worked; claims below come from search-result snippets of the cited pages. **[S]** = seen in search snippet of cited URL; **[unverified]** = from memory, not confirmed this session. To fetch directly, those hosts must be allowed in the session network settings.

---

## 1. Insight levels

Conventions: n = days (or runs) with both inputs present. "Present" column = how to show it. All Level 2/3 output must carry: n, effect size with CI, and "association, not cause".

### Level 1: descriptive (what happened)

| Insight | Inputs | Method | Min data | Pitfalls | Present |
|---|---|---|---|---|---|
| Weekly/monthly totals by sport (dist, time, load, elev) | activities | sums, ISO weeks | 1 wk | timezone of "week" (R7) | weekly card + 12-wk bars |
| PRs & best efforts (1k/5k/10k/HM, longest run, best CS) | FIT distance stream | rolling best, dated | any | GPS glitches → cap speed, require HR sanity | PR list with date, "new" badge |
| Trend of any metric (RHR, HRV, VO2max, sleep, weight) | daily tables | 7/28-d rolling mean + Theil–Sen slope | 28 d | seasonal/device firmware steps | sparkline + slope/month |
| Streaks & consistency | activities, sleep | run-length, % days | 2 wk | — | calendar heatmap |
| Sleep consistency | sleep start/end | SD of bedtime/wake, social jetlag (weekday vs weekend midpoint) | 14 nights | naps, travel | dot strip of bed/wake times |
| Time in zones / distribution over time | per-activity zone secs (4.4) | stacked weekly % | 4 wk | LTHR changes; recompute history from dated thresholds | stacked bars |
| Swim: pace/100m, SWOLF trend per pool length | lengths | median per session | 5 sessions | drills/kick sets pollute; filter by stroke | line per stroke |
| Strength: volume (sets×reps×kg), frequency per muscle group | strength sets | sums | 4 wk | watch rep counting errors; allow edits | weekly bars per group |
| Garmin metric history (training status, readiness, race predictor, VO2max) | Garmin tables | as-is | any | label as Garmin | grey series beside ours |

### Level 2: diagnostic / relational (why)

| Insight | Inputs | Method | Min data | Pitfalls | Present |
|---|---|---|---|---|---|
| Sleep → next-day HRV/RHR | sleep dur/score, ln RMSSD, RHR | within-person: de-mean both by 28-d rolling mean, then Spearman + OLS slope; lag 0/1 | 60 paired nights | autocorrelation inflates significance → block bootstrap CI; reverse causation (illness) | scatter of deviations + "each +1 h sleep ≈ +x ms" |
| Late/hard training → sleep | activity end time, load, sleep score/deep, sleep HR | group nights: no session / session ending <3 h before bed / earlier; Mann–Whitney or mixed model | 20 nights per group | confound: hard days also long days; stress | grouped box plot |
| Load → readiness/HRV lag | daily TRIMP, ln RMSSD | cross-correlation at lags 0–3 d on prewhitened series (ARIMA residuals) | 90 d | trends make everything correlate; prewhiten | lag bar chart "biggest effect at day +1" |
| Heat → HR drift | FIT temp (wrist, biased high), weather API temp/dew point, decoupling (5.1) | regression decoupling ~ dew point + duration + pace; or HR at matched pace vs temperature | 20 steady runs spanning ≥10 °C | wrist temp reads body heat; prefer weather; hydration unmeasured | scatter + fitted line, bpm per +5 °C |
| Cadence/stride vs pace (form strategy) | FIT records | binned by pace (10 s/km bins), LOESS; compare to own past | 10 runs | speed confounds every form metric; always condition on pace | small multiples per form metric vs pace |
| Running economy proxy (EF, power/speed) | speed, HR, power | EF = speed/HR on steady parts; trend; matched pace HR | 8 steady runs/month | heat, hills, fatigue; use GAP | trend with "matched pace 5:30/km HR" |
| Stress/alcohol proxies | Garmin all-day stress, sleep HR elevated, HRV drop, user tags (6.1) | flag nights with sleep HR z>1.5 & HRV z<−1 without load; with tags: within-person difference (tag vs no tag), permutation test | ≥8 tagged nights | no real tags → only "unexplained bad night"; label as proxy, never "alcohol" | tag impact list (Whoop-style) with CI |
| Day-of-week patterns | any daily metric | mean by weekday ± CI; Kruskal–Wallis | 8 wk | multiple testing across metrics → FDR (Benjamini–Hochberg) | 7-bar chart / heatmap metric×weekday |
| Why is readiness low today | our z components (3.3), Garmin factors | decomposition (already have contributions) + top recent cause (load spike, short sleep) | have | over-explaining noise | contributor bars (Oura-style) |
| Workout vs similar past | session features | kNN on (type, dist, pace, temp) | 5 similar | different routes/terrain | "vs your 5 similar runs" row |

General L2 rules: within-person centering (subtract rolling baseline) before correlating; report Spearman ρ with block-bootstrap 95% CI; apply BH-FDR when scanning many pairs; minimum n ≥ 30 paired days to show anything, ≥ 60 to call it "likely"; never show p-values alone.

### Level 3: predictive / prescriptive (what next)

| Insight | Inputs | Method | Min data | Pitfalls | Present |
|---|---|---|---|---|---|
| Dose–response (load → performance) | daily TRIMP, performance markers (eVO2max per run, CS, EF at matched pace) | Banister impulse-response: p(t)=p0+k1·Σw(s)e^−(t−s)/τ1 − k2·Σw(s)e^−(t−s)/τ2; fit by nonlinear least squares; bound τ1 20–60, τ2 3–20 | ≥ 120 d with ≥ 15 performance points | overfits; parameters unstable; performance markers noisy (Liversedge: needs a fair amount of history [S]) | predicted vs actual curve; show param CI; "experimental" badge |
| Personal recovery time | load of session, next-days ln RMSSD/RHR z | per-session: days until HRV z back within band; regress on TRIMP (Poisson/log-linear) | 30 hard sessions | concurrent sessions overlap; censoring | "after ~X TRIMP you take ~Y days"; compare to Garmin recovery time |
| Load-spike flags (responsible injury-style) | CTL/ATL, weekly km, long-run share | ramp rate, week-over-week km change >30%, single long run >~1.5× longest of last 30 d [unverified heuristic] | 6 wk | ACWR is disputed science; do NOT call it injury risk; say "load jumped" | amber chip with numbers, no risk %; link to explanation |
| Plateau / changepoint detection | eVO2max, EF, CS, RHR | PELT or Bayesian online changepoint on weekly medians; or slope ≈0 with CI over 8 wk | 16 wk | noise vs real; season changes | shaded segments on trend chart |
| Race readiness | race date/distance (6.1), predictions (4.7), CTL, long runs, marathon-shape-style volume | composite: predicted time vs goal, volume score (Runalyze: weekly km ⅔ + long runs ⅓ over 6 mo; 10K needs 17%, HM 42.5%, M 100% [S]), TSB on race day | 8 wk | composite weights arbitrary; show parts | checklist + gauge per part |
| Taper modeling | planned load, CTL/ATL | simulate CTL/ATL/TSB forward for taper plans (e.g. −40–60% volume over 2 wk) [unverified ranges]; target TSB positive on race day | have PMC | ignores intensity retention | projected PMC with plan overlay |
| HRV-guided training rule | ln RMSSD 7-d mean, SWC band | Kiviniemi-style: hard session if HRV within SWC, else easy (HRV4Training/Altini; SWC ≈ 0.5 SD; 7-d rolling; 4–5 readings/wk enough) [S]; evidence: small benefit, fewer non-responders [S] | have (3.1) | Garmin overnight HRV ≠ morning standing RMSSD protocol; flag that | traffic light + one-line rule on daily brief |
| Personalised rule discovery | all daily features | mixed model / gradient boosting with SHAP on next-day readiness; validate by time-split | 180 d | leakage, overfitting, n=1 | "top 3 drivers for you" with stability score |
| Performance forecast | CTL trend, eVO2max trend | linear projection to race date with prediction interval | 12 wk | extrapolation | fan chart |

---

## 2. What others do (features to replicate)

| Product | Feature & how it is calculated | Source | Replicable with our data? |
|---|---|---|---|
| intervals.icu | Fitness/Fatigue/Form = EWMA of load, 42 d / 7 d; Form = **today's** Fitness − Fatigue (others use yesterday); can show Form as % of Fitness | [S] https://www.intervals.icu/features/fitness-chart/ , https://forum.intervals.icu/t/fitness-page-a-guide-to-getting-started/17702/75.md | Yes (have PMC); add Form % and zone bands |
| intervals.icu | Wellness import (HRV rMSSD/SDNN, RHR, sleep, readiness) plotted with custom charts and custom EWMA formulas | [S] https://www.intervals.icu/features/wellness/ , https://www.intervals.icu/features/custom-charts/ | Yes: correlations explorer |
| intervals.icu | eFTP from single maximal efforts (auto zones); ~90-d window reported by a user | [S] https://www.intervals.icu/features/power-curve/ ; window [unverified] | Partially: running power eCP from FIT power |
| intervals.icu | Submaximal fatigue testing: detects repeated standard efforts and charts vs sleep/stress | [S] https://www.intervals.icu/features/submaximal-fatigue-testing/ | Yes: HR at matched pace on easy runs |
| TrainingPeaks | PMC (CTL/ATL/TSB), ATP annual plan | fetch failed; [unverified] details | Already have PMC; ATP → forward projection |
| HRV4Training / Altini | 7-d rolling ln RMSSD vs normal ±SWC (~0.5 SD); hard if within band; 4–5 readings/wk | [S] https://marcoaltini.substack.com/p/a-brief-history-of-heart-rate-variability , https://pubmed.ncbi.nlm.nih.gov/26909534/ , https://www.ais.gov.au/__data/assets/pdf_file/0013/1130260/HRV-BPG_FINAL.pdf | Yes (3.1 done); add rule + tag correlations |
| Oura | Readiness 0–100 from contributors vs personal averages: RHR (last night lowest vs long-term; penalty if 3–5 bpm higher), HRV balance (14 d vs 3 mo, recent weighted), body temp deviation, recovery index (sleep after HR nadir, optimal ≥ 6 h), plus sleep, activity balance etc.; bands 85+/70–84/60–69/<60 | [S] https://support.ouraring.com/hc/en-us/articles/360057791533 , https://ouraring.com/blog/readiness-score/ | Mostly: HRV balance 14d/90d, RHR delta, recovery-index proxy from Garmin sleep HR curve; skin temp if FR955 lacks → skip |
| Whoop | Monthly Performance Assessment: isolates each journal behaviour's effect on recovery (e.g. alcohol −9 pts across members), categories significant→negligible; needs enough yes/no answers; strain/recovery/sleep heatmaps for a year | [S] https://www.whoop.com/thelocker/monthly-performance-assessment , https://www.whoop.com/ca/en/thelocker/a-new-way-to-see-insights-on-which-behaviors-affect-your-recovery/ ; strain/recovery formula not found | Yes if we add tags (6.1); heatmaps yes |
| Runalyze | Effective VO2max per run from HR–pace relation + individual correction factor from best race; Marathon shape (6 mo, weekly km ⅔, long runs ⅓; required 17/42.5/100% for 10K/HM/M); "not scientifically based" | [S] https://runalyze.com/help/article/88 , https://runalyze.com/glossary/marathon-shape , https://blog.runalyze.com/tutorial/runalyze-understanding-the-calculations/ | Yes: correction factor + marathon shape on our predictions |
| Golden Cheetah | Banister model (learns individual impulse response, predicts performance; needs lots of history) + PMC | [S] https://markliversedge.blogspot.com/2019/01/implementing-banister-impulse-response.html , https://goldencheetah.org/ | Yes (L3 dose–response) |
| WKO5 | Power-duration model → mFTP without testing; values differ from other tools | [S] https://ctyeh.com/articles/958?lang=en | Partial: running power-duration from FIT power |
| Stryd | CP drives zones, targets, race predictions; adaptive training checks CP accuracy against RPE & fatigue; schedules CP-estimate run; return-from-break logic | [S] https://help.stryd.com/en/articles/12580285-stryd-adaptive-training-how-to , https://blog.stryd.com/2026/02/17/new-adaptive-training-update-race-support-smarter-return-to-training-greater-cp-accuracy/ | Partly: wrist power CP; "CP stale" prompt; return-to-training rule |
| Athlytic | Recovery from overnight HRV + RHR vs baseline; stress score | [S] https://apps.apple.com/CA/app/id1543571755 | Already equivalent (3.3) |
| Elevate | Fitness trend (PMC from HR/power for Strava) | [S] https://www.github.com/thomaschampagne/elevate/issues/682 (details [unverified]) | Already have |
| Runna / Athletica / AI Endurance | Adaptive plans from recent performance; Runna owned by Strava since Apr 2025 | [S] https://www.sensai.fit/blog/ai-coaching-endurance-athletes-runners-cyclists ; rules [unverified] | Later (Phase 7): plan adjust by readiness + compliance |
| Garmin Connect+ Active Intelligence | Paid AI insights reacting to recent data/trends; Performance Dashboard; reviewers: sometimes repetitive | [S] https://www.garmin.com/en-US/blog/fitness/what-is-the-garmin-connect-performance-dashboard/ , https://www.androidcentral.com/wearables/garmin/garmin-connect-plus-in-depth-hands-on-much-more-than-an-ai-unfortunately | Have daily brief/weekly review; avoid repetition (dedupe messages) |
| Strava Athlete Intelligence | Per-workout AI summary vs past trends | [S] https://www.androidcentral.com/wearables/new-garmin-connect-plus-subscription-adds-active-intelligence-beta-enhanced-smarts (thin) | Have (5.3 recap) |

Replicable feature shortlist: Form % + zones; HRV balance 14d/90d; recovery index proxy; tag-impact analysis; year heatmaps; submaximal fitness test (HR at matched easy pace); marathon shape; race correction factor; Banister fit; CP-stale prompt; dedupe of AI-style messages.

---

## 3. Dashboard design

### Views

| View | Chart | Notes |
|---|---|---|
| Daily brief card | text + 3 KPI tiles (readiness, HRV state, sleep) + suggestion | first screen on mobile; one sentence why |
| Readiness gauge + contributors | semicircle or bullet gauge; horizontal diverging bars of z-components | Garmin readiness as separate grey tile, not merged |
| PMC | CTL line, ATL line, TSB bars (zone bands), daily load bars below; event markers | 90 d default, zoom to 1 y |
| HRV band | ln RMSSD daily dots, 7-d mean line, shaded SWC normal band | same pattern for RHR (inverted colour meaning) |
| Sleep consistency | per-night horizontal bar bed→wake (Actogram), duration line | weekday/weekend shading |
| Pace curve | log-x duration vs pace; current 90 d vs all-time vs last year; CS line | |
| Running form at matched pace | small multiples: cadence/stride/GCT/VO vs month, each at fixed pace band (e.g. 5:15–5:45/km) | removes speed confound |
| Weekly summary | totals table + intensity stack + vs 4-wk avg arrows | Sunday/Monday |
| Calendar heatmap | year grid colored by load / readiness / sleep (Whoop-style) | click-through to day |
| Correlations explorer | pick X,Y,lag → scatter of de-meaned values, ρ + CI, n | warning banner on n<30 |
| Activity page | map optional, HR/pace/power stream, laps, decoupling, vs similar runs | |

### Stack options (local, SQLite)

| Option | Pros | Cons | Mobile |
|---|---|---|---|
| **Static HTML generated by Python + Plotly.js or Chart.js** | no server, open file or serve via any static host/Tailscale; reproducible; versioned; cheap | regenerate on sync; interactivity limited to client-side (fine with JSON embedded) | good with responsive CSS |
| Streamlit | fastest to build in Python, widgets for explorer [S] https://docs.streamlit.io/get-started/why-streamlit.md | needs running server; every chart/login is code [S] jetadmin roundup; reruns whole script | OK, not great |
| Datasette (+ datasette-vega/dashboards plugins) | instant browse/SQL over SQLite; facets [S] https://www.jetadmin.io/blog/best-sqlite-dashboard-tools/ | charts via plugins; read-focused | weak |
| Grafana + SQLite plugin | great time-series panels, alerts | community plugin, engineer-oriented [S]; heavy for one user; awkward for scatter/curves | OK app |

**Recommendation:** static HTML site generated by a Python command (`garmin-dashboard build`) after each sync, Plotly.js (or Chart.js for smaller payload) with data as embedded JSON; mobile-first single column; optional Datasette as an ad-hoc SQL companion. Streamlit only for the correlations explorer if client-side becomes too heavy. Reasons: no server to maintain, works offline, fits current Python/SQLite stack, and can also be published as a private artifact.

### Keeping Garmin vs ours visible
- Colour code: Garmin values always grey/neutral with a "G" badge; ours in accent colour with "ours" badge.
- Side-by-side tiles, never averaged together; show delta (ours − Garmin) and flag big disagreements.
- Every chart footer: source + formula link (glossary 5.6) + data window + n.
- Provenance field (6.3) drives the badge automatically.

---

## 4. Prioritised backlog (later phases)

| # | Level | Insight | Data needed | Effort | Value |
|---|---|---|---|---|---|
| 1 | 1 | Static HTML dashboard skeleton: daily brief, PMC, HRV band | existing tables | M | High |
| 2 | 1 | Calendar heatmaps (load, readiness, sleep), year view | daily tables | S | High |
| 3 | 1 | PR/best-effort list with "new" detection | pace curve | S | Med |
| 4 | 1 | Sleep consistency actogram + social jetlag | sleep | S | Med |
| 5 | 2 | Running form at matched pace (small multiples) | FIT records | M | High |
| 6 | 2 | Submaximal fitness test: HR at standard easy pace over time | FIT, temp | M | High |
| 7 | 2 | Heat-adjusted HR drift (weather dew point) | FIT, weather API | M | Med |
| 8 | 2 | Sleep → next-day HRV/RHR (de-meaned, bootstrap CI) | sleep, HRV | S | High |
| 9 | 2 | Late/hard session → sleep quality | activities, sleep | S | Med |
| 10 | 2 | Load → HRV lag profile (prewhitened CCF) | TRIMP, HRV | M | Med |
| 11 | 2 | Day-of-week patterns with FDR | daily | S | Low |
| 12 | 2 | Tags (alcohol, stress, travel, illness) + Whoop-style impact | user tags via 6.1 | M | High |
| 13 | 2 | Correlations explorer view | all daily | M | Med |
| 14 | 2 | Oura-style HRV balance (14 d vs 90 d) + recovery-index proxy | HRV, sleep HR | S | Med |
| 15 | 3 | HRV-guided session rule in daily brief | 3.1 band | S | High |
| 16 | 3 | Load-jump flags (ramp, km +30%, long-run spike), no "injury risk" wording | activities | S | High |
| 17 | 3 | Personal recovery-time model vs Garmin's | TRIMP, HRV/RHR | M | Med |
| 18 | 3 | Plateau/changepoint on eVO2max, EF, CS | trends | M | Med |
| 19 | 3 | Marathon-shape volume factor + race-time correction from best race | activities, races | S | High |
| 20 | 3 | Race readiness checklist + forward PMC/taper simulator | goal race (6.1), PMC | M | High |
| 21 | 3 | Banister dose–response fit (experimental) | ≥120 d load + perf | L | Med |
| 22 | 3 | Running CP from wrist power + "CP stale" prompt | FIT power | M | Med |
| 23 | 3 | Personal driver discovery (time-split validated model) | ≥180 d all | L | Low/Med |
| 24 | — | Message dedupe/novelty for brief & weekly review | outputs | S | Med |
