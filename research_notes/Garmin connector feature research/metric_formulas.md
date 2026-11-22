# Endurance Training and Recovery Metric Formulas (Implementation Reference)

Scope note: this run used a limited number of web searches. Formulas marked [verified-search] were confirmed by search results in this session. Formulas marked [primary-ref] come from well-known primary publications cited by DOI or PubMed but were not re-fetched here. The report writer should treat [primary-ref] items as standard but give them a final check against the originals before publishing.

## Training load: TSS, rTSS, hrTSS, TRIMP variants, session RPE, NP, IF, NGP/GAP

### Takeaway
All of these metrics share one form: duration multiplied by an intensity weight that is anchored to a threshold (FTP, threshold pace, LTHR, HRR or ventilatory thresholds). Power-based TSS is the best defined. HR-based TRIMP variants differ only in how they weight intensity. sRPE is the only one that works across any modality without sensors.

### Cited Findings
- **Normalized Power (NP)** [primary-ref]: take a 30 s rolling mean of 1 Hz power, raise each value to the 4th power, average them, then take the 4th root. **IF = NP / FTP.** **TSS = (t_sec × NP × IF) / (FTP × 3600) × 100**, so one hour at FTP equals 100 TSS. — [Allen & Coggan, *Training and Racing with a Power Meter*](https://www.trainingpeaks.com/learn/articles/normalized-power-intensity-factor-training-stress/); [TrainingPeaks TSS explainer](https://www.trainingpeaks.com/learn/articles/what-is-training-stress-score/)
- **rTSS** [primary-ref]: TrainingPeaks' running TSS uses NGP and functional threshold pace (FTPace). IF = NGP speed / threshold speed, and rTSS = hours × IF² × 100. NGP adjusts for gradient. TrainingPeaks has not published its exact grade model. — [TrainingPeaks rTSS](https://www.trainingpeaks.com/learn/articles/running-training-stress-score-rtss-explained/)
- **GAP / grade cost** [primary-ref]: the metabolic cost of running on slopes from -45% to +45% follows a polynomial: Cr(i) = 155.4i⁵ − 30.4i⁴ − 43.3i³ + 46.3i² + 19.5i + 3.6 J·kg⁻¹·m⁻¹, where i is the gradient as a decimal. Flat-equivalent speed = v × Cr(i)/3.6. Strava's 2017 GAP model is instead fitted empirically from HR data across many users, and it penalises steep downhills less than Minetti does. — [Minetti et al. 2002, J Appl Physiol 93:1039](https://doi.org/10.1152/japplphysiol.01177.2001); [Strava engineering blog](https://medium.com/strava-engineering/an-improved-gap-model-8b07ae8886c3)
- **hrTSS** [primary-ref]: TrainingPeaks scales TRIMP so that one hour at LTHR equals 100. — [TrainingPeaks hrTSS](https://help.trainingpeaks.com/hc/en-us/articles/204071724)
- **Banister TRIMP** [verified-search]: TRIMP = Σ Δt_min × HRr × 0.64 × e^(k × HRr), where HRr = (HR − HRrest)/(HRmax − HRrest). k = 1.92 for men and 1.67 for women. — [GoldenCheetah TRIMPPoints.cpp](https://bazaar.launchpad.net/~ubuntu-branches/ubuntu/saucy/goldencheetah/saucy/view/head:/src/TRIMPPoints.cpp); [arXiv 2508.11613](https://arxiv.org/html/2508.11613v2); original: Banister 1991, and Morton, Fitz-Clarke & Banister 1990, J Appl Physiol 69:1171 ([doi](https://doi.org/10.1152/jappl.1990.69.3.1171))
- **Edwards TRIMP** [verified-search]: minutes in each of five %HRmax zones are multiplied by a zone weight and summed. The zones are 50–60% (×1), 60–70% (×2), 70–80% (×3), 80–90% (×4) and 90–100% (×5). The zone weights are standard but were not in the search snippet. — [arXiv 2508.11613](https://arxiv.org/html/2508.11613v2); Edwards 1993, *The Heart Rate Monitor Book*
- **Lucia TRIMP** [primary-ref]: three zones are bounded by VT1 and VT2. Time below VT1 is weighted ×1, between VT1 and VT2 ×2, and above VT2 ×3. A search source notes that these weights are still arbitrary. — [Lucia et al. 2003, MSSE 35:1381](https://doi.org/10.1249/01.MSS.0000079048.03357.D1); [arXiv 2508.11613](https://arxiv.org/html/2508.11613v2)
- **Session RPE** [primary-ref]: load = CR-10 RPE × session duration in minutes, with RPE collected about 30 minutes after the session. — [Foster et al. 2001, JSCR 15:109](https://pubmed.ncbi.nlm.nih.gov/11708692/)

### Inferences
- Cycling TSS needs FTP, rTSS needs threshold pace, and hrTSS/TRIMP need resting HR, max HR and LTHR. All of these must be stored per athlete with dates on them so that historical values stay correct when thresholds change.
- TSS units from different modalities are not strictly equivalent, so summing bike and run TSS is only an approximation.
- Garmin FIT files provide 1 s power, speed, altitude and HR, which is enough to compute everything above. Altitude from a barometer is noisy, so smooth it before computing grade (for example a 10–30 m distance window).
- If Garmin's own "Training Load" is available, treat it as a separate, proprietary Firstbeat EPOC-based metric. Do not mix it with TSS.

### Gaps
- TrainingPeaks' exact NGP formula and its hrTSS scaling are proprietary and were not verified.
- The Edwards zone weights were not confirmed verbatim in this session.

## Performance Management Chart: CTL, ATL, TSB, ramp rate, Banister model, ACWR

### Takeaway
CTL and ATL are exponentially weighted averages of daily load with time constants of 42 and 7 days. TSB is the difference between them. Banister's impulse-response model is the theory underneath, but its fitted parameters are unstable for individuals. ACWR is heavily contested and should not be presented as an injury predictor.

### Cited Findings
- **CTL, ATL, TSB** [primary-ref]: CTL_t = CTL_{t−1} + (TSS_t − CTL_{t−1}) / 42, and ATL_t = ATL_{t−1} + (TSS_t − ATL_{t−1}) / 7. TSB is usually computed as TSB_t = CTL_{t−1} − ATL_{t−1}, meaning yesterday's values ("form going into today"). intervals.icu calls these Fitness, Fatigue and Form and uses decay constants e^(−1/42). Ramp rate is the change in CTL over 7 days. — [TrainingPeaks PMC](https://www.trainingpeaks.com/learn/articles/the-science-of-the-performance-manager/); [intervals.icu forum/docs](https://forum.intervals.icu/)
- **Banister impulse-response model** [primary-ref]: p(t) = p0 + k1 Σ w(s)e^(−(t−s)/τ1) − k2 Σ w(s)e^(−(t−s)/τ2). Typical values are τ1 ≈ 42–45 days, τ2 ≈ 7–15 days, and k2 > k1. — [Banister et al. 1975](https://doi.org/10.1080/00049537508255241); [Morton et al. 1990](https://doi.org/10.1152/jappl.1990.69.3.1171). Criticisms are that the parameters are ill-conditioned, poorly identifiable and predict badly out of sample. — [Hellard et al. 2006, Physiol Meas 28](https://doi.org/10.1088/0967-3334/27/12/007)
- **ACWR criticism** [verified-search]: ACWR is mathematically coupled when the acute window is included inside the chronic window. In one example the ratio was 1.45 coupled versus 1.71 uncoupled. — [Lolli et al., BJSM 2019;53:921](https://bjsm.bmj.com/content/53/15/921.full)
- **ACWR criticism** [verified-search]: when chronic load was replaced with fixed or random values, the association with injury was the same. The authors call for the ratio to be dismissed. — [Impellizzeri et al., Sports Med 2021](https://iris.univr.it/retrieve/e34cfb98-e922-4c2f-aab5-18583ab7e31b/Impellizzeri_What%20Role%20Do%20Chronic%20Workloads%20Play_SportMed_2021.pdf); [IJSPP 2020 "Conceptual issues and fundamental pitfalls"](https://www.pubmed.gov/31672929/)
- **ACWR counterpoint** [verified-search]: an elite-sport case study found low practical impact from coupling. — [ECU case study](https://ro.ecu.edu.au/ecuworkspost2013/7321/)
- **ACWR origin** [primary-ref]: Gabbett's "sweet spot" of 0.8–1.3 and danger zone above 1.5. — [Gabbett 2016, BJSM 50:273](https://doi.org/10.1136/bjsports-2015-095788). An EWMA version of ACWR exists (λ = 2/(N+1)). — [Williams et al. 2017, BJSM](https://doi.org/10.1136/bjsports-2016-096589)

### Inferences
- Before the first CTL value, seed it either with about 6 weeks of history or with an assumed starting value. Values from the first 6 weeks or so are unreliable and the UI should show that.
- Rest days count as TSS = 0. Without them the decay is wrong.
- Rules of thumb such as a ramp rate of 5–8 CTL/week or a TSB of −10 to −30 being "productive" are practitioner heuristics, not validated thresholds. Label them that way.
- If ACWR is shown, use the uncoupled EWMA version and describe it as "load change", not injury risk.

### Gaps
- No validated population thresholds for TSB or ramp rate were found in peer-reviewed sources during this session.

## HRV: RMSSD, ln(RMSSD), rolling baseline, SWC / normal range

### Takeaway
Use ln(RMSSD) measured at the same time each morning or overnight. Compare the 7-day rolling mean against a longer baseline (about 30–60 days), using a normal band of baseline mean ± k × SD. Plews/AIS guidance supports 7-day rolling averages with a smallest worthwhile change. The specific multiplier is not standardised.

### Cited Findings
- RMSSD = sqrt(mean((RR_{i+1} − RR_i)²)) computed over artefact-corrected RR intervals. It reflects vagal (parasympathetic) activity. — [Task Force 1996, Circulation 93:1043](https://doi.org/10.1161/01.CIR.93.5.1043)
- A 7-day rolling average of ln RMSSD is more valid than single-day values. At least about 3–5 measurements per week are needed. — [Plews et al. 2014, IJSPP "how much compliance"](https://bvbvf1.bib-bvb.de/vufind/PrimoRecord/cdi_proquest_miscellaneous_1559624308); [Plews et al. 2013, Sports Med 43:773](https://doi.org/10.1007/s40279-013-0071-8); [AIS HRV best practice guide](https://www.ais.gov.au/__data/assets/pdf_file/0013/1130260/HRV-BPG_FINAL.pdf) [verified-search]
- The coefficient of variation of ln RMSSD (CV = SD/mean over 7 days) is a second marker. A rising CV together with a falling mean can indicate maladaptation. — [Plews et al. 2012, Eur J Appl Physiol 112:3729](https://link.springer.com/content/pdf/10.1007%2Fs00421-012-2354-4.pdf) [primary-ref]
- SWC is commonly set at 0.5 × the individual's SD of ln RMSSD, which is the AIS/Plews practice. Search did not confirm the exact multiplier, and one secondary source uses 0.3–0.5 SD. — [Substack (secondary, non-peer-reviewed)](https://platypusandfox.substack.com/p/understanding-heart-rate-variability)
- HRV4Training (Altini) computes the "normal range" from a roughly 60-day baseline and flags a 7-day mean outside about ±0.5 to 1 SD. Its daily advice combines the daily value against the baseline. — [HRV4Training blog](https://www.hrv4training.com/blog) [primary-ref, not fetched]

### Inferences
- Garmin's "HRV Status" is the overnight average of RMSSD (its own algorithm) with a baseline band. You can store the nightly value and recompute ln, the rolling 7-day mean and SD yourself, but Garmin's export does not give you raw RR intervals during sleep unless you use a device or log that records them.
- Implementation: lnRMSSD = ln(RMSSD_ms). Then baseline_mean and baseline_sd over the last 60 days (excluding the last 7), roll7 = mean of the last 7 days, and flag if |roll7 − baseline_mean| > 0.5 × baseline_sd (make the multiplier configurable).
- If ln(RMSSD) is above the band after heavy load it is not automatically "good". Parasympathetic saturation exists, so interpret it in context.

### Gaps
- The exact HRV4Training band parameters and the Plews SWC multiplier were not verified verbatim.

## Readiness/recovery composites

### Takeaway
There is no validated published formula for a combined readiness score. Commercial scores (Garmin Training Readiness, Whoop, Oura) are proprietary. A defensible approach is to compute per-metric z-scores against the athlete's own baseline (ln RMSSD, inverted RHR, sleep duration, ATL/TSB), then combine them with transparent weights.

### Cited Findings
- The AIS guide recommends interpreting HRV alongside other markers such as wellness questionnaires and load, rather than on its own. — [AIS HRV BPG](https://www.ais.gov.au/__data/assets/pdf_file/0013/1130260/HRV-BPG_FINAL.pdf)
- Subjective wellness measures respond to acute and chronic training load more consistently than objective markers. — [Saw, Main & Gastin 2016, BJSM 50:281](https://doi.org/10.1136/bjsports-2015-094758) [primary-ref]

### Inferences
- Suggested design (heuristic, not validated): z_i = (x − baseline_mean_i) / baseline_sd_i, with RHR and ATL inverted. Readiness = weighted mean, clipped and mapped to 0–100. Show each component so users can see what drove the score.

### Gaps
- No peer-reviewed validation exists for any composite readiness weighting.

## VO2max estimation and race prediction

### Takeaway
VDOT (Daniels–Gilbert) and Riegel are simple closed-form models that can be implemented directly. Critical speed/power with W′ is the most physiologically grounded and is fitted from best efforts. Firstbeat's HR–speed VO2max is proprietary.

### Cited Findings
- **Cooper test** [primary-ref]: VO2max ≈ (d_metres − 504.9)/44.73, where d is the distance covered in 12 minutes. — [Cooper 1968, JAMA 203:201](https://doi.org/10.1001/jama.1968.03140030033008)
- **Daniels–Gilbert VDOT** [primary-ref]: VO2(v) = −4.60 + 0.182258v + 0.000104v², with v in m/min. %VO2max(t) = 0.8 + 0.1894393e^(−0.012778t) + 0.2989558e^(−0.1932605t), with t in minutes. VDOT = VO2(v)/%max. To predict a race time for a given VDOT, solve for t numerically. — Daniels & Gilbert 1979, *Oxygen Power*; [Daniels' Running Formula](https://us.humankinetics.com/products/daniels-running-formula-4th-edition)
- **Riegel** [primary-ref]: T2 = T1 × (D2/D1)^1.06. — [Riegel 1981, American Scientist 69:285](https://www.jstor.org/stable/27850427). The exponent varies by individual (about 1.03–1.15), and the formula underestimates marathon times for less-trained runners. — [Vickers & Vertosick 2016, BMC Sports Sci Med Rehabil](https://doi.org/10.1186/s13102-016-0052-y)
- **Critical speed/power** [primary-ref]: with the 2-parameter model, d = CS × t + D′ (or W = CP × t + W′), fitted from best efforts lasting roughly 2–15 minutes. W′ balance during exercise can be tracked with Skiba's model: W′bal = W′ − ∫(W′exp)·e^(−(t−u)/τ), where τ = 546e^(−0.01·D_CP) + 316. — [Jones et al. 2010, MSSE 42:1876](https://doi.org/10.1249/MSS.0b013e3181d9cf7f); [Skiba et al. 2012, MSSE 44:1526](https://doi.org/10.1249/MSS.0b013e3182517a80)
- **Firstbeat** [primary-ref]: estimates VO2max from the linear relationship between HR and speed during valid running segments. Its white paper reports a MAPE of about 5%. — [Firstbeat VO2max white paper](https://www.firstbeat.com/en/science-and-physiology/white-papers/)

### Inferences
- Only fit critical speed from maximal efforts. Training runs underestimate it. Ask the user to tag or confirm best efforts.

### Gaps
- Firstbeat's algorithm details are proprietary.

## Intensity distribution, aerobic decoupling, efficiency factor, duration curves

### Takeaway
Seiler's three-zone model (below VT1/LT1, between thresholds, above VT2/LT2) defines polarized versus pyramidal distribution. Pa:HR decoupling and efficiency factor (EF) are TrainingPeaks/Friel practitioner metrics, not validated research measures.

### Cited Findings
- Elite endurance athletes do about 75–80% of sessions in zone 1 with the rest spread over zones 2 and 3 ("polarized" by session count). Pyramidal distribution means Z1 > Z2 > Z3. — [Seiler & Kjerland 2006, Scand J Med Sci Sports 16:49](https://doi.org/10.1111/j.1600-0838.2004.00418.x); [Seiler 2010, IJSPP 5:276](https://doi.org/10.1123/ijspp.5.3.276)
- A polarization index has been proposed: PI = log10((Z1/Z2) × Z3 × 100), counted as polarized when PI > 2.00 (Z1 > Z3 > Z2). — [Treff et al. 2019, Front Physiol 10:707](https://doi.org/10.3389/fphys.2019.00707)
- The results depend on whether time-in-zone or session-goal counting is used. — [Seiler & Kjerland 2006](https://doi.org/10.1111/j.1600-0838.2004.00418.x)
- EF = NP/avg HR (bike) or NGP/avg HR (run). Aerobic decoupling (Pa:HR) = (EF_first half − EF_second half)/EF_first half. Less than 5% is considered aerobically fit for a steady long effort. — [TrainingPeaks / Friel](https://www.trainingpeaks.com/blog/aerobic-endurance-and-decoupling/) [primary-ref]
- The mean-maximal power or pace curve is the best average over each duration (for example 1 s to 5 h), taken across a time window.

### Inferences
- Decoupling is only meaningful for steady efforts of 60 minutes or more. Heat, hydration and terrain confound it.

### Gaps
- None critical.

## Monotony and strain (Foster)

### Takeaway
Weekly monotony = mean(daily load)/SD(daily load) over 7 days. Strain = weekly total load × monotony.

### Cited Findings
- Monotony and strain were defined from daily sRPE load. High strain and monotony (monotony above about 2) were associated with illness. — [Foster 1998, MSSE 30:1164](https://pubmed.ncbi.nlm.nih.gov/9662690/) [primary-ref]

### Inferences
- Include rest days as 0. If SD = 0 (constant load), monotony is undefined, so guard against dividing by zero.

### Gaps
- The illness association comes from small samples. Treat thresholds as indicative only.
