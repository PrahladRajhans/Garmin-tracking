# Accuracy and source review — 23 November 2026

This is an evidence ledger for ROADMAP's reliability/accuracy/UI review, not a second plan.
No user database was available; findings distinguish code defects from unverified scientific
assumptions. Existing real-data figures in earlier changelog entries remain historical.

## Retrieved primary evidence

1. **AASM/SRS sleep consensus:** *Recommended Amount of Sleep for a Healthy Adult: A Joint
   Consensus Statement of the American Academy of Sleep Medicine and Sleep Research Society*,
   SLEEP 2015;38(6):843–844. [Full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC4434546/).
   The consensus says adults should sleep **7 or more hours** regularly. It does not measure
   this user's need. Our common 8-hour fallback is a planning choice; Garmin's valid need wins.
2. **Tanaka et al., age-predicted HRmax:** *Age-predicted maximal heart rate revisited*,
   doi:[10.1016/S0735-1097(00)01054-8](https://doi.org/10.1016/S0735-1097(00)01054-8),
   [PubMed 11153730](https://pubmed.ncbi.nlm.nih.gov/11153730/). The abstract retrieved through
   Europe PMC reports `208 − 0.7 × age` from the meta-analysis. This supports the published
   equation, **not** its accuracy for this person or our max(repeatable peak, equation) policy.
   Full-paper validation and a personal max-HR test remain separate requirements.
3. **FRIEND treadmill reference:** Kaminsky LA, Arena R, Myers J. *Reference Standards for
   Cardiorespiratory Fitness Measured With Cardiopulmonary Exercise Testing: Data From the
   Fitness Registry and the Importance of Exercise National Database.* Mayo Clin Proc.
   2015;90(11):1515–1523. doi:[10.1016/j.mayocp.2015.07.026](https://doi.org/10.1016/j.mayocp.2015.07.026).
   [Full text, **Table 3**](https://pmc.ncbi.nlm.nih.gov/articles/PMC4919021/#T3) retrieved.
   This is the percentile table, not Table 2 (which contains maximal-effort responses).
   It reports measured treadmill CPX values for a US cohort without cardiovascular disease,
   ages 20–79. Reference percentiles are neither individual targets nor a validation of wearable
   estimates, and US reference data may not represent an individual in India. Do not mix the
   measured FRIEND rows with the Cooper predicted rows in the same table.

## Retrieved technical/practitioner evidence

- [Python datetime](https://docs.python.org/3/library/datetime.html): naive datetime methods
  can interpret times as local. Normalized sleep timestamps are UTC, so the HR window comparison
  must attach UTC explicitly before converting to epoch milliseconds. The corrected comparison
  also excludes the prior known sleep window and negative missing samples.
- [TrainingPeaks decoupling guide](https://www.trainingpeaks.com/blog/aerobic-endurance-and-decoupling/),
  retrieved title *Aerobic Decoupling: Ultimate 2026 Heart Rate Drift Guide*. This is practitioner
  guidance, not a controlled validation of a universal threshold. It discusses heat, dehydration,
  fatigue and intensity as alternative contributors. Run advice now retains the measured drift
  but avoids declaring aerobic base the single cause.
- [W3C contrast minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html):
  normal text needs 4.5:1, large text 3:1, subject to its listed exceptions.
  [Focus visible](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html): keyboard users
  need a visible focus indicator. These guide measured UI checks, not a claim of full compliance.

## Corrections supported by code evidence

- Debt used a 7-hour fallback while Sleep %/bedtime used 8. They now share one 8-hour planning
  fallback with per-night provenance. Missing nights are not zero-debt observations.
- Two nights could generate a sleep z-score despite the documented baseline sufficiency rule.
  Sleep now needs 14 prior valid observations; RHR/respiration correctly count 21 **prior** values.
- Calibrating readiness could return reassuring training advice; it now says insufficient data.
- A blood-pressure dipping heuristic had become a heart-rate "healthy" label. No heart-rate-specific
  validation was established in the project's sources. Removed the health label, without inventing
  a replacement cutoff. The descriptive percentage is retained with its inputs and caveats.
- Recovery-weight study lost official-HRV days without health-status rows. It now merges those
  streams consistently. Composite variants share comparison days per outcome. `r=0` is no longer
  treated as missing. Equal weights and the >0.05 improvement on **both** outcomes rule remain.
- Invalid workout times, reversed targets, fractional zones and invalid overrides could crash or
  silently change meaning. Validation now rejects them; technical format limits bound nested steps.

## Not established by this review

- No new real-data agreement, clinical efficacy, injury prediction or personal HRmax calibration.
- No claim that population percentiles make Garmin and effective VO2max physiologically equivalent.
- Swain coefficient details and several older formula references still need full-paper verification;
  one targeted literature request timed out. Existing tests pin implementation, not scientific truth.
- HRV normal-band widths, the 60-day window, sleep fallback, readiness composite and strain mapping
  remain documented design choices/heuristics. The displayed HRV CV is calculated on **ln RMSSD**;
  it must not be presented as raw-RMSSD CV without a separately validated change.
- Formal changepoint significance, prospective prediction, causal behavior effects and matched-route
  run classification are not added. Multiple values can be shown together without claiming causation.
- Live Mac/iPhone, Garmin sync and Cloudflare account behavior still need device/account checks.
  Cloudflare/Garmin marketing pages returned HTTP errors even after network access was restored;
  the current Access pricing allowance has not been independently confirmed.

Future work and priorities stay in ROADMAP. No source was cited as read when it only returned
an error. Literature helper packaging lacked a shared support file; research here used the
actual full-text websites and Europe PMC records, not fabricated tool results.

### Dashboard interpretation follow-up (v0.14.1)

The UI review removed the unconditional “under 5% = solid aerobic base” drift label, and
run advice does not claim a personal comparison when prior form history is absent. A
nonpositive/nonfinite fitted form expectation is unavailable, rather than a denominator.
Current-day personal ranges exclude stale measurements and require preceding observations;
see METRICS for exact minimums. These changes qualify interpretation without changing the
underlying physiological formulas. W3C sources, screenshots and accessibility evidence are
linked in [UI_REVIEW](../../docs/UI_REVIEW.md). No new competitor or clinical validation is claimed.

### Run timing follow-up (v0.14.2)

Retrieved Garmin's [FIT duration article](https://developer.garmin.com/fit/articles/cookbook/durations.html)
on 23 November 2026. It defines elapsed duration as wall time including pauses and timer
duration as stopwatch time excluding them. Moving duration uses a speed threshold and can
differ across platforms. The repo now labels its sample-based estimate separately from Garmin
FIT fields. The gap, coverage and steady-run rules are documented engineering choices. The
recording tests check one-second and five-second sampling, a long pause, interpolation and an
odd/partial last kilometre. The owner's Garmin history was unavailable in cloud.
