# Follow-up audit, 23 November 2026

This audit records the status of the owner's requests. [ROADMAP](../ROADMAP.md) is the plan.
All visual checks use synthetic fixtures. The owner's archive and physical devices remain
separate validation tasks.

| Request | Evidence in this pass | What remains |
|---|---|---|
| Smaller chart cursor and smoother scrolling | v0.15.1 and PR #18. Thinner guides, frame-based pointer updates and native vertical scrolling. | Physical iPhone Files preview. |
| Finer detail without a long daily brief | History links show a day, last seven days, each populated month and the last 12 completed months. Day details show available Garmin readings, sleep stages, recorded workouts and hourly pulse for recent dates when available. | More historical intraday charts, sport-specific pages and older per-workout traces. The current trace view covers recent runs with FIT data. |
| Explain baselines, changes and next checks | Recovery adds shared personal context for resting pulse, overnight oxygen and breathing. HRV keeps its existing range and adds a prior-week comparison when available. Sleep shows the recent average beside the target, and Training a historical load guide. Today shows noteworthy range departures. | Compare against the Mac's archive and watch fit, and validate whether measured changes help choose training. Descriptive changes are not forecasts. |
| Try optional overlays in a few workouts | The Run timeline pilots cadence/step length and speed/heart rate, using a shared time axis and relative medians, with actual values in the point readout. | Owner feedback on overlay readability. Expand only after checking what measures have comparable time and coverage. |
| Weather and air quality later | Source audit covers station observations, historical models, local AQI, physiologic evidence and sleep limitations. [Feasibility note](../research_notes/Garmin%20connector%20feature%20research/environmental_context_feasibility.md) | Confirm local coverage and privacy, validate an outdoor context-only trial, and separately assess bedroom exposure. |
| Review the outside references and keep citations current | All eleven submitted URLs were checked. The source ledger distinguishes inspected material, vendor claims and unavailable notebook/article content. [Source review](../research_notes/Garmin%20connector%20feature%20research/owner_reference_review_2026-11.md) | Inspect the blocked Medium article and notebook cells if a public edition becomes available. |
| Main, publishing and governance | Log versions and link the exact CI results from GitHub. Version references, setup, handover, metric definitions and screenshots are updated. | This project is delivered from main. Live Mac refresh, iCloud and account-protected hosting still need the owner's device and account. |

The open issue for coaching quality is evidence. Short-term associations can orient a user
toward a useful check. Advice that predicts response or prescribes a change needs realistic
coverage, comparable workouts and a held-out period. A product feature inventory alone cannot
establish performance parity with Garmin, Whoop or Apple.

## Follow-up implementation, v0.17.0

| Request | Shipped | Next evidence |
|---|---|---|
| Learn from the websites and apply their methods | Prior-only matched-effort calculation, evidence drill-down and readiness benchmark. [Source-to-implementation ledger](../research_notes/Garmin%20connector%20feature%20research/owner_reference_review_2026-11.md#implemented-in-v0170) | Check which of the owner’s runs qualify and compare them with Garmin; repeat the benchmark on later weeks. |
| Show weather and AQI at workout points | Garmin snapshot and optional timestamped observations/models in the run chart cursor, with AQI standard and source. Retired prior watch-temperature slope. | Validate local provider coverage and timestamps before an automatic outdoor fetch trial. Sleep conditions are a separate research question. |
| Make insights concise and inspectable | One sentence per run comparison, median and observed span, dated record links, and expandable evidence on Training. | Use actual laptop, iPhone Safari and Files to check scrolling, contrast and navigation. Before publishing health data, verify private access on the account. |

The owner’s original handover also called for the exact FRIEND VO₂max bar and a private
phone path. The bar is on Body. The private publisher exists and requires the account
and device checks in [MAC_SETUP](../MAC_SETUP.md#private-phone-access-optional).
The original synthetic findings are historical. [ROADMAP](../ROADMAP.md) owns the order
of outstanding work.

## Coaching and repository follow-up

The unreleased pass tracks the interpretation layout, local model and prompt controls, and
the repository inventory in [the repository review](REPOSITORY_REVIEW.md). Three-year replay
passed against generated fixtures. The owner's original Mac archive and the complete manual
line review remain open. The [roadmap](../ROADMAP.md#repository-and-coaching-review) carries the
order of work.

## Running performance

The running redesign adds a four-week comparison, pace-and-pulse evidence, matched form
references, next-run checks, a separate local running review, and an elapsed kilometre
overlay. The [running roadmap](../ROADMAP.md#running-performance-review) tracks open
Mac archive validation, device checks and model selection.
