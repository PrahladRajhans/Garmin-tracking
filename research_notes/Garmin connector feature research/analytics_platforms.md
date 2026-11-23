# Consumer and Athlete Analytics Platforms (Garmin / Apple Health / Strava data), as of 2026

Method note: about 12 web searches; most findings come from search-result summaries of official help pages. Where a vendor publishes no formula, that is listed as a gap. I found little 2026-specific material; most method docs are older but still current pages.

## Whoop: Strain, Recovery, Sleep, Healthspan/Whoop Age, Stress

### Takeaway
Whoop publishes concepts and bands but not formulas. Strain (0-21) is a logarithmic measure of cardiovascular load plus muscular load. Recovery (0-100%) comes from HRV and RHR, with respiratory rate and sleep also feeding in. Healthspan/Whoop Age uses 9 metrics and needs 21 recoveries.

### Cited Findings
- Strain is a 0-21 scale built from cardiovascular load (heart rate) and muscular load (strength work). It is logarithmic, so each extra point gets harder to earn, and separate workouts do not simply add up — [Whoop: How does Strain work](https://whoop.com/thelocker/how-does-whoop-strain-work-101)
- Recovery is a daily percentage reflecting cardiovascular and nervous-system recovery (HRV, RHR), not muscle soreness. Bands: green 67-100%, yellow 34-66%, red 0-33% — [Whoop: How does Recovery work](https://www.whoop.com/us/fr/thelocker/how-does-whoop-recovery-work-101/)
- Recovery sets a recommended daily Strain target meant to keep fitness while still recovering — [Whoop Strain 101](https://whoop.com/thelocker/how-does-whoop-strain-work-101)
- Healthspan analyzes 9 key metrics to calculate Whoop Age (faster or slower aging) and becomes available after 21 recoveries — [How WHOOP works](https://www.whoop.in/pages/how-it-works)
- Community thread on how Strain is calculated — [Whoop community](https://community.whoop.com/t/how-does-whoop-calculate-strain/133)

### Inferences
- A Garmin-based tool could copy Strain's design (a log-compressed, HR-zone-weighted daily load) and Recovery's design (HRV/RHR z-scores against a rolling baseline). Neither is proprietary in concept.

### Gaps
- The exact weights for Recovery inputs, how respiratory rate and sleep enter Recovery, the 9 Healthspan metrics, and how the Sleep Performance and Stress Monitor are calculated were not confirmed in the sources found.

## Apple-Health-based apps (Athlytic, Bevel, Gentler Streak)

### Takeaway
Athlytic documents the most: Recovery is HRV (weighted more) plus RHR, compared against a 60-day baseline and taken from sleep windows. Bevel publishes only high-level descriptions. Gentler Streak's "Activity Path" is based on a TSB (fitness-fatigue) model driven by workout heart rate.

### Cited Findings
- Athlytic Recovery compares each day's HRV and RHR against a rolling 60-day average. HRV is weighted somewhat more than RHR — [Athlytic: Understanding Recovery](https://athlyticapp.helpscoutdocs.com/article/20-understanding-recovery)
- With Sleep Prioritization (the default), it uses average HRV during sleep and overnight RHR. Without sleep samples, Recovery updates during the day — [Athlytic Recovery Preferences](https://athlyticapp.helpscoutdocs.com/article/21-recovery-preferences); [Preventing Recovery updating](https://athlyticapp.helpscoutdocs.com/article/32-preventing-recovery-from-updating-throughout-the-day)
- Athlytic offers an optional RMSSD computed from beat-to-beat data (with outlier filtering) in place of Apple's SDNN. It can also write its own sleep-based RHR to Health — [Athlytic help](https://athlyticapp.helpscoutdocs.com/article/20-understanding-recovery)
- Athlytic is marketed as turning an Apple Watch into a Whoop — [TechRadar](https://techradar.com/computing/websites-apps/this-app-turns-my-apple-watch-into-a-whoop-band)
- Bevel: Strain Score is "personalized based on your sleep and recovery". Recovery is a daily readiness score. Sleep analysis covers stages, duration and interruptions. "Energy Bank" combines recovery, sleep, strain and stress. Cardio Load shows a "Calibrating" status — [Bevel App Store](https://apps.apple.com/us/app/bevel-all-in-one-health-app/id6456176249)
- Gentler Streak Activity Path combines logged workouts, their intensity and their impact on fitness. It is TSB-model based, more HR data makes it more accurate, and premium users get a 4-day rest forecast — [TapSmart deep dive](https://www.tapsmart.com/features/deep-dive-gentler-streak/?amp=1); [BGR](https://www.bgr.com/tech/gentler-streak-improves-activity-path-tracking-offers-50-off-in-black-friday-deal); [9to5Mac](https://9to5mac.com/2022/02/17/gentler-streak-apple-watch-app/)

### Inferences
- The common recipe is: overnight HRV/RHR versus a personal baseline (14-60 days) gives recovery; HR-based TRIMP-like load in an ATL/CTL model gives strain/form. All of these inputs can be had from Garmin data too.

### Gaps
- Bevel's formulas and Athlytic's exact Exertion/strain formula were not found.

## intervals.icu, Runalyze, Golden Cheetah, TrainingPeaks/WKO, Stryd: unique metrics

### Takeaway
These tools publish their methods most openly. intervals.icu offers a PMC (CTL/ATL/TSB) plus eFTP from single maximal efforts. Runalyze offers Effective VO2max from HR versus pace, Marathon Shape, and TRIMP-based ATL (7d)/CTL (42d). Golden Cheetah models CP/W'/Pmax, Banister and PMC. TrainingPeaks offers TSS/rTSS/hrTSS. Stryd offers RSS against Critical Power.

### Cited Findings
- intervals.icu Fitness chart: CTL (fitness), ATL (fatigue), TSB (form) = fitness minus fatigue — [intervals.icu Fitness chart](https://www.intervals.icu/features/fitness-chart/); [forum](https://forum.intervals.icu/t/can-i-interpret-the-form-metric-always-in-the-same-way/110929.md)
- intervals.icu eFTP is estimated automatically from single maximal efforts, with no test needed. It also offers automatic submaximal fatigue testing and a power curve — [intervals.icu](https://intervals.icu); [Submaximal fatigue testing](https://www.intervals.icu/features/submaximal-fatigue-testing/); [Power curve](https://www.intervals.icu/features/power-curve/)
- intervals.icu has no official VO2max metric; forum users propose estimates — [forum](https://forum.intervals.icu/t/vo2max-estimation/10157)
- Runalyze Effective VO2max is estimated per run from the HR-versus-pace relationship and used to predict races. On its own it ignores whether the athlete has trained enough for the distance — [Runalyze calculations](https://blog.runalyze.com/tutorial/runalyze-understanding-the-calculations/)
- Runalyze Marathon Shape uses the last 6 months: weekly km weighted 2/3, long runs 1/3. Thresholds are 17% for 10k, 42.5% for a half marathon and 100% for a marathon. It corrects over-optimistic long-distance predictions and is "not scientifically based" — [Glossary: Marathon shape](https://runalyze.com/glossary/marathon-shape); [Blog: other distances](https://blog.runalyze.com/features/new-marathon-shape-for-other-distances)
- Runalyze TRIMP feeds ATL (EWMA over 7 days) and CTL (EWMA over 42 days) — [Runalyze help: Calculations](https://runalyze.com/help/article/88)
- TrainingPeaks: bike TSS needs power for at least 80% of the workout. rTSS uses Normalized Graded Pace versus threshold pace. hrTSS is the fallback, accurate for steady efforts but weaker for variable ones — [TrainingPeaks help](https://help.trainingpeaks.com/hc/en-us/articles/204071944)
- Stryd RSS per second = a × (power/CP)^b. One hour at CP = 100 RSS. RSS is 0 if CP is unset. Running stress rises more steeply with intensity than cycling — [Stryd help: RSS](https://help.stryd.com/en/articles/6879537-running-stress-score-rss); [Stryd blog](https://blog.stryd.com/2017/01/28/running-stress-score/)
- Golden Cheetah: CP, W' (finite work above CP) and Pmax modeling, plus Banister and PMC charts. GOVSS is a running analogue to TSS/BikeScore. Running RSS follows the Stryd implementation — [goldencheetah.org](https://goldencheetah.org/); [GC users: GOVSS](https://groups.google.com/g/golden-cheetah-users/c/zJuNFOeTP9w); [GC users: RSS](https://groups.google.com/g/golden-cheetah-users/c/MgtlbMqAUqY)

### Inferences
- The highest-value features to copy from Garmin FIT data: a PMC with sport-specific load, automatic threshold estimation (eFTP / critical speed), Effective VO2max from HR versus pace, and a volume-readiness correction like Marathon Shape for race predictions.

### Gaps
- No source confirmed intervals.icu's aerobic decoupling (Pa:HR / Pw:HR drift) formula, WKO5 mFTP/PDC modeling, Golden Cheetah W'bal implementation details, or Runalyze's exact TRIMP variant (Banister with gender factor is likely but unverified). Final Surge: no methodology found; it appears to be mainly a plan and log platform.

## Strava: Relative Effort, Fitness & Freshness, Athlete Intelligence

### Takeaway
Relative Effort (replaced Suffer Score in 2018) is an HR-based internal-load score that feeds the subscriber-only Fitness & Freshness chart. Athlete Intelligence produces AI written recaps of each activity covering pace, HR, elevation, power and Relative Effort.

### Cited Findings
- Relative Effort replaced Suffer Score in April 2018. It measures internal (cardiovascular) load, unlike TSS's external load. Fitness & Freshness and Weekly Relative Effort are subscriber-only — [the5krunner](https://the5krunner.com/2019/03/28/strava-relative-effort/)
- Athlete Intelligence turns workout data into a short summary of achievements and goals, commenting section by section on pace, HR, elevation, power and Relative Effort. It is generated on upload but runs when the activity is opened. It launched as a beta in 14 languages (Oct 2024) and later fully launched — [TechRadar](https://techradar.com/health-fitness/strava-s-powerful-ai-insights-are-here-athlete-intelligence-is-now-available-in-beta); [the5krunner](https://the5krunner.com/2024/10/03/strava-athlete-intelligence-subscribers/); [Wareable](https://www.wareable.com/news/strava-athlete-intelligence-full-launch-flyover-sharing-progress-comparison)
- Since then it has shifted toward explaining effort, fatigue and trends in plain language. Strava also now lets Claude access a user's training history — [T3 2026](https://www.t3.com/active/strava-2026-future-and-challenges); [T3 Claude](https://www.t3.com/active/strava-claude-ai-training-data-integration-0626)
- Criticism: some call it pointless or too positive — [Cycling Weekly](https://www.cyclingweekly.com/news/strava-says-its-new-ai-feature-is-not-a-novelty-but-i-think-its-pointless)

### Gaps
- Strava's Relative Effort and Fitness & Freshness formulas are not published in the sources found.

## Oura, HRV4Training, Elite HRV (readiness from HRV)

### Cited Findings
- Oura Readiness contributors: lowest RHR and its timing, body temperature, sleep, previous-day activity, HRV balance, sleep balance and activity balance. HRV Balance compares the last 14 days (recent days weighted more) against a 3-month average. Bands: 85-100 optimal, 70-84 good, 60-69 fair, below 60 pay attention — [Oura support](https://support.ouraring.com/hc/en-us/articles/360057791533); [Oura blog](https://ouraring.com/blog/readiness-score/)
- Elite HRV Morning Readiness uses ln(RMSSD) against a personal baseline built over several days. Gauge sensitivity adapts to baseline variability — [Elite HRV help](https://help.elitehrv.com/article/56-how-is-morning-readiness-determined)
- HRV4Training is used in research for daily rMSSD/RHR tracking. lnRMSSD is the recommended transform — [PMC study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8659706); [AIS HRV guide](https://www.ais.gov.au/__data/assets/pdf_file/0013/1130260/HRV-BPG_FINAL.pdf)

### Gaps
- HRV4Training's own readiness algorithm (it is believed to use a normal range around the baseline) was not confirmed from a primary source.

## Which insights users value most

### Takeaway
Forum evidence (TrainerRoad, Slowtwitch, reviewers; no Reddit threads were retrieved) suggests users trust simple signals most: sleep duration, RHR, and HRV trends against a baseline. Composite readiness and recovery scores draw the most skepticism.

### Cited Findings
- Sleep tracking and accountability were rated most useful by a long-time Garmin and Whoop user. Others named sleep hours and RHR as their most useful data — [TrainerRoad forum](https://www.trainerroad.com/forum/t/whoop-vs-oura-for-recovery-and-sleep-trends/113593.md); [TrainerRoad](https://www.trainerroad.com/forum/t/favorite-sleep-recovery-trackers-do-they-work/36842.md)
- Garmin Training Readiness is divisive: some turned it off, while a reviewer finds it useful for flagging negative inputs — [TrainerRoad](https://www.trainerroad.com/forum/t/incorporating-garmin-training-readiness-data-into-tr/115381); [the5krunner](https://the5krunner.com/garmin-features/training/training-readiness/)
- HRV is valued as a trend. RPE and subjective feel are still considered key — [Slowtwitch](https://forum.slowtwitch.com/t/adjusting-training-plan-based-on-recovery-metrics-hrv-training-readiness-recovery-time-etc/827209); [TrainingPeaks blog](https://www.trainingpeaks.com/blog/the-metrics-athletes-should-track-every-morning/)
- An expert argues to look at underlying metrics rather than the readiness score — [Tom's Guide](https://www.tomsguide.com/au/wellness/fitness/an-exercise-recovery-expert-says-this-is-the-metric-you-should-look-at-and-its-not-your-readiness-score)

### Inferences
- Transparent, explainable metrics (showing the inputs behind a score) likely beat black-box composites for this audience.

### Gaps
- Reddit (r/Garmin, r/whoop, r/AdvancedRunning) was not directly retrieved, and no quantitative survey of feature value was found.
