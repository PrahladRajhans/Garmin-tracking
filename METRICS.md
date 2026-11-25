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
| LTHR | best time-weighted 20-min HR window on a run ≥ 25 min in 365 days. Require ≥ 90% measured time in the window, using positive adjacent intervals ≤ 10 s with usable end-sample pulse. Fall back to Garmin's threshold when no window qualifies. A field test or explicit override can replace the heuristic. |
| TRIMP | Banister weighted by measured sample duration, men 0.64·e^(1.92x), women 0.86·e^(1.67x). Use a stream covering ≥ 90% of recorded workout duration, or valid average HR and that duration. Require compatible resting and maximum HR. Otherwise return missing load. |
| CTL / ATL / TSB | exponential, λ = 1 − e^(−1/N), N = 42 / 7 (design choice; TrainingPeaks uses 1/N). TSB = yesterday's CTL − ATL. Ramp = CTL − CTL 7 days ago |
| Monotony / strain | Foster: mean/SD of 7 daily loads; strain = weekly load × monotony |
| rTSS | hours × IF² × 100 with Minetti-graded speed divided by an explicit threshold pace or critical speed from maximal efforts. Uses the same distance-window grade as running analysis. |
| Intensity zones | Seiler 3-zone from LTHR (design choice): Z1 < 0.90·LTHR, Z2 0.90–1.00, Z3 ≥ LTHR; Treff PI = log10(Z1/Z2·Z3·100), only when Z1 > Z3 > Z2 |
| Pace curve | best distance per window (1–120 min) from the FIT distance stream; outdoor runs only (treadmill speed is wrist-estimated) |
| Critical speed | 2-parameter linear fit on 3–20 min best efforts; flagged submaximal unless 50 ≤ D′ ≤ 400 m and r² > 0.95 |
| Effective VO2max | median over runs ≥ 20 min at ≥ 70 % HRmax of Daniels VO2(raw summary speed) ÷ Swain %VO2max (%HRmax = 0.6463·%VO2max + 37.182; Swain 1994) |
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
| Cadence | FIT one-foot running cadence **plus its fractional part** (`fractional_cadence`), × 2 (steps/min). Before v0.32.1 the fraction was dropped, which read about 0.9 spm below the watch. Cycling streams and workout details keep the recorded revolutions per minute. |
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

The Garmin comparison uses the most recent FIT zone maximum-HR setting on or before the
selected day, within the field's 1–254 bpm range. With no usable record, the setting is unavailable.

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
| Running form bands | Garmin colour gauges. Cadence spm: red < 153, orange 153–163, green 164–173, blue 174–183, purple ≥ 184. GCT ms: purple < 218, blue 218–248, green 249–277, orange 278–308, red > 308. VO cm: < 6.4 / 6.4–8.1 / 8.2–9.7 / 9.8–11.5 / > 11.5. VR %: < 6.1 / 6.1–7.4 / 7.5–8.6 / 8.7–10.1 / > 10.1 | [Garmin FR955 manual](https://www8.garmin.com/manuals/webhelp/GUID-9D99A9D4-467A-4F1A-A0EA-023184FEA3DD/EN-US/GUID-62A09512-518A-424A-8491-FE2B80CD2091.html). The UI labels the chest reference for bounce and ratio |
| Pace-matched form | Least-squares line of each form metric vs average speed over up to 120 earlier runs (≥ 5 runs); a run is compared with the line at its own speed | Cadence and stride rise with speed (Moore 2016 review) |
| Running effectiveness | speed (m/s) ÷ (power W ÷ weight kg) | Coggan/WKO (Palladino). Garmin wrist power reads higher than Stryd, so compare only with yourself |
| Cadence advice (historical) | The old 170 spm trigger was replaced by the current gated cadence experiment below | Heiderscheit 2011 (knee energy absorption falls at +5 %), Lenhart 2014 (+10 % → −14 % patellofemoral force), Willy 2016 (+7.5 % retained at 1 month) |

## Implemented in v0.21.0: coaching follow-up (`trials.py`)
| Item | Rule |
|---|---|
| Attempt | Any outdoor run with FIT data that starts after the experiment began and before it closed |
| Did it (cadence) | Moving seconds (speed > 1 m/s) with FIT cadence × 2 ≥ target − 2 steps/min, converted to minutes using the median sample interval |
| Felt | Garmin `workoutFeel` 0/25/50/75/100 = very weak/weak/normal/strong/very strong. `workoutRpe` 10–100 ÷ 10 = effort 1–10. Other values are ignored |
| Comparison runs | Same activity type, steady (≥ 20 min, 1-min speed CV < 15 %), average pace within ±30 s/km and moving time within ±40 % of the attempt, before the experiment started; most recent 6. Needs ≥ 2 |
| Change | Attempt minus the median of the comparison runs. "About the same" under: HR 3 bpm, efficiency 3 %, drift 2 points, cadence 2 spm, stride 0.02 m (typical wrist-data run-to-run noise; heuristic) |
| Verdict | < 3 attempts: "early". From 3 attempts: median efficiency change and median next-morning knee score |
| Safety | Knee ≥ 4/10 during or next morning → next step is to stop and rest |

## Opt-in conditions retrieval (v0.21.0, `weather_fetch.py`)
| Item | Rule |
|---|---|
| Consent | Off unless `meta.weather_opt_in = 1` (tool `weather_retrieval(enable=True)` or `garmin-mcp-weather --enable`) |
| Sent | First recorded GPS point rounded to 2 decimals (~1.1 km) and the run's UTC date range. Weather may include the following UTC date for the midnight rain reading |
| Endpoint | Run within 60 days: Open-Meteo forecast API (recent past); older: archive API. Air quality: Open-Meteo air-quality API (`us_aqi`) |
| Stored | One window per UTC hour that overlaps the FIT timeline; kind `model`; values outside `conditions.FIELDS` limits are dropped; AQI rounded to an integer, US-EPA scale |
| Scope | Outdoor runs from the last 14 days without existing condition windows, at most 10 per sync |

## Optional local narration (v0.22.0)

- Python supplies the same recovery score, recovery band and Garmin readiness used elsewhere on
  the dashboard. Overnight facts use the complete night ending on the snapshot date and optional
  Garmin scores and sleep need. Run facts use the displayed distance, FIT pace, average heart rate
  and cadence. The experiment uses the number of reviewed attempts and the measured cadence
  target/time available from `trials.py`. Other recent workouts use Garmin summary duration,
  distance and average heart rate. The Training recap uses the existing seven-day review's
  activity-load join, total load points and the available-night mean rounded to 0.1 h.
  Location, dates, names and free-form notes are omitted from prompts.
- Displayed summaries contain 1–3 plain sentences, at most 60 words. Every number appears in the input
  values. Decimal formatting such as `5.7` → `5.70` is accepted. Pace and ratio values are checked
  together as complete tokens. Unverifiable number formats, spelled-out numerals, and language
  such as “diagnose”, “disease”, “injury risk”, or “guaranteed” are rejected.
- Ollama receives numbered candidate sentences and returns a JSON array of their permitted IDs.
  Python resolves and checks each sentence against its permitted metric, number, unit, and
  source. This prevents a valid number from being swapped into another measurement or
  used for new advice, a prediction, or a medical claim. Repeated facts display once.
  The text and its facts are escaped in HTML.
- Today can submit two or more findings already qualified by `daily_focus`, including their
  supporting evidence and existing follow-ups. Ollama chooses one integer ID. Python accepts
  only an ID from that request, moves the corresponding finding to the top, and displays its
  original text and link. The choice applies only to display order.
- Valid and rejected results are cached locally by a hash of model, prompt rules and input facts.
  Unavailable Ollama, a timeout or an unfinished response leaves the existing dashboard text
  available and can be retried by a manual rebuild or scheduled sync check.
- Open-ended Today, Sunday and Running reviews group the measured value and baseline in one
  citation and require evidence from at least two current categories. Running pace evidence states
  the direction of the seconds-per-kilometre change explicitly. Matched late-run cadence retains
  the measured comparison time and pace/grade qualification. A Python check filters unsupported
  premises in the model's follow-up question and can replace that question with a repeat check
  from its cited signals. A separate review checks the observation and final question, including
  after a single correction. Training decisions and source values stay in Python.

## Outdoor conditions and following recovery

- Reuse the outdoor run matching rules for run type, pace, moving time and ascent.
  Compare time-weighted condition medians only when a single source covers at least 80%
  of each FIT interval. Observation and model windows stay separate. AQI also requires
  the same standard. The Garmin weather snapshot stays separate.
- Training takes up to 60 days with one recorded outdoor workout from the last 180 days.
  Within the same conditions source, reading type and AQI standard, pair runs within 42 days,
  the same two-decimal start-location cell, and within 3 hours of local time of day.
  Each day can appear once per exposure/source group. The required contrast is 3 °C, 15
  relative-humidity percentage points, or 20 AQI points. These are comparison cutoffs.
- An outcome uses 6 or more separate pairs spanning at least 14 days. Report the median
  of the within-pair changes (higher minus lower condition value). Follow-up health
  requires a valid Garmin night on the next local wake date, with its sleep start within
  24 hours after the run. Each outcome uses only pairs with two readings. Skip days tagged
  sick, injured or on a break. Date/time matching does not require that the later night's
  building shares the run location.
- These comparisons describe associations in the owner's records. Indoor air, route, effort,
  fitness change, correlated weather variables and other factors can still differ. Outdoor
  readings describe the area and may use averaged or modelled values. No values are used
  to adjust scores or prescribe training. [Environmental evidence and limits](research_notes/Garmin%20connector%20feature%20research/environmental_context_feasibility.md)

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
use end-sample speed weighted by interval duration. Both grade-adjusted speed and the early/late
form comparison estimate grade from elevation change over a 20 m distance window around each
interval. The window shifts at segment ends and interpolates its elevation endpoints, so closely
spaced samples can contribute. Windows stay within increasing distance, finite elevation and
contiguous active samples separated by at most ten seconds. When grade is unavailable, speed
remains unadjusted and the interval cannot support a grade-matched form comparison. Minute CV
uses complete 60-second moving-time bins; the existing steady criterion is at least 1,200
seconds and CV below 15%.
Efficiency uses matched speed and HR intervals. For the overall value and either moving-time
half, valid HR must cover at least 90% of the corresponding duration. Decoupling remains
100 × (first-half EF − second-half EF) / first-half EF. HR change is second minus first
weighted HR in bpm. Neither establishes aerobic fitness by itself.

Daily and weekly TRIMP totals require usable load for every recorded workout in the period.
A day without a recorded workout can contribute zero. The smoothed curves use recorded
contributions and continue to decay over time. Missing sessions can lower those curves,
so an incomplete day or week does not generate a load comparison or daily strain score.
This coverage policy is an engineering choice. Match the new results against the owner's
archive before interpreting a change in long-term trend.

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

## Monthly and pattern evidence (v0.14.3)

Monthly HRV averages one positive finite nightly value per day. `recovery.nightly_hrv`
prefers the dedicated HRV table, with Garmin health status filling missing dates. Sleep averages
still require a record of at least three hours. The report returns calendar length and
per-input counts for both months. Comparisons describe recorded observations, and coverage
can differ by month. Bars use a zero origin and the largest observed month in that metric.

Patterns ranks passing pairs before exploratory pairs. A fit line appears for a pair only
when the established q < 0.10 and |r| ≥ 0.15 rule is met. Baseline, minimum pair count,
Pearson/bootstrapping and false-discovery formulas are unchanged. Seven-observation blocks
can span more than seven calendar days when measurements are missing. Confounding, common
sources, watch wear and selective recording can bias these associations. The displayed
interval does not establish an individual's future response.

## Nightly HRV consistency and visible insight evidence (v0.15.0)

The health snapshot's 7-day and 60-day HRV averages and the trend/relationship inputs
now use `recovery.nightly_hrv`. A valid positive finite value in the dedicated HRV table
wins for that date. Health status supplies a valid value when dedicated data is missing
or invalid. Snapshot averages include the selected day and expose their observation
counts. Existing recovery weights and statistical evidence cutoffs remain unchanged.

Training uses the established `insights.weekly_review` date windows, while explicitly
showing recorded sessions and the count of usable nights. Charts label partial weeks
and keep absent training weeks blank. Today cites the sign and units of supported
trends, the number of readings, and the record date. Treat linked patterns as personal
associations and load suggestions as coaching heuristics. Link validation needs both
the Garmin record for the date and a consistent input history.

## Personal comparison cards and paired telemetry (v0.16.0)

`signal_context.collect` compares arithmetic averages of the most recent seven calendar
days and the seven days before them. Each window needs at least four readings. Its
personal reference is the mean ± one sample standard deviation from the 60 days ending
before the current seven-day window, omitting explicitly tagged sick, injury or break
days. Resting pulse needs 21 reference observations and the sleep metrics need 14.
A constant series does not establish a range. Sleep duration, breathing and Pulse Ox
use nights with at least three recorded hours. Pulse Ox accepts 0 < x ≤ 100 and caps
the reference at the physical ceiling. Changes are shown in percentage points.
HRV retains the separate established log RMSSD model and band. No forecasting or
clinical thresholds were added. Coverage and personal reference are reported by
`insight_feed`. Lasting shift detection uses the deduplicated nightly HRV source.

Reference context: [MedlinePlus adult resting pulse](https://medlineplus.gov/ency/article/003399.htm),
[FDA pulse oximeter limitations](https://www.fda.gov/medical-devices/products-and-medical-procedures/pulse-oximeters),
[HRV measurement context](https://pmc.ncbi.nlm.nih.gov/articles/PMC5624990/) and
[AASM adult sleep consensus](https://pmc.ncbi.nlm.nih.gov/articles/PMC4434546/). General adult
guidance and a personal range describe different things. Wrist readings require attention
to sensor, altitude and fit.

For run overlays, use paired valid FIT samples on a common elapsed-time axis. Each line
is 100 × (sample / median of that signal's paired samples − 1). A gap exceeding twice
the sampling interval breaks the line. Actual values remain in the cursor readout. The
FIT SDK gives step length in mm (÷ 1000 for m) and running cadence per foot (× 2 for
steps/min). Overlay visibility and scaling do not establish correlation or causation.
Hourly day pulse averages observed raw samples grouped by local hour in the configured
time zone for the latest seven days.

## Matched run evidence and outdoor conditions (v0.17.0)

- **Moving heart rate on comparable runs.** Use the existing time-weighted FIT moving
  heart rate (≥90% HR coverage). The target and candidates must be steady (≥20 recorded
  moving minutes and speed variation under 15% across complete one-minute windows) and
  moving samples must cover at least 80% of the FIT record span. Select the eight most
  recent earlier runs at most, in the previous 180 days, of the same outdoor activity
  type. Match pace within 15 s/km, moving time within ±20% of the target and Garmin
  total ascent divided by Garmin distance within 5 m/km. A confirmed zero ascent is
  valid. Missing ascent cannot establish a match. Use GMT start time when both runs
  have it, otherwise local start times. Report the target minus the median in bpm and
  the min–max of the earlier measurements when at least three qualify. The span is an
  observed reference, with no clinical threshold. These are matching rules to validate
  on the archive. Pace and ascent density do not identify the route, grade pattern,
  effort, weather, surface or sensor accuracy.
- **Pace and form.** A regression-based form reference stays within the observed speed
  range for that metric and the matched-pace median needs three values per metric.
  The cadence check uses a change from personal form at the observed pace (below −3%),
  a display heuristic. Garmin colour gauges are shown as descriptive comparisons.
- **Steady-run efficiency trend.** Restrict the existing Theil-Sen trend to steady
  outdoor runs within 10% of their median distance and on at least three dates.
  Workout names no longer bypass those checks. The output describes grade-adjusted speed
  per heartbeat rather than a direct measure of fitness.
- **Readiness benchmark.** In the last 365 days, use each day’s earliest valid Garmin
  readiness record with a raw Garmin UTC timestamp. The snapshot must precede the
  qualifying run’s GMT start. Join at most the first qualifying run per local date.
  Outcome is its moving bpm minus the median of earlier matched efforts. Compute
  Spearman rank correlation with tied ranks averaged after at least 20 paired days
  and with both quantities varying. The minimum is a coverage gate. Repeated courses,
  shared reference runs, season and training decisions can affect the result.
  A negative value means higher recorded readiness tended to accompany lower HR at
  comparable pace. This is retrospective and does not modify either readiness score.
- **Conditions.** The unofficial Garmin activity-weather DTO supplies a saved
  `temp` in °F, converted to °C as `(°F − 32) × 5/9`, and `relativeHumidity` in %.
  `issueDate` is displayed only as an upstream reference string. Garmin wind units can
  depend on account settings, so only unit-explicit local wind is displayed in m/s.
  Source windows preserve supplied temperature in °C, relative humidity in %, wind
  in m/s, precipitation in mm over its window and reported AQI with its named standard.
  UTC-aligned windows cover FIT timestamps from start inclusive to end exclusive.
  Gaps are blank. Zero is a valid reading. The observed interval belongs to the source,
  so AQI may describe a rolling or daily measurement. Weather and AQI do not adjust HR,
  efficiency or coaching. The earlier wrist-temperature heat slope was withdrawn.

[Source methods, unit evidence and scope](research_notes/Garmin%20connector%20feature%20research/owner_reference_review_2026-11.md#implemented-in-v0170).

## Coaching focus and readiness coverage (v0.18.0)

- **Recovery coverage.** At least three of four personal z-score components must qualify
  to show our composite and colour or set a strain target. Components remain visible in
  MCP and Garmin’s score stays separate. The threshold is a product coverage policy, with
  no claim about its predictive accuracy. The historical agreement figures above predate
  this gate. High readings support the session already planned. An illness pattern or Garmin Low/Poor can still suggest an easy day or rest.
- **Seven-day coaching start.** Use the four complete seven-day blocks preceding the
  requested date. Count distinct run days and the shorter recorded duration on multiple-run
  days. Exclude workouts under five minutes and tagged sick, injured or break days.
  If the median count is below one or the last two blocks have no eligible run, offer an
  optional 10-minute easy walk as a general starting point. Otherwise use the floored
  median run-day count, capped at three. Duration is the smaller of 45 minutes, the
  median recorded session duration and the median weekly minutes divided by the plan’s
  count, rounded down to whole minutes. Calibration, below-usual recovery or Garmin Low
  brings the first easy outing down to one session of at most 20 minutes. Tagged days
  pause the plan. Illness signals, well-below-usual recovery or Garmin Poor suggest
  resting and reassessing. The plan does not schedule or upload workouts.
- **Optional cadence trial.** With a knee note, a steady outdoor run, and positive cadence
  readings in at least 80% of the run’s moving FIT samples, offer a one-minute trial at
  the measured cadence × 1.05 (rounded to the nearest step/min). Keep the same comfortable
  easy pace. The display rule does not override tagged days. The one-minute duration is a
  conservative trial design. Lab studies measure per-step mechanics; they do not establish
  that this trial will change knee symptoms or long-term injury risk.
  [Heiderscheit et al. (2011)](https://pubmed.ncbi.nlm.nih.gov/20581720/)

## Today coaching priorities (v0.19.0)

- The daily cue respects tagged days, an illness/recovery warning and Garmin Poor/Low.
  A rise in resting pulse of at least 1 rounded bpm versus the preceding seven-day
  period, above the personal range, supports an easy-day cue when sleep is also
  at least ten minutes shorter and below its range, or HRV is below its range.
  This rule uses existing personal comparisons and is a training choice,
  with no validated prediction for the next workout.
- Offer a sleep action when four or more nights in the last seven average at least 30
  minutes below their mean recorded Garmin targets or the stated 8-hour fallback.
  The 30-minute earlier routine is a simple trial. A qualifying same-day
  sleep/readiness relationship can supply its estimated points per hour and paired-day
  count. It uses the existing baseline adjustment and discovery rule and describes history.
- Show Garmin Detraining with actual seven-day running kilometres and the existing
  conservative plan. That label does not measure personal fitness lost or establish a
  minimum exercise dose. Never add hard training based on the label alone.

## Measured conditions and outcomes (v0.20.0)

- For an outdoor run, intersect each timed **observation** window with its FIT record
  span. Group by source and, for AQI, reporting standard. Require at least 80% of
  elapsed record time for one source. Compute the time-weighted median of its recorded
  values. Retain three or more earlier qualifying pace-, duration- and climb-matched runs
  from that same source and AQI standard. Report the current weather value and moving
  HR next to medians of those same earlier efforts. The AQI value is a median of source
  readings, never converted across standards. Garmin snapshots and modeled observations
  remain contextual.
- For bedroom observations, intersect with the stored sleep start and end. Apply
  the same source and 80% gate separately to temperature, humidity and fine-particle
  concentration. In a trailing 180-day window, split nights by each source's median
  reading, excluding ties at the split. Require 6 distinct nights on each side and a
  recorded span of at least 14 days. Group medians describe observed sleep duration.
  Show the optional morning self-rating (1–5) only with at least four recorded
  ratings on each side. The rating is kept separate from Garmin Body Battery.
- These comparisons can reveal where to look next. Changes in venue, route, exertion,
  sleep timing and health can affect the results. The comparisons leave the training
  plan and recovery score unchanged. Observation coverage gates are engineering choices.
  [Bedroom sensor study](https://pubmed.ncbi.nlm.nih.gov/37474050/) ·
  [Exercise in heat consensus](https://pmc.ncbi.nlm.nih.gov/articles/PMC4602249/)

## Chart color and interpretation (v0.23.0)

- Running-form dots use the existing Garmin population bands from `running.GAUGES`
  for cadence, ground contact time, bounce and vertical ratio. Apply the same
  exclusive upper cutoffs as the existing running-form gauge. They describe how form
  compares with other runners. Compare your own readings at a similar pace.
- Heart-rate colors appear when the activity includes valid increasing FIT band
  bounds. Each point uses the first exclusive upper bound it falls below.
- On Recovery, colors compare each observation with its own historical range. The
  readout states whether it is below, within or above usual. Sleep bars use the current
  sleep goal as the visible comparison. Pace, stride length, elevation and power retain
  their actual units and default colors.
- [Garmin running dynamics bands](https://www8.garmin.com/manuals/webhelp/GUID-C001C335-A8EC-4A41-AB0E-BAC434259F92/EN-US/GUID-EE9E7F6F-49BE-4452-82E6-B40371D0AEC1.html)
  and [Garmin bounce and vertical ratio bands](https://www8.garmin.com/manuals/webhelp/GUID-C001C335-A8EC-4A41-AB0E-BAC434259F92/EN-US/GUID-E2728EFE-C7BC-418E-A31D-D44FD12D1A4C.html).

## Dashboard sleep periods and timing

- A complete night contains at least three recorded hours. Periods are trailing 7, 30, and
  365 wake dates inclusive, with missing nights excluded from averages and left blank on charts.
  Year bars average observed nights by calendar month. Garmin score averages use scored nights only.
  Weekly change needs at least four nights in each of two adjacent seven-day blocks.
- Wake consistency is the population standard deviation of local wake minutes over the last
  14 dates with at least five measured wake times. Unwrap the clock at the largest gap.
  The usual wake time is the median. The weekly plan anchors to the preceding 14 dates at
  the start of the week when enough observations exist.
- The bedtime proposal is a planning heuristic. It steps up to 15 minutes earlier than
  the prior week's median measured sleep onset, stopping at the wake anchor minus sleep need.
  If most measured nights missed the step implied by the previous block, it holds at the recent
  median. It needs at least four nights with onset in the preceding week.
- The shortfall scenario is the ceiling of half the reported seven-night shortfall divided by
  40 extra minutes. This illustrates added time from the existing shortfall estimate.
- Stage totals come from the normalized record. Draw the nightly sequence only from valid Garmin
  Connect intervals within the recorded sleep window. Missing intervals stay blank. Reject
  overlapping intervals. [Garmin stage overview](https://www.garmin.com/en-IE/garmin-technology/health-science/sleep-tracking/)
  · [Connect sleep interval field mapping](https://pkg.go.dev/github.com/abrander/garmin-connect).

## Coaching follow-up and local journal (v0.25)

- Wake follow-up compares the last two complete calendar weeks, each with at least four timed
  nights. Both weeks use the same median wake anchor from the 14 dates preceding the reviewed week,
  with at least five timed readings. Within 30 minutes is counted using circular clock distance.
- The movement floor is the median of the previous 28 dates' recorded steps with at least 14 days.
  A missing day breaks the streak. If today's total is below the floor, the reported streak is
  through yesterday.
- Planned sessions match unique observed workouts of the same date and type, preferring the
  closest duration. If fewer than half the prior planned runs were recorded, suggest repeating
  the week. Otherwise the next suggestion is capped at the lower of planned minutes and 110% of
  completed minutes. Skip adaptation until the previous week has recorded coverage.
- At least 14 paired rested ratings and Garmin scores are required. Compare means for ratings
  1–2 and 4–5 only with at least three in each group. Tags reuse baseline-adjusted next-day
  comparisons with five tagged and 20 comparison days. These are observed associations.
- A knee rating of 4 or more suppresses the following day's running guidance. More restrictive
  rest or pause guidance takes precedence.
- Route replay uses FIT cumulative distance and GPS (55 m maximum separation at sampled points
  250 m apart). Totals agree within 3%, and interpolation spans at most 100 m. Display complete
  one-kilometre elapsed-time sections including stops. GPS coordinates stay out of the HTML.

## Thinking interpretation evidence

The opt-in interpretation reuses the non-overlapping sleep and resting heart rate comparisons,
current and previous seven-day HRV, and the current day's matched run when coverage qualifies.
The numbers and coverage come directly from the existing calculations. Python requires two
or more distinct evidence domains, rejects invalid citations and disallowed text, and displays
the cited readings separately. Model-authored interpretations and a question to check next
undergo a separate review against the cited readings. They never drive the training plan.

Remembered readings come from previously reviewed, deterministic evidence. The prompt can use
up to two readings from the last accepted snapshot within 14 days. The prior snapshot can
overlap current summary windows, so the model treats it as context. At least two current
domains still must be cited.

## Running performance block

- Training rhythm shows 12 completed Monday–Sunday weeks and the current week to date. The two
  scorecards compare the latest four complete calendar weeks with the four before. Garmin run,
  trail, track, treadmill, virtual and ultra entries count. Run days are distinct local dates.
  Distance totals sum finite positive recorded metres. A record without distance still counts as
  a run, the weekly table discloses missing records, and a week with only missing measurements
  has no distance bar. A zero is zero recorded distance, which can include an archive gap.
- The pace-and-pulse plot reviews the most recent 48 outdoor FIT candidates from the block.
  Inclusion requires at least 20 minutes of moving time, minute-speed variation below 15%,
  moving samples covering at least 80% of elapsed time, and usable heart rate on at least 90%
  of moving time. Each point shows FIT moving pace and time-weighted pulse. Terrain and
  conditions can differ across points. Use the matched-run section for like-for-like comparison.
- Half comparisons use equal moving-time windows and at least 90% heart-rate coverage in each
  half. Raw pace uses the same intervals as the pulse reading. The decoupling percentage is
  100 × (first-half grade-adjusted speed per heartbeat − second half) / first half. Positive
  means less adjusted speed per heartbeat later. Block median requires three available readings
  and describes the qualifying sample without an ability score.
- Form notes explain step rate, step length, ground contact, vertical oscillation and the ratio
  of oscillation to step length. Prefer the median and observed minimum–maximum of at least
  three earlier matched runs with that metric. For sparse measurements, use an in-range
  pace regression with at least five earlier readings from the same activity type. The two
  methods have separate labels. Population colours are references. Optional cadence cues use
  a comfortable pace and comfort as the check.
- Kilometre guides use cumulative elapsed time from the full FIT stream's interpolated distance
  crossings, relative to the first recorded sample. The pace, cadence and elevation charts
  share those times even when displayed samples have been thinned. Pauses remain on this clock.
  Distance resets or unavailable crossings suppress guides rather than guessing.
- Training load trend applies exponential smoothing with a 42-day time constant to training
  load points based on recorded duration and effort. A rising line indicates that recently
  recorded sessions are contributing more load. Judge improvement with actual running efforts.
- Sources and decisions are recorded in the [running research](research_notes/Garmin%20connector%20feature%20research/running_performance_2026-11.md).

### Comparing form within a run

For steady outdoor runs, split the moving time into two halves. Require at least 20 moving
minutes and moving coverage of 80% or more of elapsed time. Use adjacent FIT records at most
10 seconds apart, measured pace buckets 15 s/km wide and measured uphill/downhill buckets
2 percentage points wide. Omit missing altitude/distance, distance changes at most 2 m, and
absolute slopes above 12%. Limits are coverage heuristics.

For each recorded metric, keep only buckets with at least 60 seconds in each half. Use each
bucket's shorter recorded duration as its weight in both halves. Show a metric only after
at least 120 matched seconds per half. Use the existing FIT units for cadence, stride length,
ground contact and oscillation. The result describes measured form under similar conditions
within one run. Repeat the observation before attributing it to fatigue or technique.

Split guides use elapsed seconds from the first FIT sample. The individual split table still
measures each recorded kilometre from the first usable distance observation.

### Accepted weekly bedtime targets

Targets apply to nights by local wake date in a Monday–Sunday week. Times are compared on a
noon-to-noon clock so a target after midnight compares correctly to a bedtime before midnight.
Only complete nights with a recorded start count. After at least four timed nights, missing
the target on a majority suggests 15 minutes later. Otherwise the suggestion may move up to
15 minutes earlier, bounded by the wake anchor minus sleep need. Adherence and the outcome
averages are descriptive. A comparison for a metric needs three readings in each group.


## Day readings, sleep shortfall and archive baselines

- **Dated availability.** Malformed and non-finite measurements do not count as readings.
  A missing trend half has no average. Wake times are compared on a circular clock. The
  fixed wake target, sample count, and spread use the same set of complete nights from
  the previous two weeks. Identical readings have zero spread.
- **Awake versus sleep pulse.** Require a valid sleep window and 60 unique, usable awake
  pulse samples from one source. Try Garmin Connect when the Personal API data falls short.
- **Garmin resting estimate.** Personal API `heartRate.restingValue` takes precedence, then
  Connect summary, then the export's `currentDayRestingHeartRate`. The rolling export field
  `restingHeartRate` is excluded from daily RHR during normalization. An older tidy database
  needs a full sync or `python -m garmin_mcp.normalize` to rebuild this mapping from retained raw data.
  Garmin's watch looks for the lowest 30-minute average in 24 h. The independent on-page check
  requests an awake repeat below 50 bpm or outside a personal review range with at least 14
  positive readings in the preceding 28 days. Its center is the median and the radius is the
  larger of 5 bpm and three times 1.4826 × median absolute deviation. These are display
  heuristics. Historical highlights reuse that robust range with floors of 0.5 h sleep,
  1,500 steps and 8 stress points. The latest day omits completed-day comparisons.
- **Intraday pulse.** Use one source per local day. Prefer the source with more measured
  15-minute windows, then the one with the latest sample, then the Personal API. Keep unique
  timestamps in the athlete's local day and retain raw data. Show median, minimum, maximum
  and sample count in each 15-minute slot, with breaks for missing slots. Only windows with
  at least two samples qualify for the highest-median callout. Workout start guides mark
  timing where pulse coverage spans the start and the local time can be aligned.
- **Sleep shortfall.** Sum positive differences between each recorded night of at least
  3 hours and its dated Garmin target, or 8 hours when Garmin did not supply one. Round
  displayed totals and per-night means once. Extra sleep on one night does not erase another
  night's gap. Compare means over two adjacent seven-day windows with at least five usable
  nights each. Tagged but otherwise usable nights count in this descriptive review. The
  readiness model retains its own exclusions. The estimates describe time below target.
- **Sleep trends.** On daily charts the trailing seven-day average needs at least four
  usable readings. The reference band is the observed middle half in the preceding 28 days
  before the displayed window starts and needs 14 readings. For the year, each month
  averages its recorded nights in the displayed window, the trend needs three consecutive
  observed months and the band needs eight plotted months. Duration and Garmin score use
  separate units and coverage.
- **Archive windows.** In Week History and the resting pulse check, the short, medium and long
  windows are 28 days, 90 days and all earlier retained health dates. Each ends the day before
  the displayed date. Each usable date contributes one value per metric. Windows with at least
  14 readings show the median and middle-half observed interval (sorted zero-based indices
  `n//4` and `(n−1)*3//4`). Dates with missing or invalid observations count as gaps. Sparse
  windows include the missing date ranges and do not display a numeric baseline. See
  [Garmin sources and independent research](docs/GARMIN_DATA_REVIEW.md).

## Daily distance

`daily.distance_m` is walking and running distance in metres. The Personal API reports it as step
distance. The export and Connect summaries use `wellnessDistanceMeters`, falling back to
`totalDistanceMeters` only when it is absent. Before v0.32.1 the export used the total, which also
counts rides and swims. Rides and swims keep their own distance on each activity.

## Intraday Stress and Body Battery

Connect stores epoch-millisecond Stress and Body Battery entries in the daily stress response.
Garmin files each reading under the **watch's** local date. When a stored day records a different
UTC offset (travel), the day filter and the clock labels use that offset; otherwise they use the
configured timezone. The same applies to the intraday pulse chart.
Both `--source both` (default) and `--source garminconnect` download it. Before v0.32.1 the
default mode skipped it, so those archives have no intraday timeline for earlier days until a
forced sync covers them.
Use the configured local timezone, accept Stress 0–100 and Body Battery 5–100, and keep
the first usable value at a duplicate timestamp. For each 15-minute window, Stress shows
the median plus the recorded low and high. The peak summary needs at least two readings
in that window. Body Battery shows the last recorded value in each window with its first
and last observed reading as context. Those endpoints may cover only part of the day.
The plotted full-day axis allows side-by-side comparison, and absent windows break lines.
The metrics share physiological inputs and the chart supports time comparison without
inferring causality, duration at a value or a recovery recommendation. Garmin Personal
API series require their own confirmed mapping. [Source evidence](docs/GARMIN_ECOSYSTEM_REVIEW.md#implementation-evidence)

## Interpreting running form and kilometre bars

- The split chart uses the median duration of the full recorded kilometres from the
  same run. Each bar is elapsed seconds minus that median, with positive above zero
  and negative below. Pauses count in the elapsed duration. The timing summary retains
  its original equal-distance comparison. The chart formatter rounds plot labels
  to whole seconds and shows tenths in the list and cursor readout.
- Garmin population bands, workout heart-rate zone cutoffs, and the observed range
  across matched prior runs answer different questions. The dashboard shows which
  comparison is in use. Upper cutoffs are exclusive in the continuous chart.
  Bounce and vertical ratio use the published chest bands as a labelled reference.
  The manufacturer documents different ranges by placement. A compatible accessory
  is needed for left/right ground contact balance on the FR955.
- [Running guide data](src/garmin_mcp/running.py) drives the dashboard and MCP glossary.
  For a change in vertical ratio, inspect bounce and step length independently.
  The device metric alone cannot establish running economy. Compare pace, grade,
  surface, sensor and comfort. Small matched-pace cadence experiments have measured
  acute biomechanics outcomes, which are distinct from a universal step-rate goal.
  [Garmin FR955 running dynamics](https://www8.garmin.com/manuals/webhelp/GUID-9D99A9D4-467A-4F1A-A0EA-023184FEA3DD/EN-US/GUID-62A09512-518A-424A-8491-FE2B80CD2091.html)
  · [Heiderscheit et al.](https://pubmed.ncbi.nlm.nih.gov/20581720/)

## Dated inputs, naps and Body Battery review

Today's availability checks the expected local date independently of the dated snapshot.
It marks an absent reading as pending when a current complete sync is missing or a sync
must retry. This is a sync state rather than proof the watch has a reading. Prior archived
measurements retain their last observed date. An incomplete night remains separate.
The readiness method and its minimum input count are unchanged.

Nap coverage reads only explicit `napTimeSeconds` from dated original Garmin sleep summaries.
Use the established source priority. A missing field stays unknown and an explicit zero
counts as a dated observation. Nap totals are separate from overnight sleep and schedule
recommendations. [Garmin nap tracking](https://support.garmin.com/en-US/?faq=2icqqZFq3YAX5K9VGU2CQ9)
· [Dated nap field](https://github.com/abrander/garmin-connect/blob/master/SleepSummary.go)

Body Battery charge and drain are Garmin's recorded daily point totals, with medians over the
28 dates before the snapshot. Split charge on whether overnight sleep met an explicit Garmin
target. Split drain on recorded run presence and, separately, explicit positive versus zero
nap totals. Each arm needs at least four paired dates. These are descriptive calendar-day
comparisons. No timing within a day or effect of a run or nap is inferred.
