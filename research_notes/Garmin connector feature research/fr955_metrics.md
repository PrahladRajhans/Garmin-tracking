# Garmin Forerunner 955 / 955 Solar: Metrics Catalogue (as of Nov 2026)

Research note: from this session, WebFetch could not reach garmin.com, dcrainmaker.com or the5krunner.com (DNS blocked). Findings come from search-result summaries of those pages plus other sources. Anything marked "(unverified)" is background knowledge with no source retrieved here; treat it as a lead and check it.

## Daily health metrics (steps, intensity minutes, HR, HRV status, stress, Body Battery, respiration, SpO2, sleep, skin temp, hydration, women's health)

### Takeaway
The FR955 has the full Garmin/Firstbeat 2022-generation health suite: all-day HR and resting HR, overnight HRV Status (RMSSD), stress, Body Battery, respiration, Pulse Ox, and sleep stages with a sleep score. It does **not** have a skin-temperature sensor or ECG; those first arrived on the FR970 (2025).

### Cited Findings
- **HRV Status:** a 7-day average of overnight HRV is compared against a personal baseline range. The labels are Balanced (inside the range), Unbalanced (above or below it), Low (well below) and Poor (well below the normal range for your age). No status is shown until there is enough data for a 7-day average — [Garmin manual: HRV Status](https://www8.garmin.com/manuals/webhelp/GUID-607F08F6-33FC-40BF-9727-84E54043D82D/EN-US/GUID-9282196F-D969-404D-B678-F48A13D8D0CB.html)
- The HRV metric is RMSSD. The status needs about 3 weeks of regular overnight wear before it activates, and the baseline drifts slowly with your normal overnight values — [Garmin Japan health science: HRV status](https://www.garmin.co.jp/minisite/garmin-technology/health-science/hrv-status)
- "Unbalanced" can mean either higher or lower than baseline. A reading above baseline after a big jump in training may mean the body is working harder to recover — [Garmin blog: Understanding HRV status](https://www.garmin.com/en-SG/blog/fitness/understanding-the-hrv-status-on-your-garmin-smartwatch/)
- Garmin publishes no exact cutoffs for the HRV labels — [the5krunner HRV Status](https://the5krunner.com/garmin-features/physiology/hrv-status/)
- **Body Battery:** uses Firstbeat analytics of stress and recovery (HR rises and HRV falls under stress; high HRV means parasympathetic rest). Garmin cites the Firstbeat white paper "Stress and Recovery Analysis Method Based on 24-hour Heart Rate Variability" (2014) — [Garmin blog: Body Battery](https://www.garmin.com/en-SG/blog/body-battery/)
- Body Battery inputs are RMSSD-based HRV, HRV-derived stress, and sleep quality and duration, and it needs continuous optical HR (secondary source) — [the5krunner Body Battery](https://the5krunner.com/garmin-features/sleep/garmin-body-battery)
- Body Battery can struggle to recharge as illness begins — [Garmin blog](https://www.garmin.com/en-US/blog/fitness/why-your-body-battery-may-struggle-to-charge-when-you-start-to-get-sick/)
- **Pulse Ox:** the wrist SpO2 sensor supports spot checks, sleep monitoring and optional all-day/acclimation tracking — [Dell listing / review summary](https://dell.com/en-us/shop/garmin-forerunner-955-solar-smart-watch/apd/ac418630/wearable-lifestyle-technology); [the5krunner specs](https://the5krunner.com/specs/garmin/forerunner-955/)
- **Skin temperature and ECG:** Garmin lists both as FR970 features, and comparisons describe them as additions over the FR965 — [Garmin blog: FR965 vs 970](https://www.garmin.com/en-US/blog/fitness/the-difference-between-garmin-forerunner-965-and-970/); [Android Central FR970 review](https://www.androidcentral.com/wearables/garmin-forerunner-970-review); [the5krunner 970 vs 965](https://the5krunner.com/2025/05/15/garmin-forerunner-970-comparison-965)

### Inferences
- Since the FR965 lacks skin temperature and the FR955 is the older platform, the FR955 almost certainly has no skin temperature. Any skin-temp field from the Garmin API will be empty for FR955 users.
- Standard daily fields are also likely present (unverified): steps, step goal, floors (barometric altimeter), moderate/vigorous intensity minutes (vigorous count double), active and resting calories, all-day stress 0-100 (Firstbeat HRV-based), respiration rate (breaths/min, all day and sleep), sleep stages (light/deep/REM/awake) with a sleep score 0-100 and sub-scores, sleep coach/sleep need, manual hydration logging, and menstrual/pregnancy tracking via Connect.

### Gaps
- No Garmin page was retrieved that confirms Sleep Coach / sleep need or nap detection on the FR955. These are believed to have arrived via firmware (unverified).
- Exact Body Battery formula: Garmin publishes none.

## Training and performance metrics

### Takeaway
The FR955 launched (June 2022) with Training Readiness, HRV Status, Morning Report, Real-Time Stamina, the updated Race Predictor, Acute Load and native wrist running power. Endurance Score and Hill Score arrived in a Q3 2023 firmware update (beta 16.09 onward). All of these are Firstbeat models built on HR, HRV, pace and power, and Garmin publishes no exact weightings.

### Cited Findings
- **Training Readiness:** the watch combines training, recovery and sleep into one score. The six inputs are sleep score, recovery time, HRV status, acute load, sleep history and stress history — [T3 explainer](https://www.t3.com/how-to/garmin--training-readiness-feature-explained); [Garmin FR955 manual: Training Status](https://www8.garmin.com/manuals-apac/webhelp/forerunner955/EN-SG/GUID-30B699EB-48E7-411C-ADC5-90A94CA8E4AE-1590.html)
- No official percentage weights for Training Readiness have been published — [the5krunner Body Battery/TR summary](https://the5krunner.com/garmin-features/sleep/garmin-body-battery)
- **Acute Load:** a weighted sum of recent exercise load scores (duration and intensity) over about 7 days, compared with chronic load to show load balance and injury risk. **Recovery Time** is the time remaining until you are fully recovered for the next hard session — [Garmin FR955 manual: Training Status](https://www8.garmin.com/manuals-apac/webhelp/forerunner955/EN-SG/GUID-30B699EB-48E7-411C-ADC5-90A94CA8E4AE-1590.html); [T3](https://www.t3.com/how-to/garmin--training-readiness-feature-explained)
- **Endurance Score and Hill Score:** added in beta 16.09 (July 2023) and stable in Q3/Sept 2023 for FR955 and FR965 — [Notebookcheck 16.09](https://www.notebookcheck.net/Garmin-Forerunner-955-smartwatch-receives-new-features-with-Public-Beta-Version-16-09.733697.0.html); [Android Central Sept 2023](https://www.androidcentral.com/wearables/garmin-september-2023-update-forerunner-instinct-watches); [DC Rainmaker feature list](https://dcrainmaker.com/2023/06/complete-fenix-features.html)
- Hill Score measures strength on steep climbs and endurance on long ascents, using VO2max and training history. Endurance Score uses VO2max plus acute and chronic load — [Wareable](https://www.wareable.com/garmin/garmin-forerunner-265-965-hill-score)
- **Real-Time Stamina:** shows current exertion plus remaining energy and time/distance capacity at the current pace during a run or ride. **Race Predictor/race widget:** gives race-day-specific predictions with weather, a countdown and trendlines. **Morning Report:** a daily summary combining sleep, HRV, Training Readiness and other data — [Slowtwitch](https://www.slowtwitch.com/industry/garmin-brings-upgraded-hardware-and-all-the-analytics-to-forerunner-955-solar/); [Live Science review](https://www.livescience.com/gamin-forerunner-955-review); [Tom's Guide review](https://www.tomsguide.com/reviews/garmin-forerunner-955)
- **Firstbeat EPOC:** EPOC is the excess oxygen consumed during recovery compared with rest. It is estimated step by step from current intensity (%VO2max, derived from HR), time elapsed and previous EPOC. On Garmin, training load is EPOC accumulated over 7 days, and aerobic Training Effect (0-5) is derived from EPOC. Firstbeat reports r=0.89 against measured EPOC (Rusko et al. 2003) — [Firstbeat EPOC & Training Effect](https://www.firstbeat.com/en/science-and-physiology/epoc-and-training-effect/); [Firstbeat EPOC white paper (third-party mirror)](https://www.wanarun.net/blog/wp-content/uploads/2013/07/EPOC_white_paper.pdf); [Firstbeat Training Load guide](https://content.firstbeat.com/hubfs/Sports/Sports%20Guides/Sports%20Guides%20(English)/ENG-Sports-Guide-Training%20Load.pdf)
- **VO2max estimation:** Firstbeat analyzes the HR-to-speed relationship at multiple reliable segments of a session. A validation with optical wrist HR found MAPE of about 5.2% against lab tests — [Firstbeat fitness level](https://www.firstbeat.com/science-and-physiology/fitness-level/); [Firstbeat VO2max white paper](https://www.firstbeat.com/wp-content/uploads/2015/10/FFW609US05-171.pdf)

### Inferences
- Other FR955 metrics that are well established but were not verified this session (unverified):
  - VO2max for running and cycling (cycling needs a power meter), with heat- and altitude-adjusted values
  - Training Status (Productive, Maintaining, Peaking, Recovery, Unproductive, Detraining, Strained, Overreaching), which became HRV-aware in 2022
  - Load Focus (anaerobic, high aerobic and low aerobic buckets against targets, over 4 weeks)
  - Aerobic/Anaerobic Training Effect with a primary benefit label
  - Lactate Threshold HR and pace (auto-detect or guided test; auto-detect historically needed a chest strap and has since been allowed from the wrist on some models)
  - Functional Threshold Power (cycling, with a power meter)
  - Performance Condition (-20 to +20, shown after 6-20 min)
  - Heat and altitude acclimation (%)
  - Running power, native wrist since FR955 (requires no strap but is more accurate with HRM-Pro/RD pod), with power zones
  - Recovery Time, and Intensity Minutes per activity
- Garmin's "Training Readiness" can be treated as a Firstbeat composite. Any connector should store the component values, not just the score.

### Gaps
- Official Training Readiness weights are unpublished. Figures circulating online should be treated as speculative.
- Whether Lactate Threshold auto-detection on the FR955 still requires a chest strap in current firmware could not be verified.

## Activity-level metrics and running dynamics (with sensor requirements)

### Takeaway
Per activity, the FR955 records GPS track, pace and speed, distance, HR and HR zones, cadence, elevation (barometric), wrist running power with power zones, laps and splits, Training Effect, EPOC load and temperature. Advanced running dynamics need an accelerometer accessory (HRM-Pro family or the Running Dynamics Pod). Without one, the watch falls back to limited wrist-based dynamics, and ground contact time balance is never available from the wrist.

### Cited Findings
- If the HRM-Pro or pod is not connected, the watch automatically switches to wrist-based running dynamics. GCT and balance are computed only while running, not walking — [Garmin FR955 manual: Running Dynamics](https://www8.garmin.com/manuals-apac/webhelp/forerunner955/EN-SG/GUID-16B503BA-936C-4A24-A8F2-9E3C07B49647-9193.html); [Tips for missing running dynamics data](https://www8.garmin.com/manuals-apac/webhelp/forerunner955/EN-SG/GUID-D7671200-AEE8-43AF-950A-E237663EB65F-660.html)
- GCT balance is not calculated with wrist-based running dynamics. It is shown as a left/right % split (e.g. 48-52) — [Garmin manual: Running Dynamics](https://www8.garmin.com/manuals/webhelp/GUID-2492EDA1-1182-400B-8F43-D8B3211E4F3C/EN-US/GUID-62A09512-518A-424A-8491-FE2B80CD2091.html)
- Vertical oscillation and vertical ratio ranges differ between a chest sensor (HRM-Pro) and a waist sensor (RD Pod) — same Garmin manual pages above
- Multi-band GNSS (GPS, GLONASS, Galileo, BeiDou, QZSS) with SatIQ comes on both the 955 and the 955 Solar. On the Solar, battery is about 49 h in standard GPS and about 22 h with multi-band — [the5krunner specs](https://the5krunner.com/specs/garmin/forerunner-955/); [Slowtwitch](https://www.slowtwitch.com/industry/garmin-brings-upgraded-hardware-and-all-the-analytics-to-forerunner-955-solar/)

### Inferences
- Full dynamics set with accessory (unverified for complete list): cadence, stride length, GCT, GCT balance, vertical oscillation, vertical ratio. The wrist alone gives cadence and stride length, and some sources say limited GCT, VO and VR also come from the wrist on newer firmware.
- Temperature comes from the internal wrist sensor, which body heat skews, or from a Tempe sensor (unverified).
- Strap-only data: beat-to-beat HR while swimming (HRM-Pro storage). A chest strap also improves the accuracy of HR-derived metrics (Training Effect, load, VO2max).

### Gaps
- No official list of which dynamics the wrist supports was retrieved.
- Running power algorithm details (wind, slope) were not retrieved for the FR955.

## Differences vs newer models

### Takeaway
The FR965 (2023) launched with Endurance and Hill Score and an AMOLED screen. The FR955 received both scores by firmware. The FR970 (2025) adds hardware the FR955 cannot receive by update: a skin-temperature sensor and the ECG app. Its newer HRM 600-dependent features also do not reach the FR955.

### Cited Findings
- The FR970 adds skin temperature (overnight deviation) and ECG (AFib screening) over the FR965 — [Garmin blog](https://www.garmin.com/en-AU/blog/?p=3760); [the5krunner](https://the5krunner.com/2025/05/15/garmin-forerunner-970-comparison-965)
- FR955/965 shared a feature roll-down of Fenix 7 Pro/Epix Pro features in 2023 — [DC Rainmaker](https://dcrainmaker.com/2023/06/complete-fenix-features.html); [the5krunner](https://the5krunner.com/2023/06/02/garmin-965-955-new-features-inbound)

### Inferences
- FR970-era metrics such as running economy, step speed loss (with HRM 600), training load ratio and the Elevate Gen5 sensor are likely absent on the FR955, which uses the Gen4 sensor (unverified).

### Gaps
- No confirmation of the FR955's current (2026) firmware version or whether it is still receiving feature updates.
