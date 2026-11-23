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
| HRV status | 7-day avg overnight RMSSD vs personal baseline band; Balanced/Unbalanced/Low/Poor; thresholds unpublished | Plews 2012–14: ln RMSSD, 7-day rolling mean; normal = baseline ± SWC (≈0.5 SD); CV rising signals strain | ln(RMSSD) nightly → 7d mean vs 60d mean ± 0.5 SD (⚠ 0.5 SD multiplier to confirm); plus 7d CV | Garmin status + ours, nightly value, band, "within / below / above normal", CV trend |
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

## Thresholds we need (stored with dates so history can be recomputed)
HRmax, RHR baseline, LTHR, threshold pace / CS, HR zones, body weight. Initial values come from Garmin (zones, LT, user profile); later from our own estimates when confidence is higher.

## Build mapping
Phase 3 = recovery/readiness · Phase 4 = load + performance · Phase 5 = workout coaching + fitness age (see ROADMAP.md).
