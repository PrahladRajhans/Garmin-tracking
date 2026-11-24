# Running performance research

Reviewed 24 November 2026. The dashboard uses an original design and renders local Garmin records.

| Source | What informed the release | Limits |
|---|---|---|
| [Strava Matched Activities](https://support.strava.com/en-us/articles/15401955-how-do-i-view-my-matched-activities) and [subscription features](https://support.strava.com/en-us/articles/15402044-what-features-are-included-in-a-strava-subscription) | Put the next check beside a visual training log and allow users to open a recorded effort. Build on the existing same-route replay and prior-only matched cohort. | Similar-pace cohorts can include different routes. The pace-and-pulse plot describes the sample without a fitted ability or race prediction. |
| [Garmin Forerunner 955 running dynamics](https://www8.garmin.com/manuals/webhelp/GUID-9D99A9D4-467A-4F1A-A0EA-023184FEA3DD/EN-US/GUID-62A09512-518A-424A-8491-FE2B80CD2091.html) | Define cadence, stride length, ground contact, oscillation and vertical ratio beside the measurements. Lead with personal pace-adjusted comparisons. | Garmin population bands are descriptive. The manual varies some reference bands by sensor position. Data fields can also be absent. |
| [Heiderscheit et al., step rate and joint mechanics](https://pubmed.ncbi.nlm.nih.gov/20581720/) and [Doyle et al., systematic review](https://pmc.ncbi.nlm.nih.gov/articles/PMC9441414/) | Offer a brief, optional shorter-step experiment at the same comfortable speed, with comfort as the follow-up. | Laboratory joint mechanics and athlete comfort are separate outcomes. Evidence on injury and performance is limited. Avoid a universal cadence target. |
| [Coyle and González-Alonso, cardiovascular drift](https://pubmed.ncbi.nlm.nih.gov/11337829/) and [running and cycling in the heat](https://pubmed.ncbi.nlm.nih.gov/32102057/) | Place pace beside heart rate for equal FIT moving-time halves. Point an unusual comparison back to context and a repeat effort. | Recorded heart rate or decoupling can shift with conditions, pacing and measurement. A single workout cannot explain why. |
| [Running injuries and training parameters, systematic review](https://pmc.ncbi.nlm.nih.gov/articles/PMC9528699/) | Show distance, frequency and repeatability with equal completed windows. | Findings on training parameters and injury were conflicting. Training volume does not establish personal injury risk or a safe growth rate. |

## Release and follow-up

- Ship recorded volume, elapsed versus moving time, pace and pulse, form comparisons, and an
  evidence-linked local interpretation. The deterministic recommendation remains available offline.
- Check the owner's archive for sufficient comparable sessions and clean device samples before
  proposing stronger durability or progression targets. Use repeated conditions and a held-out block
  to assess whether the recommendation helped.
- Consider best efforts from distance crossings and a formal durability protocol separately.
  Each needs rules for GPS gaps, stops, intervals, device changes and seasonal conditions.
