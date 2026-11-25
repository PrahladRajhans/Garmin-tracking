# Owner request audit

This audit records the status of the owner's requests. [ROADMAP](../ROADMAP.md) is the plan.
The visual checks in this workspace use synthetic fixtures. The owner's archive and physical
devices remain separate validation tasks for the current release.

## Request reconciliation through v0.26.1

Reviewed 24 November 2026 against the conversation, Claude's pasted briefs and the repo.
The [current priorities](../ROADMAP.md#current-priorities) give the sequence and acceptance checks.

| Request | Shipped or verified | Still open |
|---|---|---|
| Qwen3.5 as the default across local AI | v0.26.1 sets `qwen3.5:4b` and migrates settings using the former default on first open. Local-only Ollama accepted 5/5 fictional routine summaries, with a median generation time of 13.36 seconds. The release and both CI versions passed. [Release](https://github.com/PrahladRajhans/Garmin-tracking/releases/tag/v0.26.1) | Verify the saved model, enabled and thinking settings, scheduled rebuild and visible cache on the owner's Mac. The older 14/29-summary check used Qwen2.5. |
| AI across the app, creative coach voice, long thinking and prompts | Routine checks and model capability detection shipped. Original reviewed prose is available for the Today and Running interpretations. There is a separate running prompt, editable voice, fictional cases, a 1–30-minute draft budget, and bounded SQLite memory of prior evidence. [Ollama guide](OLLAMA.md) | Validate review quality across eligible surfaces. The Qwen3.5 4B open-ended running draft was withheld in the Linux test. Finish the AI-written weekly story and checked reasons behind existing actions. The footer has a result count. It still needs the latest accepted time and clear status for disabled, unavailable, or withheld results. |
| Historical Garmin validation, preserve data, and test the AI | Replay checked 36 synthetic months with no broken links or duplicate IDs and an unchanged source file. Changed raw responses and FIT revisions are retained. [Repository review](REPOSITORY_REVIEW.md) · [Backups](OPERATIONS.md#backups-and-rollback) | Run coverage, replay and timing checks on the actual three-year archive. Verify the schedule, snapshot freshness, and backup/restore on the Mac. Missing older Garmin data or overwritten revisions require an export or backup if one exists. |
| Sleep design and a real plan | Night detail, stage timeline where recorded, week/month/year, wake consistency, a conservative bedtime proposal and hold, shortfall scenario, slept/rested journal and tag views shipped. [Dashboard plan](../DASHBOARD_PLAN.md) | The bedtime card computes a proposal. Finish a persistent weekly experiment, progression and step-back, nights on target vs recorded outcomes, and the before/after follow-up. Verify how the real sleep history reads. The Garmin watch schedule is set manually. |
| Planned vs done, movement, check-ins and Sunday review | Saved sessions can match recorded activities and inform the next week. The movement floor/streak and private morning/evening check-ins shipped. The Sunday card summarizes measured facts and includes the weekly plan. | Verify the loop on real records. The Sunday text is still rule-based. A routine knee-aware strength progression and a concise descriptive evening stress/Body Battery review from the brief are still candidates. Strength can already be logged in the plan. Review whether check-ins change the intended next-day decisions. |
| Advanced Running, charts, definitions and split toggle | v0.26 has the completed block comparison, pace/pulse plots, prior matched dynamics, individual checks and tips, split guides with denser charts and a distinct AI prompt. Training and Recovery got early definitions and chart-readout polish. [Metrics and sources](../METRICS.md#running-performance-block) | Verify matched cohorts and guides on actual runs, and check if the suggested experiment helps. Best efforts and late-run durability still need data and a defined comparison. |
| End-to-end UX, visual hierarchy and redundancy sweep | Removed the shared graph interaction instructions. Main navigation, run links, effort and sleep drill-downs, and narrow viewport checks shipped. [UI review](UI_REVIEW.md) | Complete the requested screen-by-screen sweep. Check wording, links, labels, empty states, scroll, contrast, saved-file size and real Safari/Files. The latest box and chart changes were concentrated in Running. |
| Garmin Connect, WHOOP and AthleteData inspiration | Public Garmin and WHOOP research led to journal comparisons, route replay, planned vs done and a weekly review. The AthleteData inventory documents ideas and access limits. [Paid coaching review](../research_notes/Garmin%20connector%20feature%20research/paid_coaching_2026-11.md) · [Connector inventory](../research_notes/Garmin%20connector%20feature%20research/connected_connectors_inventory.md) | No signed-in end-to-end comparison was verified. The exact original labels for AthleteData items 1 and 2 are not recoverable from the available brief, so completion of that numbered pair remains unverified. |
| Larger model and Nimble comparison | Qwen3.5 4B remains the chosen default. The tested Nimble tag exposes a decision interface. Its text-generation request was rejected. | Evaluate a broader set of cases on the Mac. Larger Qwen for writing and Nimble for a separate review classifier are optional experiments. |
| Messaging | A local digest/inbox with a single reviewed change, private evidence link and deduplication is documented. | Design only, per the owner's instruction. |
| Full cleanup, self-review, release tracking and governance | Static inventory covered all 152 tracked files at the earlier baseline. Checked entry points, selected dynamic paths and duplicates, removed confirmed unused code, and shipped the latest releases on main. | Complete the manual file-by-file and line-by-line review, inspect runtime/disabled paths and dependency coverage, and keep a per-file decision record. Keep priority, implementation, and verification status visible before reporting work complete. |

The earlier handoff also includes private Cloudflare activation, a real watch workout upload,
source coverage and calibration. Keep those separate from the current release check. Cloudflare
is optional, requires the owner's configured account and phone, and remains disabled by default.

## Claude suggestion checklist

The pasted briefs and review are the source for this mapping. The
[execution queue](../ROADMAP.md#detailed-execution-queue) owns sequencing and test gates.

| Suggestion | Status at v0.26.1 | Queue |
|---|---|---|
| Support newer Ollama models, detect capabilities, warm up once, separate reasoning, test and report model state. | Capability checks, local-only gate, warm-up, benchmark and CLI diagnostics shipped. The Mac's current install and broader recent-model compatibility have separate acceptance checks. | 01, 20, 24 |
| Give the narrator a freer voice with cited facts, reasons and only supported actions. | Checked clauses and reviewed original Today/Running observations shipped. A full explanation tied to the existing action and reasons across surfaces is unfinished. | 20–21 |
| Write a brief Sunday story with what improved, what slipped and the next focus. | The Sunday card exists and uses measured facts and the plan. AI-written wording and its dedicated tests are pending. | 22 |
| Show the last accepted AI time and the reason the feature is inactive. | The dashboard shows a count. It has no latest accepted timestamp or complete status reason. | 23 |
| Prioritize stable waking, improve bedtime gradually, and step back after repeated misses. | Wake-time anchor, consistency and follow-up shipped. The rolling proposal can hold. Persisting an accepted weekly target and a reproducible progression remains open. | 50 |
| Run a one-step bedtime experiment and link adherence to duration, score, HRV and readiness with honest sample limits. | Sleep has a shortfall scenario and general coaching. The linked experiment and recorded outcomes remain open. | 50 |
| Show sleep disruptor tags and compare how rested the owner feels to Garmin sleep scores. | Tag and rating paths shipped, including a minimum of 14 joined ratings and enough in both comparison groups. Validate coverage and usefulness on the Mac archive. | 03, 50–51 |
| Track planned vs done, adapt with a capped next week, set a personal movement floor, and use morning and evening ratings. | Shipped. Knee check-in can alter the next day's brief. End-to-end agreement between plan, run suggestions and experiment outcomes still needs testing. | 44, 51 |
| Add two knee-aware strength sessions and a concise evening stress/Body Battery reflection. | Strength plans can be logged. A tailored strength progression and the descriptive evening review have not been delivered. | 51 |
| Restore useful knee-aware cadence coaching and close the feedback loop. | Optional cadence trial and post-run checks exist. A consistently linked attempt, repeat, outcome and next action across the dashboard is unfinished. | 43–44 |
| Use a more glanceable design, reduce jargon and hide sparse or weak evidence. | Navigation, leading guidance, short definitions and several hiding/disclosure paths shipped. A full current-release sweep, especially both themes, sparse data, Patterns and phone performance, is still open. | 30–34 |
| Split the large dashboard module and consolidate governance. | Interaction JavaScript has a separate module and common agent rules were consolidated. Page-module boundaries and duplicated document sections have not been fully reviewed. Changes need caller and render evidence. | 14–16 |
| Verify the Mac's stale-build issue, release health, protected phone access and research provenance. | Local snapshot and version guards, replay tooling and documentation shipped. Current device rollout, archive coverage, and optional configured hosting need their own acceptance checks. | 00–05, 52–53 |
| Consider a morning digest or notification. | Concept only. Its timing, deduplication and privacy belong in the design record. | 52 |

## Running work left after v0.26

The release added a training block and effort charts, per-run form definitions and practical
checks, earlier matched ranges, a side-by-side pace/pulse half comparison, linked AI evidence,
and elapsed kilometre guides. That was an analysis of *recorded form*. It did not establish
whether a form change improves this owner's running. The open work is a Garmin/FIT comparison
on dated runs, source and cohort validation, pace-matched late-run mechanics, a per-metric
interpretation and cue map, and follow-up after a recorded attempt. The
[running queue](../ROADMAP.md#4049-deepen-running-before-expanding-the-advice) lists the required
evidence per step. Best efforts and durability claims remain separate evaluations.

## v0.27.0 follow-through

| Request | Delivered | Still open |
|---|---|---|
| Claude's Sunday and AI status suggestions | Evidence-linked Sunday wording, the existing rule fallback and the current model's status with last accepted time. | The live Qwen Sunday draft was withheld. Compare with thinking on the Mac and evaluate stronger prose and action reasons across surfaces. |
| One-step bedtime trial | A saved Monday target, gradual adjustments and dated comparisons of sleep, overnight HRV and Garmin readiness when enough measurements exist. | Review adherence and coverage on the owner's archive. A tailored strength progression and evening stress and Body Battery review are open. |
| Running depth and charts | Pace- and grade-matched late-run mechanics, thinner elapsed split guides, keyboard focus, consistent knee guidance, and stricter trial comparison counts. | Verify against Garmin on real runs and observe the full trial loop. Evaluate best efforts and durability independently. |
| Review and release | All 160 baseline paths have a review record, with dependency traces and repair evidence. Chromium and generated 36-month archive verification. | Mac, Safari, iCloud, optional protected hosting, private archive and other runtime checks in the execution log remain open. |

The [execution log](REPOSITORY_REVIEW.md#execution-log) records the order, evidence and
remaining verification by workstream.

### v0.27.1 repair

The live Sunday reproduction separated a missing citation from a model review that accepted an
unmeasured feeling. The repair groups the comparison, checks question premises before review and
records both stages. Live Qwen3.5 4B produced an accepted Sunday result after the five-minute
Linux thinking call fell back to direct drafting. The private Mac archive remains the acceptance
gate for usefulness and thinking speed. Running and ordinary scatter plots have smaller dots,
with touch and keyboard selection tested in both themes. [Model and UI verification](OLLAMA.md#verification)

## Earlier follow-up audit, 23 November 2026

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

The v0.26.0 pass shipped the interpretation layout, local model and prompt controls, and
the repository inventory in [the repository review](REPOSITORY_REVIEW.md). Three-year replay
passed against generated fixtures. The owner's original Mac archive and the complete manual
line review remain open. The [roadmap](../ROADMAP.md#repository-and-coaching-review) carries the
order of work.

## Running performance

The running redesign adds a four-week comparison, pace-and-pulse evidence, matched form
references, next-run checks, a separate local running review, and an elapsed kilometre
overlay. The [running roadmap](../ROADMAP.md#running-performance-review) tracks open
Mac archive validation, device checks and model quality.

## Dated health request, v0.27.4

| Request | Implemented | Remaining verification |
|---|---|---|
| Garmin source review and review handoff | [Garmin and research register](GARMIN_DATA_REVIEW.md) and [review index](REVIEW_START_HERE.md) | Owner payload coverage for detailed stress, Body Battery, naps and additional FIT fields |
| Heart rate and daily context | 15-minute pulse, spans and gaps, workout starts, prior-only check, raw source disclosure, day highlights | Verify the specific Garmin 44 bpm entry and signal agreement |
| Sleep shortfall and dated trends | Dated targets, coverage, average shortfall comparison and duration and score trends | Owner target coverage and browser pass on physical iPhone |
| Three baseline horizons | 28 days, 90 days and all earlier retained records on nine health metrics, with missing-date coverage | Test the owner archive after a full sync rebuilds the RHR mapping |
| Patterns and local thinking | Plain-language association followed by its evidence, and qualified sleep and pulse observations | Owner Qwen acceptance and usefulness in regularly synced dashboards |

## Garmin ecosystem review, v0.28.0

- Reviewed every supplied link in the original sequence. The evidence and license scope,
  implementation choices and deferrals are in the [decision log](GARMIN_ECOSYSTEM_REVIEW.md).
- Shipped aggregate archive inspection and timestamped wellness UI without new collection
  or model inference. Actual payload coverage and FIT file availability on the owner's Mac
  are independent acceptance checks. The Ollama output issue from the previous release is open.

## Running and coaching follow-through, v0.29.0

Closed in code: bar split view, desktop readability, Garmin bounds at the point of
use, a common glossary, a tested fallback for rejected/unfinished local AI prose,
targeted archive exports, additional Body Battery handling, per-feature ecosystem
follow-up and MIT attribution. Still open: the owner’s actual archive and Mac, the
iPhone performance target and wellness FIT import beyond the validated inputs.
