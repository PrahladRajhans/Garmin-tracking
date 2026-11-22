# Garmin-derived insights: reference (FR955, Nov 2026)

Sources: fr955_metrics.md and metric_formulas.md (citations live there). `[bg]` = background knowledge that was not re-verified this session. Algorithms are Firstbeat Analytics (owned by Garmin) unless stated otherwise. **None publish weights or full formulas.** "Open equivalent" = what we can compute ourselves from FIT and daily data.

Legend for "Pub?": Y = formula published; P = concept/inputs published; N = opaque.

| Insight | Inputs | How calculated (Pub?) | Output / labels | FR955 | Open equivalent we can compute |
|---|---|---|---|---|---|
| Training Readiness | Sleep score, sleep history, recovery time, HRV status, acute load, stress history | Weighted composite (P, no weights) | 0–100; Poor / Low / Moderate / High / Prime [bg] | Yes (launch) | Z-score composite of ln RMSSD, inverted RHR, sleep h, TSB/ATL. Show components (metric_formulas §Readiness) |
| Training Status | VO2max trend, acute load, load balance, HRV status (since 2022) | Rule matrix on VO2max trend × load (P) | Productive, Maintaining, Peaking, Recovery, Unproductive, Detraining, Strained, Overreaching, No Status | Yes | CTL ramp + eVO2max/CS trend + HRV band. Rule table of our own |
| HRV Status | Overnight RMSSD | 7-day mean vs personal baseline band; ~3 wk to activate (P) | ms; Balanced / Unbalanced / Low / Poor | Yes | ln RMSSD 7d roll vs 60d mean ± 0.5 SD (Plews/HRV4Training) |
| Body Battery | HRV-derived stress/relaxation, activity, sleep | Energy reservoir drained by stress/activity, charged by rest (P) | 5–100 | Yes | No standard. Proxy: cumulative recovery/strain balance from all-day HR/HRV. Low priority |
| Stress | All-day HRV + HR (only while still) | Firstbeat autonomic stress index (N) | 0–100; Rest 0–25, Low 26–50, Medium 51–75, High 76–100 [bg] | Yes | Per-minute HR above RHR / RMSSD-derived; Baevsky stress index (needs RR) |
| Sleep Score | Duration, stages, restlessness, stress during sleep, HRV [bg] | Weighted score (P) | 0–100; Excellent ≥90, Good 80–89, Fair 60–79, Poor <60 [bg] | Yes | Store Garmin's stages. Our score = duration vs need + efficiency + regularity (SRI) |
| Sleep Coach / Sleep need | Sleep history, load, HRV, naps [bg] | Need = baseline + adjustments (N) | Hours | Yes [bg] | Rolling baseline sleep + debt (Σ need − actual) |
| Acute Load | EPOC per activity | 7-day weighted EPOC sum (P) | Number + optimal range band | Yes | ATL from TRIMP/rTSS (7-day EWMA) |
| Load Focus | EPOC split by intensity class | 4-wk buckets vs targets (P) | Low aerobic / High aerobic / Anaerobic; shortage/balanced | Yes | Seiler 3-zone time-in-zone + polarization index |
| Training Effect (aerobic/anaerobic) + primary benefit | HR→%VO2max, EPOC, high-intensity bursts | EPOC mapped to fitness level (P; Firstbeat white paper) | 0–5 each; labels Recovery/Base/Tempo/Threshold/VO2max/Anaerobic/Sprint | Yes | TRIMP/rTSS per session relative to CTL. Zone-based session classification |
| Recovery Time | EPOC, TE, sleep, stress, HRV | Countdown (N) | 0–96 h [bg] | Yes | TSB-based "fresh" estimate. Session load ÷ CTL heuristic |
| VO2max (run, cycle) | HR vs speed (or power) segments; heat/altitude correction | Firstbeat HR–speed regression (P; ~5% MAPE) | ml/kg/min + age/sex percentile | Run yes; cycle with a power meter | Runalyze-style effective VO2max (VDOT from HR-adjusted pace); Cooper/VDOT from race results |
| Race Predictor | VO2max, training history (newer: long-run volume) | Proprietary (N) | 5K/10K/HM/M times | Yes (updated model) | Riegel (exp ~1.06, individualised), VDOT, critical speed |
| Endurance Score | VO2max + acute/chronic load across sports | Composite (P) | Number; Recreational → Elite (6 tiers) [bg] | Yes (fw 2023 Q3) | CTL + long-session share + eVO2max. No standard |
| Hill Score | VO2max, history on climbs (strength + endurance) | Composite (P) | 1–100; Recreational → Elite [bg] | Yes (fw 2023 Q3) | GAP-adjusted climb power/pace curve (Minetti); best VAM |
| Lactate Threshold | HR + pace (+ HRV) during a guided test/auto-detect | Firstbeat HRV/HR breakpoint (N) | LTHR bpm, LT pace (+ power) | Yes; chest strap historically required (unclear now) | Critical speed/power from best efforts; 30-min TT avg HR (Friel LTHR); HRV DFA-α1=0.75 (needs RR, neurokit2) |
| Heat acclimation | Temp/humidity of runs, HR response | Proprietary (N) | 0–100 % | Yes | Count of hot sessions in last 14 d plus HR-at-pace drift vs temperature |
| Altitude acclimation | Altitude exposure, SpO2 [bg] | Proprietary (N) | 0–100 % | Yes | Days above X m; SpO2 trend |
| Performance Condition | Real-time HR vs pace vs VO2max | Deviation of current fitness (N) | −20…+20 after 6–20 min | Yes | Efficiency factor (NGP/HR) vs 30-d baseline at the same point in the run |
| Real-Time Stamina | VO2max, LT, Body Battery?, current effort | Energy model (N) | Potential/current %; remaining distance/time | Yes | W′bal (Skiba) on run power or speed above CS |
| Running Power (wrist) | Pace, grade, wind/accel, body mass | Garmin model (N); includes wind | W; power zones | Yes, native (HRM-Pro improves it) | Store Garmin's W. Note it's not comparable to Stryd. Can compute CP and RSS-like load |
| Intensity Minutes | HR zones / accel | Moderate ×1, Vigorous ×2 (Y, WHO-based) | Min/week vs 150 goal | Yes | Recompute from HR stream (≥ moderate zone), identical rule |
| Fitness Age | VO2max, RHR, BMI/body fat, vigorous minutes | Norm tables (P) | Years | Yes | VO2max vs age norms (e.g. HUNT/Nes 2013 formula) [bg] |
| Respiration, Pulse Ox, RHR (raw-ish) | Optical sensor | Measured | brpm, %, bpm | Yes | Store raw; baselines and anomaly z-scores |
| Morning Report | Sleep, HRV, readiness, weather, plan | Aggregation | Text card | Yes | MCP "daily brief" tool |
| Not on FR955 | Skin temp, ECG, Training Readiness 2.0 extras, Hill/Endurance on older | n/a | n/a | No (FR970) | n/a |

## Implementation notes
- Store Garmin's values **and** their components (e.g. the readiness sub-scores in python-garminconnect `get_training_readiness`). Never blend Garmin's EPOC load with our TSS in one series.
- Garmin numbers are the "reference truth" for the user. Our open equivalents are for transparency, history recompute and what-if analysis.
- The minimum inputs to store for all of the open equivalents: FIT 1 s streams (HR, speed, power, altitude, temp), nightly RMSSD, RHR, sleep stages/duration, dated thresholds (RHR, HRmax, LTHR, CS/threshold pace).
