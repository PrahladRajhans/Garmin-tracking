# Metrics design: what we calculate and why

For each derived metric: what Garmin does, what the science says, what **we** do, and how it is presented.
Sources and citations: `research_notes/Garmin connector feature research/` (`metric_formulas.md`, `garmin_insights_reference.md`). Items marked ⚠ need checking against primary sources or your real data before we rely on them.

## Principles
1. **Two columns, never one series.** Garmin's value (Firstbeat, unpublished formula) is stored and shown as Garmin's. Our open value sits beside it with its formula. If they disagree, we say so.
2. **Baseline-relative, not population-relative.** Recovery signals compare you to your own rolling normal: the approach shared by HRV4Training, Plews et al., Athlytic, Oura and Whoop.
3. **Every number ships with:** value, your baseline or normal range, trend (7 vs 28 d), a one-line meaning, and the inputs used. Composite scores always show their components.
4. **Data sufficiency is explicit.** A baseline needs ≥14 nights (HRV ≥21, matching Garmin's ~3 weeks). Below that we return "calibrating", not a number.
5. **Watch-only honesty.** No chest strap means wrist HR during intervals and wrist power may be noisy. Metrics that depend on them carry a confidence note.

## FR955 data we build on (watch only)
Raw: 1 s HR, GPS pace and distance, barometric elevation, cadence, stride length, wrist running power, temperature, overnight RMSSD (HRV), RHR, respiration, SpO2, sleep stages, stress, Body Battery, steps, intensity minutes.
Garmin-computed (fetched as-is): Training Readiness plus factors, Training Status, Acute Load and Load Focus, Training Effect (aerobic/anaerobic) plus primary benefit, Recovery Time, VO2max, Race Predictor, Endurance Score, Hill Score, Lactate Threshold (⚠ may need a chest strap on FR955), Heat/Altitude acclimation, Fitness Age, HRV Status, Sleep Score.
Not available: skin temp, ECG, ground contact time balance (not computed from wrist). Vertical oscillation, GCT, vertical ratio ARE recorded via wrist-based Running Dynamics (fw 15.09+, Apr 2023; confirmed in our FIT data).

## Decisions

### Recovery and readiness
| Metric | Garmin | Science | **Our method** | Presented as |
|---|---|---|---|---|
| HRV status | 7-day avg overnight RMSSD vs personal baseline band; Balanced/Unbalanced/Low/Poor; thresholds unpublished | Plews 2012–14: ln RMSSD, 7-day rolling mean; normal = baseline ± SWC (≈0.5 SD); CV rising signals strain | ln(RMSSD) nightly → 7d mean vs 60d mean ± 0.5 SD; plus 7d CV. **Implemented v0.4.0.** 7-day rolling ln RMSSD + SWC verified: [AIS HRV guide](https://www.ais.gov.au/__data/assets/pdf_file/0013/1130260/HRV-BPG_FINAL.pdf), [PMC5721172](https://pmc.ncbi.nlm.nih.gov/articles/PMC5721172/). The 60-day window is **our design choice** (no source fixes it; one study used a 42-day EWMA). Needs ≥21 nights | Garmin status + ours, nightly value, band, "within / below / above normal", CV trend |
| Resting HR | Daily RHR | Elevated RHR (> ~5 bpm over baseline) tracks fatigue/illness | 7d mean vs 60d baseline, z-score | Delta in bpm with flag |
| Sleep | Sleep Score 0–100 (weights unpublished) | Duration vs need, regularity (Sleep Regularity Index), efficiency matter most | Store Garmin score and stages. Ours = duration vs 28d personal norm + debt (7-day Σ shortfall) + bedtime consistency (SD) | Hours, debt, consistency, Garmin score |
| Readiness | Training Readiness 0–100 from sleep, recovery time, HRV, acute load, sleep/stress history; weights unpublished | No validated composite exists | **Transparent z-score composite**: HRV (ln RMSSD z), RHR (inverted z), sleep (vs norm), load (TSB). Equal weights at first; shown component by component | Garmin readiness next to ours; components ranked by impact; "what's holding you back today" |
| Illness/strain flag | none explicit | HRV↓ + RHR↑ + respiration↑ together precede illness | Flag when ≥2 of HRV z<−1, RHR z>+1, respiration z>+1 for ≥2 days | Plain warning + the signals that triggered it |

### Training load and fitness
| Metric | Garmin | Science | **Our method** | Presented as |
|---|---|---|---|---|
| Session load | EPOC-based training load (Firstbeat) | Banister TRIMP (HR reserve), rTSS from normalised graded pace, sRPE | **Primary: TRIMP** (works for every HR-recorded activity). **Secondary: rTSS** for runs (needs threshold pace). Garmin load stored alongside | Per activity: Garmin load, TRIMP, rTSS |
| Fitness / fatigue / form | Acute Load, Load Balance, Training Status | CTL = 42d EWMA, ATL = 7d EWMA, TSB = CTL−ATL (Banister / Coggan) | CTL/ATL/TSB on TRIMP; ramp rate (CTL Δ per week) | Chart-ready series + today's form zone. TSB/ramp thresholds labelled **heuristics** |
| Load spikes | Acute load vs "optimal range" | ACWR is contested (Impellizzeri 2020, Lolli 2019): not an injury predictor | Week-over-week load change % and monotony/strain (Foster). **No ACWR "injury risk".** | "Load up 38% vs last 4 weeks" as fact, not a risk score |
| Intensity distribution | Load Focus: low aerobic / high aerobic / anaerobic | Seiler 3-zone (below VT1 / between / above VT2); polarised ≈ 80/20 | Time-in-zone from HR (zones from your LTHR, or Garmin zones until known); polarisation index (Treff) | % per zone over 4 wks next to Garmin's Load Focus, with a short "what that means" |
| Training status | Rule matrix: VO2max trend × load × HRV | No standard | Our label from CTL trend + eVO2max/CS trend + HRV band, rule table documented in code | Garmin status next to ours, with the reasons |

### Performance
| Metric | Garmin | Science | **Our method** | Presented as |
|---|---|---|---|---|
| VO2max | Firstbeat HR–speed regression, ~5% error vs lab | VDOT (Daniels–Gilbert); Runalyze-style HR-adjusted effective VO2max | Show Garmin's as the main value. Ours = VDOT from best recent race-like efforts, for a cross-check and trend | Value, 90-day trend, age/sex percentile |
| Race prediction | Proprietary, uses VO2max + volume | Riegel T2 = T1·(D2/D1)^1.06; VDOT tables; critical speed (CS) | Three open predictions (VDOT, Riegel with a personal exponent once ≥2 race efforts exist, CS) + Garmin's; report the spread | Table: 5K/10K/HM/M × method, plus "most realistic" with reasoning |
| Critical speed / threshold | Lactate Threshold (HR breakpoint) | CS from 2–3 maximal efforts (3–20 min); Friel LTHR from a 30-min TT | CS from the pace–duration curve; LTHR = Garmin's if present, else estimated | Threshold pace, LTHR, date, confidence |
| Pace curve | Personal records | Best mean pace per duration | Rolling best pace for 1 min → 2 h from FIT, GAP-adjusted (Minetti) | Curve + PRs + changes vs 90 days ago |
| Endurance / hill score | Composite scores | No standard | Fetch Garmin's. Our supporting views: long-run share, CTL; best VAM / GAP on climbs | Garmin score + what drives it |

### Workout coaching (per run)
| Metric | Science / rationale | **Our method** | Insight given |
|---|---|---|---|
| Efficiency factor (EF) | NGP ÷ avg HR (Allen/Coggan) | Per run, for steady efforts only | EF vs your 30-day norm at a similar effort: aerobic fitness trend |
| Aerobic decoupling (Pa:HR) | HR drift relative to pace, 1st vs 2nd half; <5% often cited (heuristic) | Steady runs ≥40 min | "Good durability" or "HR drifted 8%: heat, fatigue, or under-fuelled" |
| Cadence and stride length | Pace = cadence × stride; no universal ideal cadence | Cadence and stride at your common paces vs your history | How you gain speed (stride vs cadence), changes over time |
| Pace consistency | Split CV, negative/positive split | From laps and records | Pacing feedback |
| HR zones per run | Time in zones | From FIT HR stream | Was the run the intended intensity? |
| Training Effect | Garmin aerobic/anaerobic TE (Firstbeat) | Fetched | Garmin's label and what it trained |
| Running power | Garmin wrist power includes wind; not comparable to Stryd | Stored; power-based EF later | Shown with a caveat |
| Heat effect | HR at pace rises with temperature | HR-at-pace vs temperature from FIT/weather | "Run was 25°C: HR ~X bpm higher than usual at this pace" ⚠ calibrated on your data |

### Health
| Metric | Garmin | Science | **Our method** |
|---|---|---|---|
| Fitness age | Norm tables from VO2max, RHR, BMI/body fat, vigorous minutes | VO2max is the strongest predictor of all-cause mortality; age norms from large cohorts (e.g. HUNT) ⚠ confirm the formula | Show Garmin's. Ours: your VO2max matched to age-norm tables. Levers simulated: "+3 VO2max ≈ −X years", RHR, weekly vigorous minutes, weight |
| Stress / Body Battery | Firstbeat HRV-based, unpublished | Baevsky stress index needs RR data | Fetch and trend Garmin's; no own version (low value, no valid open method) |
| Intensity minutes | Moderate ×1 + vigorous ×2 vs 150/week (WHO) | Same WHO rule | Garmin's value; trend vs goal |
| Respiration / SpO2 / RHR | Measured | Baseline deviation matters more than absolute values | Baseline + z-score; feeds the illness flag |

## Implemented in v0.4.0 (Phase 3): exact rules
| Item | Rule |
|---|---|
| Nightly HRV input | Garmin overnight HRV (`hrv.last_night_avg`); history filled from export health status (`health_status.hrv`) |
| HRV state | 7-day mean of ln HRV (≥4 of 7 nights) vs 60-day mean ± 0.5 SD (≥21 nights, else "calibrating") |
| RHR / respiration z | today vs mean and SD of the previous 60 days (≥21 days) |
| Sleep | valid nights only (≥3 h; shorter records flagged incomplete). z = last night vs valid nights in the prior 28 calendar days (≥14 required as of v0.13.3). Debt = Σ max(0, need − actual) over valid nights in the last 7 calendar days; need = Garmin sleep need, else 8 h planning fallback (unified v0.13.3). Bedtime consistency = SD of sleep start over 14 nights |
| Our readiness | mean of signed z-scores clipped to ±3 (HRV +, sleep +, RHR −, respiration −). States: ≥0.5 fresher than usual · −0.5…0.5 normal · −1…−0.5 below usual · <−1 well below usual. Heuristic; Garmin readiness shown beside it |
| Illness/strain flag | ≥2 of {HRV z<−1, RHR z>+1, respiration z>+1} on each of the last 2 days |
| Suggestion | illness flag → rest/very easy · well below usual or Garmin POOR → rest/easy · below usual or Garmin LOW → easy aerobic only · fresher + Garmin HIGH/PRIME → key session · else planned training fine |

## Implemented in v0.5.0 (Phase 4): exact rules
| Item | Rule |
|---|---|
| Sex | watch profile in FIT (`user_profile.gender`) |
| HRmax | highest activity max HR in the last 365 days (Garmin's auto-updated setting shown beside it and flagged when ≥ 8 bpm apart) |
| Resting HR | median daily resting HR, last 60 days (Garmin's zone setting of 55 is not used) |
| LTHR | best 20-min rolling HR on a run ≥ 25 min in 365 days (Friel-style estimate; lower bound without a hard 20–30 min effort). Garmin's LTHR shown beside it |
| TRIMP | Banister per 1 s sample, men 0.64·e^(1.92x), women 0.86·e^(1.67x); gaps capped at 10 s; average-HR fallback without a stream |
| CTL / ATL / TSB | exponential, λ = 1 − e^(−1/N), N = 42 / 7 (design choice; TrainingPeaks uses 1/N). TSB = yesterday's CTL − ATL. Ramp = CTL − CTL 7 days ago |
| Monotony / strain | Foster: mean/SD of 7 daily loads; strain = weekly load × monotony |
| rTSS | hours × IF² × 100 with Minetti-graded speed / critical speed; **only computed when CS comes from maximal efforts** |
| Intensity zones | Seiler 3-zone from LTHR (design choice): Z1 < 0.90·LTHR, Z2 0.90–1.00, Z3 ≥ LTHR; Treff PI = log10(Z1/Z2·Z3·100), only when Z1 > Z3 > Z2 |
| Pace curve | best distance per window (1–120 min) from the FIT distance stream; outdoor runs only (treadmill speed is wrist-estimated) |
| Critical speed | 2-parameter linear fit on 3–20 min best efforts; flagged submaximal unless 50 ≤ D′ ≤ 400 m and r² > 0.95 |
| Effective VO2max | median over runs ≥ 20 min at ≥ 70 % HRmax of Daniels VO2(speed) ÷ Swain %VO2max (%HRmax = 0.6463·%VO2max + 37.182; Swain 1994) |
| Race predictions | effective-VO2max (VDOT tables), best-effort VDOT, best-effort Riegel 1.06, CS (5K/10K, only if maximal), and Garmin's, side by side; volume warning below 30 km/week (8-week average) |

## Sense checks (run by `garmin-mcp-verify` and the `sense_checks` tool)
| Check | Tolerance | Latest result on your data |
|---|---|---|
| Our ATL vs Garmin acute load | r > 0.7 | r = 0.81 (366 days) |
| Per-run TRIMP vs Garmin training load | r > 0.6 | r = 0.92 (19 runs) |
| Effective VO2max vs Garmin VO2max | within 10 | 42.0 vs 51.4 |
| Cadence × stride = speed (unit check) | within 5 % | −0.3 % |
| HR-zone time vs Garmin's FIT zone times | ≤ 5 % | 4.3 % all sports; 0–1 % on runs |
| LTHR < HRmax | — | 166 < 193 |
| Garmin max-HR setting vs observed | within 8 bpm | **flag:** 209 vs 193 |

## Implemented in v0.6.0 (Phase 5): exact rules
| Item | Rule |
|---|---|
| Steady run | ≥ 20 min moving (speed > 1 m/s) and 1-min speed CV < 15 % |
| Efficiency factor | Minetti-graded speed (m/min) ÷ average HR |
| Decoupling (Pa:HR) | (EF 1st half − EF 2nd half) / EF 1st half × 100; < 5 % = Friel heuristic |
| HR drift | average HR 2nd half − 1st half (steady runs) |
| Cadence | FIT one-foot cadence × 2 (spm) |
| Vertical ratio | vertical oscillation / step length × 100 (matches Garmin's session value) |
| Matched-pace norm | median of runs within ±15 s/km (widened to ±30 if < 3 runs) in 180 days |
| Form trends | monthly medians within your median pace ± 30 s/km |
| Heat effect | regress HR on speed across runs, then the residual on watch temperature: slope in bpm/°C (≥ 8 runs); watch temperature reads high, so only the slope is used |
| Fitness age | Garmin's value and Garmin's own levers (target, potential age) |
| Goal verdict (v0.7.0) | gap = median prediction vs target: ≤ 0 on track · ≤ 3 % within reach · ≤ 8 % ambitious · > 8 % very ambitious (heuristic bands); cautions for > 10 % method spread or volume below the usual range |

## HRmax policy (updated 2026-11-23)
HRmax = max(repeatable activity peak, Tanaka 208 − 0.7·age), unless you set `hr_max_override`.
Repeatable peak = highest activity max HR that another activity matched within 3 bpm. On your data:
- One treadmill peak of 193 (10 Dec 2025) rose 41 bpm in about 60 s at easy pace and fell 25 bpm in 20 s, so it is flagged as an optical spike.
- Repeatable peak 177; Tanaka 188; so HRmax = 188.

Calibrating from other sports:
- HRmax already uses every activity.
- LTHR comes from runs, because thresholds are sport-specific and run HR is typically higher than swim HR.
- Wrist HR in water is unreliable, and strength sessions never reach sustained threshold.
- Critical speed needs maximal run efforts, so swims and strength can't calibrate run pace thresholds.

## Implemented in v0.9.0 (Phase 8): statistics
| Item | Rule |
|---|---|
| Baseline adjustment | value − trailing 28-day mean (≥ 10 prior values) |
| Relationship | Pearson r on adjusted values, ≥ 30 paired days, 95 % moving-block bootstrap CI (block 7 d, 1,000 resamples); BH q < 0.10 and abs(r) ≥ 0.15 = notable; measured false-positive rate 1.7 % |
| Trend | Theil-Sen slope per 30 days, 95 % bootstrap CI; flat if CI includes 0 |
| Personal range | Garmin health-status baseline bands; else 60-day mean ± 1 SD |
| Form % | (CTL − ATL)/CTL × 100 (intervals.icu); suppressed when CTL < 20 |
| Load flags | 7-day load > 1.3 × 4-week weekly mean; longest run > 1.3 × longest of prior 30 days |
| Tag impact | next-day baseline-adjusted HRV, sleep score and resting HR, tagged vs untagged days (≥ 5 tagged) |

## Implemented in v0.11.0 (Phase 10a): daily scores
| Score | Formula | Sense check (your data) |
|---|---|---|
| Recovery % | 100·Φ(composite z); green ≥ 67, yellow 34–66, red ≤ 33 | vs Garmin readiness r = 0.35 (> 0.3); bands 35 % green / 22 % red |
| Sleep % | sleep h / need h × 100; need = Garmin sleep need, else 8 h; < 3 h = incomplete | vs Garmin sleep score r = 0.85 |
| Strain | min(21, 6.3·ln(1 + TRIMP/20)); target band green 10–14, yellow 8–12, red 0–8 (heuristic) | 0–21; easy run ≈ 9, hard 2 h ≈ 16 |
| Bedtime | median wake (14 valid nights, local) − need − min(60 min, debt/7) | wake times cross-checked with Garmin local timestamps |

### Open question: max HR
188 (observed repeatable peak 177 + Tanaka) vs about 209 (Garmin's model).
- Using 209, effective VO2max is about 48, close to Garmin's 51.
- Using 188, it is about 40.

Zones, TRIMP and effective VO2max all depend on it, so the sense check stays flagged until a hard-effort test settles it.

## Implemented in v0.12.0 (Phase 12): exact rules
| Metric | Rule | Source / check |
|---|---|---|
| Heart-rate difference | (recorded awake mean on prior day − sleep avg HR) ÷ awake mean × 100. Known sleep windows excluded; stop 30 min before current sleep; require ≥60 positive daytime samples. UTC interpretation explicit. | Descriptive only. The prior BP-derived ≥10% healthy cutoff was removed in v0.13.3; not a recovery diagnosis |
| Sleep breakdown | Garmin `sleepScores` parts with `qualifierKey` and optimal start/end, shown as-is | Garmin |
| Activity status | Days tagged sick/injured/break/illness removed from every recovery baseline series (except the day scored); suggestion becomes "advice paused" | Bevel |
| Pace of ageing | Theil-Sen slope of Garmin fitness age × 365 over 180 days; needs ≥ 30 values spanning ≥ 90 days. 1.0 = calendar pace | Whoop scale. Check: 30 days gave 3.1 from a 0.3-yr wobble → span rule added |
| Shift detection | For each split k with ≥ 14 days on both sides: \|mean after − mean before\| ÷ mean of the two within-segment SDs; report the best split if ≥ 1.0 | Simple, transparent stand-in for PELT |
| Marathon shape | V = effective VO2max (≥ 25). Weekly target V^1.135 km; long-run target 12·ln(V/4) km. Long runs > 13 km in the last 70 days score (2 − 2·ago/70)·((d − 13)/(target − 13))². Shape = 100·(0.67·weekly km/target + 0.33·Σpoints·7/70), shown clamped 0–100. A race needs distance_km^1.23 % (5K 7, 10K 17, half 42.5, marathon 100) | Runalyze source (`MarathonShape.php`). Check: 1.1 km/week → 1 % |
| Running form bands | Garmin colour gauges. Cadence spm: red < 153, orange 153–163, green 164–173, blue 174–183, purple ≥ 184. GCT ms: purple < 218, blue 218–248, green 249–277, orange 278–308, red > 308. VO cm: < 6.4 / 6.4–8.1 / 8.2–9.7 / 9.8–11.5 / > 11.5. VR %: < 6.1 / 6.1–7.4 / 7.5–8.6 / 8.7–10.1 / > 10.1 | Garmin owner's manual (fēnix 7 v12 tables; same across models). Chest-strap values used for wrist data |
| Pace-matched form | Least-squares line of each form metric vs average speed over up to 120 earlier runs (≥ 5 runs); a run is compared with the line at its own speed | Cadence and stride rise with speed (Moore 2016 review) |
| Running effectiveness | speed (m/s) ÷ (power W ÷ weight kg) | Coggan/WKO (Palladino). Garmin wrist power reads higher than Stryd, so compare only with yourself |
| Cadence advice | If < 170 spm: suggest +5 % at the same pace, in short metronome blocks | Heiderscheit 2011 (knee energy absorption falls at +5 %), Lenhart 2014 (+10 % → −14 % patellofemoral force), Willy 2016 (+7.5 % retained at 1 month) |

## Implemented in v0.13.0 (Phase 13): exact rules
| Metric | Rule | Result on your data |
|---|---|---|
| Explorer points | `engine.pair_points`: baseline-adjusted x on day d, y on d + lag; same pairs as v0.9.0 relationships | 14 pairs tested; 4 notable |
| "How sure" | Not notable (FDR) → "not sure: could be chance"; CI excludes 0 and its smaller end ≥ 0.3 → "very sure"; ≥ 0.1 → "fairly sure"; else "early sign" | Sleep → Garmin readiness: very sure |
| Test runs | Steady runs (≥ 20 min, 1-min speed CV < 15 %) within ±10 % of the median steady-run distance, or named test/calibration; Theil-Sen slope of efficiency factor, × 90 days ÷ mean | 3 runs at ~5.2 km, +1.8 % / 90 d (too few to trust) |
| Recovery weighting study | Signals: the clipped components of `recovery.readiness`. Outcomes: next-night ln HRV z (vs prior 60 nights, ≥ 21) and Garmin readiness. Variants: equal, without breathing, HRV + RHR. Change only if better on both by > 0.05 r | Equal weights kept (0.36 / 0.36) |

## Thresholds we need (stored with dates so history can be recomputed)
HRmax, RHR baseline, LTHR, threshold pace / CS, HR zones, body weight. Initial values come from Garmin (zones, LT, user profile); later from our own estimates when confidence is higher.

## Build mapping
Phase 3 = recovery/readiness · Phase 4 = load + performance · Phase 5 = workout coaching + fitness age (see ROADMAP.md).

## v0.13.1: unavailable relationships and pending norms

`engine.relationship` now returns `available: false`, `status: insufficient variation`, and a
reason when a baseline-adjusted signal is constant or no valid bootstrap samples remain.
It does not fabricate a correlation or confidence interval. Existing baseline adjustment,
minimum pairs, block size, bootstrap count, and Benjamini–Hochberg thresholds are unchanged.

The age/sex VO2max bar remains pending: the primary norm table could not be retrieved because
the cloud network policy blocks the medical-reference sites tested. No norm values, percentiles,
age interpolation, or replacement formulas have been added. Obtain and cite the exact primary
table before implementing this item. Existing Garmin and effective VO2max calculations are unchanged.

## v0.13.3: accuracy corrections

- One shared 8-hour sleep planning fallback (`recovery.DEFAULT_SLEEP_NEED_H`) drives debt,
  scores and bedtime when Garmin's value is absent/nonpositive. This is our configurable-code
  design assumption, **not** the AASM minimum or a measured personal need. The primary
  [AASM/SRS consensus](https://pmc.ncbi.nlm.nih.gov/articles/PMC4434546/) says adults should
  sleep **7 or more hours** regularly; it does not justify treating 7 or 8 as this person's exact need.
- Debt includes `debt_inputs` with each day's hours, target, shortfall and source; missing nights
  are not imputed, and zero observed nights returns null debt. Sleep z needs ≥14 prior valid
  nights; RHR/respiration need ≥21 prior values. These sufficiency thresholds are design rules.
- Equal clipped readiness weights, TRIMP, HRmax policy, effective VO2max and FDR thresholds are
  unchanged. No new weight study on real data has been performed. Composite variants now use
  the same paired days per outcome; HRV-only days are retained and zero correlations are valid.
- The heart-rate comparison no longer assigns health status. Daytime activity/sampling and wrist
  measurement can influence it. Fitness-age slope is a trend in Garmin's score, not biological age.
- See [accuracy review](research_notes/Garmin%20connector%20feature%20research/accuracy_review_2026-11.md)
  for source access, limitations and the further verification queue.


## v0.14.0: VO₂max population reference

Source: Kaminsky LA, Arena R, Myers J. *Mayo Clin Proc.* 2015;90(11):1515–1523.
[doi:10.1016/j.mayocp.2015.07.026](https://doi.org/10.1016/j.mayocp.2015.07.026).
[Primary Table 3](https://pmc.ncbi.nlm.nih.gov/articles/PMC4919021/#T3), exact measured FRIEND rows
below, mL O₂/kg/min. Unused Cooper predicted rows are retained in the research CSV, not mixed in.

| Sex | Age | 5th | 10th | 25th | 50th | 75th | 90th | 95th |
|---|---|---|---|---|---|---|---|---|
| male | 20–29 | 29.0 | 32.1 | 40.1 | 48.0 | 55.2 | 61.8 | 66.3 |
| male | 30–39 | 27.2 | 30.2 | 35.9 | 42.4 | 49.2 | 56.5 | 59.8 |
| male | 40–49 | 24.2 | 26.8 | 31.9 | 37.8 | 45.0 | 52.1 | 55.6 |
| male | 50–59 | 20.9 | 22.8 | 27.1 | 32.6 | 39.7 | 45.6 | 50.7 |
| male | 60–69 | 17.4 | 19.8 | 23.7 | 28.2 | 34.5 | 40.3 | 43.0 |
| male | 70–79 | 16.3 | 17.1 | 20.4 | 24.4 | 30.4 | 36.6 | 39.7 |
| female | 20–29 | 21.7 | 23.9 | 30.5 | 37.6 | 44.7 | 51.3 | 56.0 |
| female | 30–39 | 19.0 | 20.9 | 25.3 | 30.2 | 36.1 | 41.4 | 45.8 |
| female | 40–49 | 17.0 | 18.8 | 22.1 | 26.7 | 32.4 | 38.4 | 41.7 |
| female | 50–59 | 16.0 | 17.3 | 19.9 | 23.4 | 27.6 | 32.0 | 35.9 |
| female | 60–69 | 13.4 | 14.6 | 17.2 | 20.0 | 23.8 | 27.0 | 29.4 |
| female | 70–79 | 13.1 | 13.6 | 15.6 | 18.3 | 20.8 | 23.1 | 24.1 |

`norms.reference` selects the published age decade and recorded sex. No interpolation,
extrapolation, default sex/age, exact personal percentile, or population-based fitness age.
The Body page shows Garmin and effective estimates separately. Effective pace/HR VO₂max is
not physiologically equivalent to measured CPX VO₂max, and depends on untested HRmax unless
overridden. These are US cohort reference points, not personal targets or an Indian population norm.
Source/limits and all 24 transcribed rows: [research note](research_notes/Garmin%20connector%20feature%20research/friend_2015_reference.md).

The v0.13.1 note about blocked primary-table access is historical; access was restored and
this table retrieved before implementation. No source values were reconstructed from memory.

## Personal-range freshness and baseline semantics (v0.14.1)

`engine.personal_ranges` uses the requested day's metrics, not the latest historical health-status
row. Complete, valid Garmin bounds are used only for that day. Otherwise a personal mean ± one
sample standard deviation uses the preceding 60 days, excluding the scored day: at least 21
prior values for HRV/resting HR/respiration, 14 valid nights for sleep HR/SpO₂. Nights under
three hours, nonpositive/nonfinite values and zero-variation baselines do not establish a range.
A current Garmin health-status value may fill a missing same-day series value. Missing ranges
are calibrating; above/below describes a personal baseline, not disease or fitness clearance.
`as_of` names the requested day and `range_available` distinguishes thin history. No recovery
weights, statistical/FDR rules or physiological conversion constants changed in v0.14.1.

## FIT run timing and split evidence (v0.14.2)

In `coaching.run_metrics`, recorded moving duration sums positive adjacent FIT timestamp
intervals of at most 10 seconds with speed above 1 m/s at both ends. The minimum is 120
seconds of such intervals. The 10-second gap limit and speed threshold are engineering
choices. Missing intervals are excluded from this estimate. Pace and grade-adjusted speed
use end-sample values weighted by interval duration. Minute CV uses complete 60-second
moving-time bins; the existing steady criterion is at least 1,200 seconds and CV below 15%.
Efficiency uses matched speed and HR intervals. For the overall value and either moving-time
half, valid HR must cover at least 90% of the corresponding duration. Decoupling remains
100 × (first-half EF − second-half EF) / first-half EF. HR change is second minus first
weighted HR in bpm. Neither establishes aerobic fitness by itself.

Recorded elapsed time spans the first to last FIT record. Elapsed splits use monotonic
cumulative distance relative to the first usable distance and interpolate crossings between
nearby records (explicitly recorded boundary timestamps are used directly). A distance reset
or unresolvable kilometre crossing suppresses the splits. Pauses count toward elapsed splits.
For 4 km or more, the elapsed comparison uses two equal recorded distances, including the
last partial kilometre. Second minus first gives the signed delta in seconds. Differences
within one second are shown as approximately even. Garmin FIT summary timer and elapsed
fields are displayed separately for a single stored session.

Source: [Garmin FIT Cookbook, Elapsed, Timer, and Moving Durations](https://developer.garmin.com/fit/cookbook/durations/).
The watch timer may start before the first sample and end after the final sample. These time
definitions can differ on correctly recorded activities. Tests use known fixture values.
Garmin history and current device data still require a Mac verification run.
