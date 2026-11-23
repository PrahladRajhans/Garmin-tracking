# Running & sport metrics research (FR955, wrist-only)

Status key: **[V]** checked against primary source (FIT SDK Profile / paper) from memory of the source text; **[U]** unverified this session, re-check before coding. No live web fetches were done for this note, so treat every constant as [U] until a unit test pins it against the cited source.

---

## 1. Running metrics (FR955, no strap)

FR955 wrist running dynamics: since 2022 firmware, cadence, stride length, GCT, VO and VR come from the wrist accelerometer (no HRM-Pro/RDP needed for most of them; GCT balance still needs a strap). Wrist power is native. **[U]: confirm the field list on a real FIT export; some devices only write GCT/VO with a pod.**

### 1a. FIT storage (record message; Garmin FIT SDK Profile.xlsx)

| Field | FIT type | Scale | Stored unit | Convert |
|---|---|---|---|---|
| enhanced_speed | uint32 | 1000 | m/s | pace s/km = 1000/v |
| heart_rate | uint8 | 1 | bpm | |
| cadence | uint8 | 1 | rpm (**one foot**, strides/min) | spm = 2·(cadence + fractional_cadence) |
| fractional_cadence | uint8 | 128 | rpm | |
| step_length | uint16 | 10 | mm (0.1 mm resolution) | m = raw/10/1000 |
| stance_time (GCT) | uint16 | 10 | ms | |
| stance_time_percent | uint16 | 100 | % | |
| stance_time_balance | uint16 | 100 | % (strap only) | |
| vertical_oscillation | uint16 | 10 | mm | |
| vertical_ratio | uint16 | 100 | % | |
| power | uint16 | 1 | W | |
| enhanced_altitude | uint32 | 5, offset 500 | m | |
| session: avg_running_cadence | uint8 | 1 | strides/min | ×2 |
| session: total_training_effect / total_anaerobic_training_effect | uint8 | 10 | 0–5.0 | |

fitparse/garmin-fit-sdk decoders apply scale automatically; raw readers must divide. **[V for scales of cadence/fractional/step_length/stance_time/VO/VR/enhanced_speed; U for step_length presence on wrist-only]**

### 1b. Metric table

| Metric | Definition | Typical recreational | Speed-dependent? | Tells you / interactions | Evidence & coaching |
|---|---|---|---|---|---|
| Pace / speed | GPS (+accel) distance/time | easy 5:30–7:00 /km | — | v = cadence(spm)/60 × stride(m) | Base for everything; use GAP/power on hills |
| HR | Optical PPG bpm | easy 65–78 % HRmax | yes (with drift) | Cardiac drift at constant pace → decoupling, EF | Optical lags 10–20 s at transitions; ignore first 5–10 min for drift |
| Cadence | steps/min (stored as stride rpm ×2) | 155–175 spm easy; 170–190 fast | **yes**, rises with speed | Main lever with stride; up cadence → down stride, VO, GCT, braking | Heiderscheit 2011 MSSE 43:296: +5–10 % cadence ↓ hip/knee load (+10 % ↓ knee energy absorption ~34 %). Tip: small +5 % steps; compare at matched pace; "180" is not universal |
| Stride/step length | distance per step (Garmin "stride length" = one step) | 0.9–1.2 m easy | **yes** | stride = v / (cadence/60) | Overstriding = long stride + low cadence; check footstrike isn't trend metric |
| GCT | foot-on-ground time per step | 220–300 ms | **yes**, ↓ with speed | Shorter at faster pace; fatigue ↑ GCT | Moore 2016 Sports Med review: economy links weak/mixed. Use as fatigue marker within-run |
| Vertical oscillation | torso bounce per step | 6–10 cm | weakly | Higher VO = more vertical work | Moore 2016: lower VO modestly associated with better economy |
| Vertical ratio | VO / step length ×100 | 6–10 % (lower better) | partly normalised | Efficiency proxy; combines VO and stride | Garmin colour bands roughly <6.1 excellent, >10.1 poor **[U]** |
| Running power (wrist) | Garmin model W incl. wind (from 2022/FR955, uses phone/barometric + speed) | ~2.8–4.0 W/kg easy | yes, grade/wind-aware | Power vs pace diverges on hills/wind; power/HR = alt EF | Not comparable to Stryd absolute values; within-device trends only |
| Training effect (aero/anaero) | Firstbeat EPOC-based 0–5.0 | 2–3 easy, 3–4 tempo, 4+ hard | — | Classifies session benefit | Firstbeat white paper "EPOC-based training effect" **[U]** |
| VO2max | Firstbeat speed-HR relation in steady segments | 40–55 ml/kg/min | — | Should track our VDOT (§5) | Firstbeat white paper on VO2max estimation, reported ~5 % error vs lab **[U]** |
| Performance condition | Real-time deviation from VO2max at 6–20 min, ±1 pt ≈ 1 % VO2max | −5…+5 | — | Daily readiness in-run | Garmin manual **[U]** |
| Stamina | Real-time potential/current stamina % (FR955+) | — | — | Depletion model from VO2max, LT, load | Garmin manual; algorithm proprietary |

Interactions to compute: v = f·L; VR = VO/L; GCT ∝ 1/v; aerobic decoupling (§2); EF (§2); power-HR ratio. **Always compare dynamics at matched pace bins (e.g. ±10 s/km) or regress on speed and track residuals.**

---

## 2. Phase 4 formula verification

| Item | Exact formula | Source | Notes / blog discrepancies |
|---|---|---|---|
| Banister TRIMP | TRIMP = D(min) · ΔHR · 0.64·e^(1.92·ΔHR) (men); 0.86·e^(1.67·ΔHR) (women); ΔHR = (HRex−HRrest)/(HRmax−HRrest) | Banister 1991 in *Physiological Testing of Elite Athletes*; Morton, Fitz-Clarke & Banister 1990 J Appl Physiol 69:1171 | Constants match common blogs. Some blogs drop the leading ΔHR term (wrong). Compute per sample (1 s) and sum, not on mean HR. [U for exact page] |
| Edwards TRIMP | Σ minutes in zone × weight; zones 50–60/60–70/70–80/80–90/90–100 % HRmax → 1/2/3/4/5 | Edwards 1993 *The Heart Rate Monitor Book* | Uses % HRmax, not HRR |
| CTL/ATL | EWMA. TrainingPeaks form: X_t = X_{t−1} + (L_t − X_{t−1})/N, N=42 (CTL), 7 (ATL). Exp form: λ=1−e^(−1/N) | Coggan/TrainingPeaks; Banister impulse-response | 1/N vs 1−e^(−1/N): 1/42=0.0238 vs 0.0235; 1/7=0.1429 vs 0.1331 (≈7 % difference on ATL). **Pick one and document; intervals.icu uses exp, TP uses 1/N [U].** Seed CTL with first 6 weeks mean |
| TSB | TSB_t = CTL_{t−1} − ATL_{t−1} (TP uses yesterday's values) | TrainingPeaks | Many blogs use same-day; off by one day |
| Ramp rate | CTL_t − CTL_{t−7} per week | TrainingPeaks | Heuristic: >5–8 /wk risky [U] |
| Monotony / strain | Monotony = mean(daily load, 7 d) / SD(daily load, 7 d), rest days = 0; Strain = weekly sum × monotony | Foster 1998 MSSE 30:1164 | >2.0 monotony flagged in Foster. Population vs sample SD unspecified; use population [U] |
| rTSS | rTSS = (t_s · NGP · IF)/(FTPace · 3600) ×100, IF = NGP/FTPace; equivalently hours × IF² × 100 | TrainingPeaks help docs | With pace, use speeds (m/s), not s/km |
| NGP | Grade-adjusted speed, then 30-s rolling, 4th power mean, 4th root (TP proprietary grade model) | TrainingPeaks | Exact grade cost curve proprietary; use Minetti 2002 J Appl Physiol 93:1039 cost polynomial as substitute: C(i)=155.4i⁵−30.4i⁴−43.3i³+46.3i²+19.5i+3.6 J/kg/m |
| hrTSS | hours × (HR-based IF)² ×100 using LTHR; TP uses TRIMP mapping | TP | Prefer TRIMP-scaled so 1 h at LTHR = 100 |
| Daniels–Gilbert VDOT | VO2(v) = −4.60 + 0.182258·v + 0.000104·v² (v m/min); %max(t) = 0.8 + 0.1894393·e^(−0.012778·t) + 0.2989558·e^(−0.1932605·t) (t min); VDOT = VO2/%max | Daniels & Gilbert 1979 *Oxygen Power* | Matches common implementations. Race predict by solving for t numerically |
| Riegel | T2 = T1·(D2/D1)^1.06 | Riegel 1981 American Scientist 69:285 | 1.06 is the athletic-population fit; recreational marathoners often ~1.07–1.10 (fatigue). Valid ~3.5 min–4 h |
| Critical speed | D = CS·t + D′ (linear distance–time), fit 2–4 efforts of 2–15 min | Monod & Scherrer 1965; Hill 1993; Jones & Vanhatalo 2017 Sports Med | CS ≈ ~LT2/MLSS; D′ typical 100–300 m. Our data: use best efforts from pace curve, 3–12 min |
| Seiler 3-zone | Z1 < LT1 (~2 mmol, VT1), Z2 LT1–LT2, Z3 > LT2 (~4 mmol, VT2) | Seiler & Kjerland 2006 SJMSS; Seiler 2010 IJSPP | HR proxy: Z1 < ~82 % HRmax, Z3 > ~87–90 % [U]; better anchor to Garmin LTHR |
| Polarization index | PI = log10( (Z1/Z2) · Z3 · 100 ), Z as fractions of total; PI > 2.0 = polarized; only defined if Z1>Z3>Z2 (else not polarized). If Z2=0 set Z2=0.01 | Treff et al. 2019 Front Physiol 10:707 | Blogs often omit the ×100 or condition |
| Efficiency factor | EF = NGP(m/min or m/s)/avg HR (or avg power/avg HR) | Friel / TrainingPeaks | Track in steady easy runs only |
| Pa:HR decoupling | Dec % = [(Pace₁/HR₁) − (Pace₂/HR₂)]/(Pace₁/HR₁) ×100, halves of the steady part, pace as speed | Friel, TP "Aerobic decoupling" | <5 % = good aerobic endurance (heuristic, not peer-reviewed) |
| LTHR (Friel) | Avg HR of last 20 min of a 30-min solo all-out run | Friel *Training Bible* | Data proxy: best rolling-20 min HR inside ≥30 min hard efforts; Garmin also writes LTHR |
| HRmax from data | 98th–99.5th percentile of 1-s HR in hard sessions over 90 d, artefact-filtered | practice | Tanaka 2001 JACC: 208 − 0.7·age as fallback (better than 220−age) |
| Karvonen | THR = HRrest + %·(HRmax − HRrest) | Karvonen 1957 Ann Med Exp Biol Fenn | Use Garmin overnight RHR |

---

## 3. Other sports from FIT

**Swimming (pool)**: `length` messages: length_type (active/idle), total_elapsed_time, total_strokes, swim_stroke (enum 0 freestyle,1 backstroke,2 breaststroke,3 butterfly,4 drill,5 mixed,6 IM), avg_swimming_cadence (strokes/min). `session`: pool_length (scale 100, m), num_active_lengths, avg_stroke_distance. SWOLF = length time (s) + strokes per length (Garmin computes per length; pool-length dependent). Pace/100 m = time/(lengths·pool_length)×100. Open water: GPS distance, strokes, no lengths.
Insights: SWOLF trend at matched pace & stroke; strokes/length (DPS) vs pace; CSS (critical swim speed = (400−200)/(t400−t200)); rest:work ratio; stroke mix.

**Strength**: `set` messages: set_type (active/rest), duration, repetitions, weight (scale 16, kg), category (exercise_category enum, e.g. bench_press, squat, deadlift, lunge, plank, …~30 categories), category_subtype, wkt_step_index. Rep counts from accelerometer often wrong; weight only if user enters it.
Insights: volume load = Σ reps×weight per category/muscle group; weekly frequency; est. 1RM (Epley: w·(1+reps/30)); strength days vs next-day run quality/HRV; HR-based load small vs running.

**Walking/hiking**: speed, cadence, ascent/descent, grade; insights: vertical metres/week, GAP, low-intensity volume that counts toward Z1 & total load but not run-specific load.

---

## 4. AI insight products (as of late 2026, [U] details)

| Product | Output | Replicable? |
|---|---|---|
| Garmin Connect+ "Active Intelligence" (launched Mar 2025, subscription) | Short text insights on activities, sleep, training status trends; morning report personalisation; "insights" cards | Yes: our metrics + Claude narration. Garmin's version is shallow summaries |
| Strava "Athlete Intelligence" (beta 2024, GA 2025) | Per-activity text summary: effort vs history, pace/HR/elevation comparisons, PRs, relative effort trend | Yes: needs our per-activity percentile vs 90-day history, segment-like best efforts |
| Both | Not coaching plans (Garmin Coach separate) | Later phase: Claude-written weekly review: load (CTL/ATL/TSB), PI, decoupling trend, dynamics drift, readiness link |

---

## 5. Sense-check list (ours vs Garmin)

| Our metric | Garmin counterpart | Expected relation | Tolerance / flag |
|---|---|---|---|
| ATL (TRIMP, 7 d EWMA) | Acute load (7-d EPOC-weighted) | Pearson r > 0.8 over 90 d; scale differs | r < 0.7 → check HR artefacts / zones |
| CTL / ACWR | Load ratio / training status | ATL/CTL ≈ Garmin load ratio trend | Directional agreement |
| VDOT from recent races / best efforts | VO2max (running) | VDOT ≈ VO2max ± 3 units; trends same sign | >5 units gap → check race effort / heat |
| Riegel / VDOT race predictions | Garmin race predictor | Within ±3 % 5K–HM; marathon Garmin often optimistic | >5 % → note |
| Time in HR zones | session `time_in_hr_zone` / hr_zones | Same zone boundaries ⇒ ±2 % per zone | Mismatch → boundaries differ |
| LTHR from 20-min best | Garmin LT HR (user_profile/lactate threshold) | ±3 bpm | ±5 bpm flag |
| HRmax percentile | user profile max HR | ±3 bpm | |
| TRIMP per run | Training load (EPOC) per run | Rank corr r > 0.8 | |
| Our 3-zone distribution | Garmin load focus (low aerobic / high aerobic / anaerobic) | Same ordering | |
| Cadence/stride recomputed v = f·L | enhanced_speed | Within ±3 % per lap | Larger → GPS/accel issues |
