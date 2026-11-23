# Running form benchmarks (FR955)

Key: **[R]** = I read the URL this session. **[S]** = seen only in a search snippet. **[U]** = from memory or my own inference; not verified.

## 1. Garmin running dynamics colour gauges

Source [R]: the Garmin webhelp topics `GUID-EE9E7F6F…` (colour gauges), `GUID-E2728EFE…` (VO/VR) and `GUID-B917540E…` (GCT balance) under
https://www8.garmin.com/manuals/webhelp/GUID-C001C335-A8EC-4A41-AB0E-BAC434259F92/EN-US/ (the fēnix 7 manual, v12, Aug 2025).
- **Caveat:** I could not reach an FR955-branded copy. Garmin reuses the same topic GUIDs across manuals. The FR745, FR170, MARQ and Enduro versions carry the same tables, and the manualowl FR955 p.85 snippet has the same intro text [S].
- Garmin's description of the zones: they are based on percentiles. Red and orange are typical of less experienced or slower runners; green, blue and purple of more experienced or faster runners.
- Taller runners tend to have a slightly lower cadence and slightly higher VO.
- VR = VO / stride length, and is "not correlated with height".

| Colour | Percentile | Cadence (spm) | GCT (ms) | VO chest (cm) | VO waist (cm) | VR chest (%) | VR waist (%) |
|---|---|---|---|---|---|---|---|
| Purple | >95 | >183 | <218 | <6.4 | <6.8 | <6.1 | <6.5 |
| Blue | 70–95 | 174–183 | 218–248 | 6.4–8.1 | 6.8–8.9 | 6.1–7.4 | 6.5–8.3 |
| Green | 30–69 | 164–173 | 249–277 | 8.2–9.7 | 9.0–10.9 | 7.5–8.6 | 8.4–10.0 |
| Orange | 5–29 | 153–163 | 278–308 | 9.8–11.5 | 11.0–13.0 | 8.7–10.1 | 10.1–11.9 |
| Red | <5 | <153 | >308 | >11.5 | >13.0 | >10.1 | >11.9 |

"Chest" means an HRM-Fit or HRM-Pro strap; "waist" means the Running Dynamics Pod. The manual has no wrist-only table. **Recommendation:** use the chest columns for wrist data and flag them as approximate [U].

**GCT balance** (strap only). The colour scale is symmetric around 50/50:

| Zone | Red | Orange | Green | Orange | Red |
|---|---|---|---|---|---|
| Share of runners | 5% | 25% | 40% | 25% | 5% |
| GCT balance | >52.2% L | 50.8–52.2% L | 50.7% L – 50.7% R | 50.8–52.2% R | >52.2% R |

Garmin also notes that GCT balance drifts further from 50/50 on hills.

## 2. Runalyze "Marathon shape" (source code)

Source [R]: a shallow clone of https://github.com/Runalyze/Runalyze (master branch). The relevant files are:
- `inc/core/Sports/Running/MarathonShape.php`
- `inc/core/Calculation/BasicEndurance.php`
- `src/CoreBundle/Component/Configuration/Category/BasicEndurance.php`
- `inc/core/Sports/Running/Prognosis/VO2max.php`

**Defaults** (from the config class):

| Parameter | Value |
|---|---|
| `BE_MIN_KM_FOR_LONGJOG` | 13 km. The test is strict: distance > 13. |
| `BE_DAYS_FOR_LONGJOGS` | 70 |
| `BE_DAYS_FOR_WEEK_KM` | 182 |
| `BE_DAYS_FOR_WEEK_KM_MIN` | 70. The window is `max(min(182, days_since_first_activity), 70)`. |
| `BE_PERCENTAGE_WEEK_KM` | 0.67. Long runs get 1 − 0.67 = 0.33. |
| Effective VO2max floor | 25.0 |

**Formulas** (V = max(effective VO2max, 25)):

```
target_week_km        = V ** 1.135
target_longrun_km     = ln(V/4) * 12                 # "LongJogEachWeek"; the code subtracts 13 to get the excess target
longrun_points(run)   = (2 - 2/70 * floor(days_ago)) * ((dist_km - 13) / (ln(V/4)*12 - 13))**2   # only runs >13 km in the last 70 days
weekly_pct            = sum_km(window) * 7 / window_days / target_week_km
longrun_pct           = sum(longrun_points) * 7 / 70
shape_%               = round(100 * (0.67*weekly_pct + 0.33*longrun_pct))   # not capped; the UI clamps it to 0–100
```

- Each long run's weight falls linearly from 2 (today) to roughly 0 (70 days ago).
- Example targets: V=40 gives 65.8 km/week and a 27.6 km long run. V=50 gives 84.8 and 30.3. V=60 gives 104.3 and 32.5.

**Race-shape requirement and prognosis adjustment** (`Prognosis/VO2max.php`):

```
required_shape(d_km) = d_km ** 1.23
factor = min(1, 0.6 + 0.4 * max(0, 1 - (required_shape - shape)/100))
adjusted_VO2max = V * factor
```

The required shape works out as: 5K 7.2%, 10K 17.0%, HM 42.5%, M 99.8%. These match the commonly quoted 7/17/43/100 figures. The adjustment factor bottoms out at 0.6.

## 3. Running effectiveness (RE)

| Item | Value |
|---|---|
| Definition | RE = speed (m/s) / (power W / mass kg). It is dimensionless in practice. Source: Palladino, https://www.trainingpeaks.com/blog/running-effectiveness-versus-speed-using-wko4/ [R]. It is attributed to the WKO4/Coggan work. I could not confirm a Snyder attribution [U]. |
| Inverse metric | Stryd ECOR = power / speed, in kJ/kg/km. Stryd's blog example is 0.98 [S]. |
| Typical values | About 0.95–1.05 for Stryd power; around 1.00 is common, and >1.05 is uncommon [U, from memory]. RE tends to rise slightly with speed (Palladino [R]). |
| Garmin wrist caveat | [U] Garmin native running power has a different model and absolute scale from Stryd: it includes wind and runs roughly 10–30% higher. Stryd RE benchmarks therefore do not transfer. Track RE only as a within-athlete trend on one device and one mass setting, on flat ground at steady pace. The mass setting must match between device and software (Stryd blog [S]). |

## 4. Cadence and knee loading (PubMed abstracts [R], via eutils efetch)

| Study | Design | Key numbers |
|---|---|---|
| Heiderscheit 2011, MSSE 43:296, PMID 20581720 | 45 recreational runners; preferred, ±5% and ±10% step rate | Knee energy absorption fell at both +5% and +10% (P<0.01); hip energy absorption fell only at +10%. At −10% all joints absorbed more. Step length, COM vertical excursion, braking impulse and peak knee flexion all fell as step rate rose. At +10%, peak hip adduction angle and the adduction/internal-rotation moments also fell. The abstract gives no % magnitudes; I could not open the full text (PMC3022995). |
| Lenhart 2014, MSSE 46:557, PMID 23917470 | 30 runners at 90, 100 and 110% step rate | At +10%, **peak patellofemoral joint force fell 14%**. Reduced peak knee flexion was the best predictor. |
| Willy 2016, J Sports Sci 34:1602, PMID 26679058 | RCT, n=30; +7.5% step rate with watch biofeedback over 8 runs | Per-step total tibiofemoral peak force fell **7.6%** and impulse fell **10.6%**. In the medial compartment, peak fell **8.2%** and impulse **10.6%**. The reductions held at 1 month. **Cumulative load per km was unchanged**, because there are more steps. Knee adduction moment did not change. |

**Takeaway:** about +5–10% cadence lowers per-step knee and patellofemoral load. It does not lower load per km (Willy). That makes cadence a lever for injury rehabilitation, not a performance metric.

## 5. VO, VR, GCT and running economy (PubMed abstracts [R])

| Study | Finding |
|---|---|
| Moore 2016, Sports Med 46:793, PMID 26816209 (review) | Factors that favour running economy: self-selected stride length (economy tolerates up to 3% shorter than preferred); **lower vertical oscillation**; greater leg stiffness; less leg extension at toe-off; maintained arm swing; lightweight shoes. Many other factors were inconsistent. The review cautions against prescribing a single "economical technique". |
| Folland 2017, MSSE 49:1412, PMID 28263283 | 97 runners at 10–12 km/h. **Pelvis VO during contact (normalised to height), minimum knee angle in stance and minimum horizontal pelvis velocity together explained 39%** of the variance in energy cost. Minimum horizontal pelvis velocity, shank touchdown angle, **duty factor (a GCT proxy)** and trunk lean explained 31% of the variance in performance. |
| Snyder & Farley 2011, JEB, PMID 21613526 | Metabolic cost against stride frequency is U-shaped, and runners self-select a frequency near the optimum on level, uphill and downhill. Forcing a cadence away from preferred is not "free". |

**What is modifiable:** cadence/stride length (small changes only), VO, and possibly GCT through strength/plyometric work and leg stiffness [U]. All of these depend heavily on speed, so compare them only at matched pace.

## 6. How analytics apps handle form over time ([U] unless marked)

| App | Approach |
|---|---|
| Garmin Connect | Per-run averages are colour-coded with the percentile table above. There is no pace normalisation. |
| Runalyze | Charts running dynamics against pace or HR, per activity and over time. Marathon shape is computed as in §2 [R]. |
| Stryd PowerCenter | Tracks RE/ECOR, form power ratio (form power / total power), LSS, GCT and VO, usually at matched power or pace. |
| intervals.icu | Can plot any FIT stream, including cadence, GCT, VO, efficiency factor and power/HR, against pace over time. It supports custom fields and charts. |
| WKO (Palladino) | Plots RE against speed and analyses the slope [R]. |

**Recommendation for this project:**
1. Per run, take steady-state segments (pace CV <5%, grade ±1%). Fit cadence, GCT, VO and VR against speed per athlete, as a linear regression over a rolling 90 days.
2. Report each metric's residual at a reference pace, for example easy pace or 5:00/km. That shows drift in form independent of pace.
3. Flag changes greater than the 2×SD of the residuals.
4. Report GCT balance only when a strap is present.

### Applied in v0.18.0

The optional one-minute trial uses +5% of the athlete’s measured cadence at the same
comfortable easy pace, with an explicit knee note and adequate cadence coverage.
Heiderscheit et al. studied 45 recreational runners at constant speed and found lower
knee energy absorption per step at +5% and +10%. Lenhart measured per-step joint forces.
Willy provides an important limit: cumulative load per kilometre did not decline.
The dashboard asks the runner to note comfort later that day and the next morning.
The one-minute duration and 80% sample gate are product rules. The research does not
establish how this trial affects the owner’s pain or injury risk.
[Heiderscheit full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC3022995/) ·
[Lenhart](https://pubmed.ncbi.nlm.nih.gov/23917470/) ·
[Willy](https://pubmed.ncbi.nlm.nih.gov/26679058/)
