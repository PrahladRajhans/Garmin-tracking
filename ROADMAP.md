# Roadmap: the single main plan

**This file is the one plan.** Every other planning document is reference material that feeds
into it, and every item there is mapped to a phase here:
- `reports/Garmin connector feature research.md`: 34-feature backlog, referenced as **R1–R34**.
- `METRICS.md`: how each metric is calculated (Garmin vs science vs ours).
- `research_notes/.../FINDINGS.md`: research index and open questions.
- `MAC_SETUP.md`: deployment steps for the Mac.
- `CHANGELOG.md`: what shipped, per version.

## Current priorities

Reviewed 25 November 2026 through v0.32.0 against the owner's three tables and the earlier numbered
list. The sequence below maps all 14 items to acceptance criteria. Earlier execution IDs and
release decisions remain in the detailed queue. The [execution log](docs/REPOSITORY_REVIEW.md#execution-log)
distinguishes completed evidence from owner acceptance.

| Step | Combined item | Implementation and workspace acceptance | Owner or live acceptance |
|---|---|---|---|
| 1 | **1. Archive and 44 bpm** | Connect read-only local coverage, source tracing and the existing 36-month replay. A fixture distinguishes dated pulse from rolling, contradictory or absent source fields. Report usable sleep, stress, Body Battery and decoded FIT coverage separately. | Run against the actual Mac archive, verify the dated Garmin source of 44 bpm, and review any archive gaps. Use aggregate or explicitly selected results. |
| 2 | **8. Recovery freshness** | On Today and Recovery show the latest recorded dates, evidence the recommendation still uses, and states for incomplete sync, older data and unavailable readings. An incomplete fetch alone cannot explain why a measurement is absent. Test current, partial, stale and no-reading cases. | Compare watch sync, archive dates and visible cards for a recently synced day and a missing night. |
| 3 | **3, 4. Prepared and compact model evidence** | Prepare small, bounded records with an evidence ID, the comparison date or period, units, sample counts, personal reference and known limitations. Give matched pace/grade comparisons priority over raw streams. Verify ID stability, missing values and field limits. | Confirm meaningful support and realistic missingness on the actual archive. |
| 4 | **2. Coaching evaluation** | Fixed cases include low resting pulse, conflicting recovery signals and late-run form at matched pace/grade. Exercise missed evidence, incorrect direction, unsupported advice, generic next checks and overconfident explanations. Separate conformance from usefulness. | Use locally reviewed dated cases. Record model/tag, latency and accepted prose separately from checked-reading fallback. |
| 5 | **5, 6. Running, daily and weekly coaching** | Daily, post-run and weekly jobs have distinct evidence windows and outcomes. Post-run should pair a grounded observation with a plausible alternative and one comparable next-run check when evidence allows. Weekly should review that check before suggesting whether to keep or revise the plan. Verify sparse evidence and service outage behavior. | Review whether those decisions are worth using across Today, Sleep and Running on dated records. |
| 6 | **7. Recommendation changes** | Persist dated advice and the supporting evidence used at publication, compare with its predecessor, and expose which inputs moved or became unavailable. Cover same-date rebuilds and missing predecessors without fabricating a cause. | Confirm successive recommendations and their evidence after real scheduled runs. |
| 7 | **9. Qwen on the Mac** | Verify the operation guide and fixed cases against available fixtures and any local runtime. A recovered fallback cannot close acceptance of written coaching. | Qwen3.5 4B local-only latency, usefulness and accuracy across Today, Sleep and Running, including scheduled rebuild and failure recovery. |
| 8 | **10. iPhone and delivery** | Check phone-width and offline dashboard behavior and the protected publisher on fixtures. Preserve the no-hosting path and existing full-resolution archive. | On physical iPhone Safari verify navigation, scrolling and first-read time. If the owner chooses hosting, separately verify Access sign-in, Home Screen launch, and refresh after Ollama finishes. |
| 9 | **11. Wellness FIT preview** | Provide a local read-only preview for supported monitoring summaries. Count dated gaps, agreeing overlaps and disagreements with normalized data. Show unsupported messages and ambiguous date/unit handling before any write path. | Compare a representative wellness FIT with the Mac archive. Enable mutation only after preview results establish what will be filled and how conflicts are handled. |
| 10 | **12. Deeper wellness analysis** | Verify source formats, units, observation time and independent counts before turning naps or Body Battery charge/drain into comparisons. Only compare dated, matched evidence and keep missing intervals explicit. | Determine actual coverage on the Mac, compare against Garmin and verify whether correlations are useful in context. |
| 11 | **13. Workout previews** | Extend the existing dry run for intervals and progression runs. Check repeat structure, pace bounds and applicable capability evidence. Report unsupported or unknown device behavior separately. Test valid fixtures and invalid ranges. | Compare the preview with the target watch's supported workout features. Preview remains local and read-only with respect to Garmin. |
| 12 | **14. Wider repository audit** | Reconcile all tracked paths with the register, trace legacy and opt-in paths in dependency order, and record exact reviewed ranges and checks. Classify each unresolved candidate before consolidation. | Verify launchd, live sources and enabled publishing branches in the configured environment. |

**Dependencies and checkpoints.** Start archive preparation, static review, and browser/device
checks in parallel. Steps 2–3 establish the evidence contract for steps 4–7. Step 1 guides the
scope of steps 9–10. Step 11 can advance independently on fixtures. Review targeted tests as
each workstream lands, then run Ruff, the full Python suite, and affected replay/browser checks
once against the release commit. Keep cadence, bedtime, archive restore and publication retry
coverage from the earlier queue as regression checks where affected.

### Open after the Mac acceptance run (v0.32.1)

[What was checked](docs/OWNER_ACCEPTANCE_RESULTS.md). In priority order:

1. **Owner, security:** turn off Ollama's network exposure and confirm it listens on loopback
   only. Check data-folder permissions and set up a backup ([operations](docs/OPERATIONS.md#backups-and-rollback)).
2. **Done 25 November:** the stress timeline was backfilled from 1 July 2026. Garmin returned
   nothing for earlier days tried, so older intraday history may only exist in monitoring FIT files.
3. **Owner:** give the date and label of the 44 bpm reading; review the local AI report.
4. **Device:** the watch workout check (upload not approved yet). iPhone checks in Files,
   including VoiceOver and offline reopen, passed on 25 November. Safari and Home Screen launch
   wait on a hosting decision.
5. **Code:** Running and weekly AI reviews usually fail the direction check and fall back to exact
   readings. Improve the evidence wording or the prompt, and measure on dated cases.
6. **Code:** the dashboard file is about 4.9 MB against the 600 KB target. Most is inline SVG in
   collapsed detail sections.
7. **Code:** bedtime, experiments and event timing still use the configured timezone on travel
   days.
8. **Code:** import of monitoring FIT stays disabled until Body Battery message types, conflicts
   and rollback are validated.
9. **Code:** one AI pass right after a long sync ended incomplete and the next build finished it.
   Record why a pass is incomplete so this can be diagnosed.
10. **Code:** wider repository audit (separate task, step 14 below).

### 25 November execution status

| Step | Workspace evidence | Remaining acceptance |
|---|---|---|
| 1. Archive and pulse | The [owner acceptance checker](docs/OWNER_ACCEPTANCE.md) reports whether independently dated source records support the expected value, recent usable coverage and FIT inventory. A synthetic 36-month replay left its source unchanged and found no broken links or duplicate IDs. | Actual Mac archive, the exact Garmin date, the source of the reported 44 bpm, and agreement with Garmin Connect. |
| 2. Recovery freshness | Today and Recovery distinguish recorded days, incomplete sleep, an awaiting-sync state and data absent from the archive. Dated available readings and inputs to the recovery calculation are exposed. | Confirm watch sync timing and the resulting copy on the owner's device. |
| 3–5. Coaching, records and checks | Current work adds bounded post-run evidence with distinct pace/grade or earlier-run coverage, alternative interpretations, a repeat check, and fixed cue, pulse outlier, late-form and thin-data cases. Local deterministic guidance remains available when Ollama cannot select a check. Weekly follow-up revisits the cadence experiment and shows comparison coverage. | Review actual dated written output across Today, Sleep and Running. Verify real cadence follow-up and per-surface latency separately from selection fallback. |
| 6. Recommendation history | The dashboard saves the published recommendation and its evidence, and exposes the earlier evidence when guidance changes. | Inspect successive real publications. |
| 7. Qwen on the Mac | The owner checker confirms service settings and model capabilities. Local Qwen3.5 4B passed written interpretations of fictional Today, Sleep and Running evidence in direct mode. Thinking mode and its evidence fallback are measured separately. | Verify latency, accuracy and usefulness with the owner's archive and Mac. |
| 8. Phone and delivery | Near-viewport chart setup reduced initial Run-page chart initialization from twelve to zero on a synthetic 390 × 844 case. Chromium and WebKit exercised touch, keyboard, resize and fallback behavior. The publisher tests both the root and `/index.html` on production and preview. | Physical Safari navigation and load time. Verify protected publishing after configuring the service. |
| 9. Monitoring FIT | The default read-only preview separates gaps, overlap and conflicts. Use `--include-dates` for dated counts or `--retain` to keep a validated original locally by shared content hash without writing to SQLite. | Run against a representative owner's FIT and confirm what should be imported, how conflicts should resolve and how much usable coverage would be gained. |
| 10. Deeper wellness | Recovery compares prior completed-day Body Battery charge/drain across qualified groups. Sleep reports separately recorded nap totals and coverage. No missing value is counted as zero. | Confirm nap and charge/drain coverage and validate use in repeated recovery/running comparisons on the real archive. |
| 11. Workout preview | The local compiler can expose repeat counts, performed work, pace bounds and estimated time, with watch compatibility marked unverified. | Validate owner-device behavior after explicit upload and sync. |
| 12. Repository review | The [continuation audit](docs/REPOSITORY_REVIEW.md#25-november-continuation-audit) reconciles 173 baseline paths. The [post-v0.30.0 audit](docs/REPOSITORY_REVIEW.md#post-v0300-manual-audit) tracks manual ranges and fixture results. It verifies the corrected source-specific sync gate, overlapping refresh behavior, valid workout routing and the protected publisher preflight. | Continue the recorded manual review of remaining paths. Exercise the configured scheduler, sources and publishing on the owner's Mac. |

The [v0.32.0 follow-up](docs/REPOSITORY_REVIEW.md#v0320-manual-work-and-acceptance)
closes the reproduced grade, pulse coverage, missing-load, timestamp, import-log, and
archive provenance regressions. Equivalent 1 Hz and 5-second traces qualify for the same
graded comparisons. Charts expose exact readings and announce committed taps. Open
work, in order, is the real archive and representative FIT comparison, real scheduled
Qwen coaching, physical iPhone and protected delivery, then remaining renderer, CSS,
and legacy paths. Provenance for precedence between different overlapping export bundles
requires dependable export dates.

## Detailed execution queue

### Running chart legibility, metric meaning and coaching output

1. Replace the kilometre line with discrete bars against an explicit reference and keep exact
   recorded times accessible. Increase desktop type and chart scale while checking mobile,
   both themes, long runs, keyboard/touch selection and missing data.
2. Reuse one running-metric guide for dashboard and MCP. Verify Garmin boundaries, separate
   population bands from personal matched ranges, explain units and tradeoffs, and surface
   the guide at both the form numbers and timeline.
3. Reproduce the local model timeout and rejected output. Test a useful evidence-preserving
   alternative with actual Qwen when the runtime is available. Keep owner data outside replay.
4. Implement a further feature backed by exact external code, review each repository at the
   feature level, and record adoption or the test required before shipping a deferred item.
5. Add the MIT license and Prahlad Rajhans attribution. Trace the handoff from source to UI
   and model, run the closing checks and merge the tested head.

The v0.29.0 implementation follows those steps. The source paths and checks are linked
from [the independent review](docs/REVIEW_START_HERE.md). Owner data, physical iPhone
performance, and model performance on the Mac remain separate acceptance items. The
ecosystem ledger records which future improvements need representative inputs and tests.

### Garmin ecosystem review and implementation

1. Open all 40 supplied entries in order, resolving duplicates and recording terminal states,
   upstream revisions, source links and licensing. Confirm the promising behavior in code or
   tests. Read public community discussions for questions real users ask, with repository
   evidence for each technical decision.
2. Compare adoption candidates against the current on-device archive, regular sync, read-only
   analysis and offline dashboard. Rank by value to the athlete, source coverage, reversibility
   and verification cost. Keep data transport, ingestion and derived analytics distinct.
3. Implement the highest-ranked changes through normal entry points. Require dated evidence,
   explicit unavailability and a focused test for each new failure mode.
4. Review what was adopted and why, run the end-to-end suite once, and merge the tested commit.
   Record which checks depend on the owner's archive or live Garmin access.

The first two decisions shipped in v0.28.0. The owner's Mac audit is the next gate for
confirmed coverage and visible day charts. Only then compare wellness FIT reconciliation,
local CSV and AI coaching benchmarks using the [decision log](docs/GARMIN_ECOSYSTEM_REVIEW.md).

### Evidence-first health dashboard

1. **Research first.** Trace the 955 manual, Garmin Health/FIT surfaces, Garmin's measure
   definitions, Bevel’s sleep framing, and independent sleep and pulse evidence into a source-to-field register.
2. **Explain daily readings.** Use actual timestamped samples, median/min/max and coverage.
   Keep gaps, use the athlete’s local dates, and explain what the device’s resting estimate means.
   Add a signal check with a prior personal reference and a practical verification step. Use prior
   28-day, 90-day and all-earlier archive windows, including exact sparse gaps.
3. **Explain sleep over time.** Put target gaps and coverage up front, compare equal lookback
   windows, and make dated nightly evidence and trends usable at mobile width. Missing or
   incomplete records cannot count as no debt or contribute to the baseline.
4. **Improve the interpretation layer.** Feed qualified anchored evidence to the local model.
   Keep measurements and any low-pulse guidance available offline and generated by rules.
   Explain the direction, unit and limitation of associations before plotting them.
5. **Verify and document.** Extend regression tests, replay a generated 36-month archive, check
   key mobile and desktop charts in both themes, and make formulas, sources, boundaries and
   workflows reachable from the third-party review index. Owner archive and physical iPhone
   checks are separate from the fixture gate.

The implementation covers the requested paths in [v0.27.4](CHANGELOG.md#0274---2026-11-25).
Acceptance checks and owner-only gates are in [the reviewer guide](docs/REVIEW_START_HERE.md).
Next, run the owner’s local replay, reconcile 44 bpm against its dated source, and sample
stress, Body Battery and nap payload coverage for future cross-metric timelines.
See [the source register](docs/GARMIN_DATA_REVIEW.md) for the decision gates.

**Hosted dashboard freshness.** Reuse the opt-in Pages publisher after a guarded Ollama
rebuild. Serialize uploads, stage the latest complete local file, and record successful
publication so skipped Garmin syncs can retry failures without repeat deployments. Verify
worker ordering, failure recovery and publishing-disabled behavior with a fake provider.
Live hosting and iPhone sign-in remain separate rollout checks.

**Chart readability.** First separate series identity from Garmin bands and goal status.
Then make sparse comparisons readable without selecting individual points, and add overlays
only where readings share a date or elapsed time. Review timelines, trends, bars and scatter
plots at phone and desktop widths in Light and Dark, with split guides and offline values.
Use the fixture checks for release and keep physical iPhone Safari acceptance open.

**Ollama repair after v0.27.0 (20–24).** First reproduce the rejected Sunday output on
fictional data and distinguish a draft failure from review rejection. Next supply each
comparison and its baseline together, and give the model a bounded correction when the
draft or review fails. Keep exact metrics, dated links, local-only transport, deterministic
guidance and snapshot guards. Then verify direct and thinking mode on the fictional Sunday,
recovery and Running cases, including invalid output and outage behavior. Record separately
what needs the owner's Mac. Release only after both Python checks pass.

The [request audit](docs/PROGRESS_AUDIT.md#claude-suggestion-checklist) records the outstanding
Claude suggestions. The [repository review](docs/REPOSITORY_REVIEW.md#dependency-and-failure-paths)
records what changes affect downstream. The [file register](docs/repository-review-queue.tsv)
is the file-by-file work record. The IDs below are the implementation sequence. See the
[execution log](docs/REPOSITORY_REVIEW.md#execution-log) for completed work and remaining acceptance.

Execution began 24 November 2026 from `aa14346` using Python 3.12.14. The first slice
reviews source requests, retained activity evidence, and the old-database path. Its gate
checks two-source sync, a failed detail retry, and repeated sync without duplicate requests.
The next slices use the same baseline to compare AI, chart and coaching behavior. The private
Mac archive and device steps remain open. Completed evidence goes in the
[execution log](docs/REPOSITORY_REVIEW.md#execution-log).

### 00–09. Establish a baseline and verify what is deployed

| ID | Pending work | Evidence required |
|---|---|---|
| 00 | Capture the reviewed commit, clean checkout, runtime versions, entry points and flags. | Pin the fixture versions, current test results, release reference, and pre-change visual samples. Reconcile every tracked path with the file register. |
| 01 | Confirm the Mac's scheduled job uses the intended checkout, virtual environment and archive. Check the v0.26.1 default migration and model availability. | One scheduled run identifies code version, database path and local-only status. Check an enabled record using the old default and an explicitly selected alternative model. |
| 02 | Verify full sync and skipped-fetch behavior. Follow the timestamps for data, local HTML, and the iCloud copy. | A complete sync advances freshness. An incomplete sync remains visible and retries. A skipped fetch can still rebuild and retry pending AI. Compare each destination's version and timestamps. |
| 03 | Run read-only archive replay, timing checks, and coverage on the three-year Mac history. | Document which months, valid sleep nights, runs with FIT and dynamics fields, and matched pairs are actually available. Review a small set of Garmin comparisons and outliers. No public data export is needed. |
| 04 | Verify restore using a disposable database/FIT copy. | Restore both together and regenerate a dashboard. Check file paths, revisions, source data and incomplete sync behavior. |
| 05 | Open the resulting snapshot in Mac Safari and iPhone Safari/Files or the configured private path. | Open Today → Sleep → a dated night and Running → a run → split and form details. Record which copies are readable and current. Protected hosting verification applies only if already configured or approved. |

The static and fixture work below can advance if owner-device results are pending. Keep device
acceptance open and label any findings derived from fixtures.

### 10–19. Review every file, in dependency order

| ID | Pending work | Evidence required |
|---|---|---|
| 10 | Review sync, source adapters, auth, pagination, retry/backoff, and date windows. | Map scheduled, force, no-update, skipped-fetch, and partial-source paths. Verify loop progress, timeout, local dates, and the next-run retry condition. |
| 11 | Review SQLite, FIT, import and normalization. | Trace source priority and writes, old schema and upgrade behavior, stale/missing/invalid values, atomic FIT replacement, deduplication, and revisions. Exercise incomplete import/reparse, rollback and an existing database. |
| 12 | Review analytics and formula sources across Recovery, Sleep, Training, goals, Running, and sport/conditions analyses. | Record units, sign conventions, time windows, min samples, prior-only evidence, profile/settings use and agreement checks. Track each change back to `METRICS.md`. Identify duplicated definitions and assign ownership before refactoring. |
| 13 | Review recommendation and AI inputs, trial and check-in state, work queues, retries, cache and setting changes. | Trace both ordinary and thinking calls, cloud-off gate, result states, snapshot replacement, cancellation, fallback scope, and local memory retention. Review dynamic entry points and disabled/opt-in paths. |
| 14 | Review renderers, shared chart and navigation code, exports and optional publishing. | Check that script hash, fragment IDs, links, background rebuild, stale copies, desktop and phone access roles remain consistent. Record which HTML sections and tests each shared helper affects. |
| 15 | Review every CLI/MCP registration, platform integration, config/example, dependency, test, doc and asset. | Record invoked entry points as well as imports, user docs, launchd and optional CLI workflows. Classify historical evidence with its provenance. Compare test presence with actual branch coverage. |
| 16 | Remove or consolidate confirmed dead or duplicate code in small changes. | For each candidate record callers, runtime checks, decision and test evidence. Preserve exercised or documented entry points. Re-run the affected entry points after changes. |

### 20–29. Finish the local coaching and status work

| ID | Pending work | Evidence required |
|---|---|---|
| 20 | Map each AI display and its eligibility: Today, Sleep, Recovery, Training, Sunday, experiments, Running, FIT-run and workout detail. | Per-surface matrix of present/absent data, disabled, pending, timed out, withheld, accepted and current-snapshot behavior. |
| 21 | Add approved reasons and actions to the evidence contract. Let Qwen3.5 explain a real trade-off and suggest one useful next measurement. | Cite evidence per claim, including a verified reason for a causal-sounding statement or existing action for advice. Keep refusal and deterministic fallback. Test invented numbers, unsupported advice, incorrect direction and invented causes separately. |
| 22 | Finish the reviewed AI Sunday story. Reuse completed weekly facts and the existing plan. | In a covered week, show what improved, what slipped and one focus. Missing or rejected output leaves the current rule-written review usable. Test week rollover and missing data. |
| 23 | Finish status feedback in the footer and diagnostics. | Show last accepted time and a concise reason when results are pending, unavailable, disabled or withheld. Distinguish sync freshness, build time and AI freshness. Exercise CLI and offline HTML using the same state. |
| 24 | Test standard and thinking Qwen3.5 paths and whether carry-over helps. | Compare relevance, factual correctness, actionability, latency, validation reasons and successful coverage. Use fictional cases and dated held-out local records where available. Confirm old evidence cannot replace new observations or override dated values. Benchmark alternate tags separately. |

### 30–39. Make both themes readable across the whole dashboard

| ID | Pending work | Evidence required |
|---|---|---|
| 30 | Audit contrast and text hierarchy in Light and Dark. Cover page and card backgrounds, muted text, small labels and links, chart axes, focus, status badges, split guides and overlays. | Measure rendered pairings. Target WCAG AA contrast of 4.5:1 for normal text and 3:1 for large text, and 3:1 for meaningful graphical cues and controls. Use text, marker shape or line style where colour alone carries meaning. |
| 31 | Review page flow one page at a time: Today, Sleep, Recovery, Training, Running, run/workout detail, Body, Patterns and History. | Each page has a clear first reading and a useful next link. Check redundant instructions, jargon, dead ends, duplicated charts and sparse states. Exact values remain available for each priority chart. |
| 32 | Check interactive and offline paths. | Test 320, 390, 768 and 1200+ px, both themes, keyboard, touch/scroll, back navigation, disclosures, JavaScript off, sparse data and extended history. Check active navigation and evidence fragment targets in HTML. |
| 33 | Profile dashboard size and input responsiveness on a trace-heavy fixture and the real snapshot. | Identify whether duplicate markup, SVG layers, older detail or link depth drives the cost. Preserve downloaded FIT, actual split times and recent chart resolution. Record before/after size, load and interaction. |
| 34 | Retest real Safari and iPhone after rollout. | Verify chart and comparison legibility, scroll, disclosures, orientation, and theme rendering. Capture one representative light and dark state per affected page where feasible. |

### 40–49. Deepen Running before expanding the advice

| ID | Pending work | Evidence required |
|---|---|---|
| 40 | Validate absolute values and source coverage for cadence, stride length, ground contact, vertical oscillation and vertical ratio. Include absent power/balance fields and estimates wherever applicable. | Compare full FIT, Garmin session/lap views, MCP and dashboard on dated examples. Record units, sensor type, missingness and which values are derived. Wrist and accessory metrics stay distinguishable. |
| 41 | Audit how similar runs and fallback personal pace fits are chosen. | Show included and excluded candidates, prior-only date handling, comparable pace, duration, climb, type, quality and sensor coverage. Inspect confounding by surface, terrain or conditions where recorded. Verify thin cohorts stay inconclusive and pace fits stay within their observed range. |
| 42 | Add a within-run mechanics analysis design. Test whether cadence, contact and bounce change late in the run at comparable pace. | Define comparable early/late segments and minimum usable coverage, with rules for stops, hills, intervals and gaps. Check repeated runs. Existing side-by-side half data measures pace and pulse, so the mechanics result needs its own acceptance case. |
| 43 | Build a recommendation/evidence map per metric, including cadence and stride together, ground contact and surface, and oscillation relative to step length. | Separate measurement, plausible interpretation, what to try, and what to observe on a comparable repeat. Test advice for improvement, unchanged and inconclusive outcomes. Verify the effect of knee check-ins on relevant recommendation surfaces. |
| 44 | Complete the feedback loop: suggestion → attempt → comparable repeat → explicit outcome → next check. | Use existing trial plumbing where it fits. Link dated attempts and comfort check-ins, and display when the baseline or repeat is too thin. Application state remains reproducible on historical replay. |
| 45 | Verify split boundaries and practical chart use on real workouts. Evaluate best efforts or durability later as separate proposals. | Include stops, partial last kilometres, distance resets, treadmill, hills, point thinning, multiple overlays and no-data states. Gate new best-effort or durability claims on demonstrated coverage. |

### 50–59. Close the remaining Claude requests and release each slice

| ID | Pending work | Evidence required |
|---|---|---|
| 50 | Make the bedtime experiment persist across weeks, including target acceptance, adherence and step-back. | Link the experiment to dated outcomes. Handle midnight, sparse valid nights and missed targets. Show measured sleep duration, score, HRV and readiness wherever available. Label uncertainty instead of attributing a cause. |
| 51 | Verify planned-vs-done and optional check-ins through the whole coaching path. Evaluate the earlier strength and evening review proposals. | Test activity matching and caps, repeated or partial sync, pause and next-day behavior, existing optional strength tracking, and what any evening stress/Body Battery observation can support. |
| 52 | Close competitor traceability and retain messaging as a design record. | Link features to verified research. Recover the original AthleteData item labels or record the ambiguity. Signed-in product comparisons need authorized access. Keep inbox and notifications as design, including privacy, quiet hours and deduplication. |
| 53 | Ship narrow slices in dependency order and record results. | Before each slice, record intended outcome, touched files, impact paths, test matrix and rollback. Run focused and full tests, lint, and applicable fixture/replay/browser checks. Verify both Python versions on the exact PR head, then merge when authorized. Record release and main CI, plus Mac/phone status where applicable. |

Use one [changelog](CHANGELOG.md) entry per meaningful change. Update the [handover](HANDOVER.md)
and [README](README.md) for workflow or capabilities, [metrics](METRICS.md) and research
notes for calculations and sources, the [dashboard plan](DASHBOARD_PLAN.md) and
[UI review](docs/UI_REVIEW.md) for visual changes, and
[Mac setup](MAC_SETUP.md), [operations](docs/OPERATIONS.md), or
[Ollama guidance](docs/OLLAMA.md) for rollout and AI changes.

## Goal
A free, private connector that gives Claude everything a Forerunner 955 records, plus
transparent analysis on top. Five uses: race training · recovery/readiness · health trends and
a full health snapshot · per-workout coaching (what each metric means, how to improve) ·
fitness age with next steps. AI-written insights in the style of Strava's "Athlete Intelligence"
and Garmin's "Active Intelligence" (Connect+) come from Claude narrating the numbers our tools
compute: activity recaps, daily brief, weekly review.

## Decisions (fixed unless you change them)
- Runs on your Mac: sync → local SQLite → MCP server for Claude Desktop. Development and testing
  happen in the cloud session.
- Sources, in priority order: official Personal API > unofficial `garminconnect` (extras only)
  > Garmin account export (history). Strava is excluded (API terms ban AI use).
- Garmin's own scores and our calculations are stored and shown side by side, never blended.
- Watch only, no chest strap. Wrist running dynamics are available (verified on FIT data;
  firmware 15.09+). Lactate threshold may be missing without a strap → we estimate from runs.
- Every derived number carries its inputs and a one-line meaning. No ACWR "injury risk".
- Every change: tests + `garmin-mcp-verify` + CHANGELOG + README.

## Data sources (all live in one database)
| Source | What it provides | History | State |
|---|---|---|---|
| Official Personal API | Daily summary, sleep, HRV, all-day HR, SpO2, fitness age (daily); Body Battery, stress, steps, hydration, VO2max, weight, HRV and sleep summaries (28-day windows); activities + FIT | ~1 yr per endpoint | ✅ working; rate limit ~100 req/window handled |
| Unofficial garminconnect | Training readiness/status, max metrics, respiration, intensity min, BB events, acclimation, floors, race predictions, endurance/hill score, lactate threshold, body comp; activity splits/zones/weather | full | ✅ working on the Mac (the cloud session has no login) |
| Account export | Daily summaries, sleep, health status, readiness, training status, race predictions, endurance/hill, acute load, VO2max, acclimation, hydration, abnormal HR; profile, zones, PRs, workouts, gear; all activities + FIT | May 2024 → Nov 2026 | ✅ imported and cross-checked |
| FIT files | 1 s HR, pace, cadence, power, altitude, temperature, GCT, vertical oscillation, step length, laps | per activity | ✅ parsed (116 activities) |

## Versions
| Version | Content | State |
|---|---|---|
| 0.32.1 | Fixes from the first Mac acceptance run | [Results](docs/OWNER_ACCEPTANCE_RESULTS.md) |
| 0.32.0 | FIT grade parity, pulse and load coverage, archive chronology and provenance, exact chart readings | [Review and acceptance](docs/REPOSITORY_REVIEW.md#v0320-manual-work-and-acceptance). |
| 0.31.0 | Reviewed Sleep prose, archive and FIT safeguards, partial-date rendering, refresh serialization and broader manual review | [Audit coverage and remaining dependencies](docs/REPOSITORY_REVIEW.md#post-v0300-manual-audit) and [owner acceptance](docs/OWNER_ACCEPTANCE.md). |
| 0.30.0 | Dated recovery evidence, cadence follow-up, recommendation history, FIT and workout previews, owner acceptance and phone chart loading | Workspace checks and remaining owner acceptance are in the [execution status](#25-november-execution-status). |
| 0.29.0 | Running charts, contextual metrics, Ollama fallback, archive CSV and licensing | Implemented |
| 0.28.0 | Ecosystem review, archive audit and intraday wellness charts | Implemented |
| 0.27.4 | Dated health evidence, sleep shortfall and archive windows | Implemented |
| 0.1.0 | Scaffold, 4 live tools | done |
| 0.2.0 | Phase 1: SQLite sync engine, FIT parsing, official + unofficial sources | done |
| 0.3.0 | Phase 2: export importer, tidy tables, health snapshot, DB-backed tools | done |
| 0.3.1 | Data-quality pass: unit fixes + `garmin-mcp-verify` | done |
| 0.4.0 | Phase 3: recovery & readiness + daily brief | done (merged to main) |
| 0.5.0 | Phase 4: training load & performance + weekly review | done |
| 0.6.0 | Phase 5: workout coaching (running first) + activity recap + fitness age levers | done |
| 0.7.0 | Phase 6: memory, goals, provenance | done |
| 0.8.0 | Phase 7: workouts to the watch | done (upload untested until the Mac setup) |
| 0.9.0 | Phase 8: insight engine, levels 1–3 | done (core); see status per item |
| 0.10.0 | Phase 9: dashboard | done |
| 0.11.0 | Phase 10a: daily scores (Recovery %, Sleep %, Strain), bedtime; self-update; CI | done |
| 0.12.0 | Phase 11: dashboard v2 (multi-page) + Phase 12: sleep breakdown, HR dip, activity status, pace of ageing, marathon shape, shifts, monthly report, running breakdown; sync gate | done |
| 0.13.0 | Phase 13: correlations explorer, test-run tracking, recovery weighting study | done |
| 0.13.1 | Private hosting preparation (off by default), constant-signal crash fix, continuation review | merged PR #8 after CI; hosting activation/device checks pending |
| 0.13.2 | Sync completion/retry, local dates, updater recovery, loop guards | merged in PR #9 after both CI jobs passed |
| 0.13.3 | Sleep/data sufficiency, HR interpretation, study pairing, input validation | merged PR #10 after both CI jobs passed |
| 0.14.0 | Exact FRIEND VO2max reference bar, source transcription and tests | merged PR #11 after both CI jobs passed; live profile check pending |
| 0.14.1 | Dashboard accessibility, current-day ranges, atomic/private files and provenance | implemented; CI/merge evidence recorded in GitHub PR |
| 0.14.2 | Run pacing drill-down, timestamp-based timing, elapsed splits and Garmin timer evidence | Merged in PR #13 after both CI jobs passed |
| 0.14.3 | Monthly coverage drill-down, pattern evidence, mobile navigation, archive comparison command | Implemented and checked with synthetic data |
| 0.15.0 | Direct chart controls, visible findings, training/sleep context and theme switch | Implemented with phone and laptop browser checks |
| 0.15.1 | Smaller chart cursor, smoother scrub and scroll, environmental feasibility note | Checked in browser, no environmental data collection |
| 0.16.0 | Personal signal context, date drill-downs and two run overlay trials | Browser and synthetic data checks |
| 0.17.0 | Matched effort evidence, readiness benchmark, saved weather and optional local timed conditions | Synthetic checks completed; archive, device and hosting checks pending |
| 0.18.0 | Week-ahead coaching, calibration gate and lighter daily history | First action and underlying evidence verified on synthetic records; Mac scheduled rollout pending |
| 0.19.0 | Today-first coaching, five navigation tabs, true-unit workout comparisons and HTML refresh repair | Browser and synthetic checks; Mac and real iPhone acceptance pending |
| 0.20.0 | Measured workout and bedroom comparisons | Local coverage validation and automatic provider retrieval remain open |
| 0.21.0 | Experiment follow-up, slimmer HTML and opt-in run weather and AQI | Merged in PR #25 |
| 0.22.0 | Optional on-Mac Ollama narrator with inspectable, deterministic facts | Local and mocked verification; owner Mac and iPhone acceptance pending |
| 0.23.0 | Responsive charts, single-page runs with selectable overlays, workout narration and paired conditions evidence | Synthetic viewport and data checks; owner coverage and physical-device check pending |
| 0.24.0 | Local AI diagnostics and evidence checks, guidance changes, post-run reviews, sleep summaries and timing plan, mobile navigation | Mac Ollama, launchd, iCloud and iPhone acceptance pending. See [handover](HANDOVER.md#latest-changes-for-reviewers) |
| 0.25.0 | Model evaluation, wake follow-up, Sunday review, journal, planned vs done, route replay | Synthetic and local inference checks passed. Mac archive acceptance pending. |
| 0.26.0 | Running dashboard, matched dynamics, split guides, local running review, archive replay and revision retention | Merged and published. Browser, synthetic archive and local checks recorded in [PR #31](https://github.com/PrahladRajhans/Garmin-tracking/pull/31). |
| 0.26.1 | Qwen3.5 4B default and one-time upgrade of the former default | Merged and published. 234 tests, CI, and five fictional routine summaries accepted on local Ollama. Mac acceptance open. [PR #32](https://github.com/PrahladRajhans/Garmin-tracking/pull/32). |
| 0.27.0 | Running form by comparable halves, weekly bedtime trial, Sunday AI and status, source/archive repairs and file audit | See the [execution log](docs/REPOSITORY_REVIEW.md#execution-log) and [PR #33](https://github.com/PrahladRajhans/Garmin-tracking/pull/33). Mac and private archive acceptance remain open. |
| 0.27.1 | Citation repair, reviewed draft correction, Ollama attempt diagnostics and smaller dense chart markers | See [model evaluation](docs/OLLAMA.md#verification) and [PR #34](https://github.com/PrahladRajhans/Garmin-tracking/pull/34). Mac reasoning latency and real-data acceptance remain open. |
| 1.0.0 | All of the above running on your Mac with scheduled sync | |

## Done (traceable to the backlog)
R1–R6 ingest, store, FIT, sync, `refresh_data` · R8–R10 day/sleep/activity tools · R12 trends ·
R13 coverage · R27 unofficial adapter · R28 export importer · health snapshot · cross-source
verification · research (competitors, FR955 metrics, formulas, integrations) with a verification
pass on Garmin labels (`VERIFICATION_LOG.md`).

## Phases ahead (in order)

### Reliability, evidence and usability review (owner request, 23 November)

This review extends A–D without changing the exclusions or adding unverified scores.

| Order | Front | Changes to implement and validate | Status |
|---|---|---|---|
| 1 | Operations | Record completed syncs instead of individual successful requests; use athlete-local dates; guard pagination/chunk loops; stop/retry safely after dependency-install failures; run CI on topic branches | merged PR #9 after CI; actual Mac rollout pending |
| 2 | Accuracy | Align sleep fallback/baselines, UTC and advice; repair study sampling/zero handling; validate workout/override inputs | merged PR #10 after CI; weights unchanged |
| 3 | UI/UX | Honest empty states, elapsed-date charts, readable contrast, keyboard focus, touch targets, accessible chart values; test phone/tablet/desktop and dark mode | implemented v0.14.1; 276 browser states checked; device checks pending |
| 4 | Evidence and rollout | Source-backed research ledger, realistic synthetic regression checks, synced documentation, PR/CI/merge and actual Mac/phone checks | network access restored; PR #8 merged after both CI jobs passed; live device checks remain pending |

Primary VO2max Table 3 retrieval is complete (PR #11). Deferred research: re-check statistical calibration and formula
sources against full papers, benchmark competitor workflows with actual captures. Do not invent
norms, alter recovery weights, label correlations causal, or expose a cloud MCP endpoint before
an authentication/authorization and private-data deployment design has been verified.

### Analytics and dashboard follow-up (23 November)

| Order | Deliverable | Evidence needed |
|---|---|---|
| 1 | Run timing and pacing evidence (v0.14.2) | Known-speed/HR, sparse timing, pauses, partial kilometres, link navigation and Garmin session-field mapping |
| 2 | Monthly drill-down and pattern evidence (v0.14.3) | Coverage and missing months shown. Patterns fit gated by existing rule. Six widths and both themes tested |
| 3 | Historical validation on the Mac | Run the existing data-quality verifier plus `garmin-mcp-verify --run-timing` on the archive. Review paired counts and outliers before interpreting agreement |
| 4 | Phone deployment | Verify protected preview and production, owner login, dashboard drill-down and next scheduled update |

Later review: independently verify remaining load/VO₂ conversion references, benchmark
competitor flows where available, and test patterns on held-out blocks before introducing
predictive recommendations. Date blocks in current inference are consecutive paired observations.
Sparse weeks, wear time, watch changes and selection of similar runs can bias estimates.

The Mac holds the original Garmin history and account access. Synthetic checks can validate
individual formulas, mappings and edge cases. The recorded agreement figures are historical
until the owner dataset is checked again.

### Paid coaching research and local delivery

[Feature evidence and design decisions](research_notes/Garmin%20connector%20feature%20research/paid_coaching_2026-11.md).
v0.25 implements model diagnostics and fictional evaluation, cited wording, Sunday review,
wake follow-up, a sleep journal, private check-ins, a movement baseline, planned-vs-done and
same-route replay. The Mac acceptance check is to run the fictional evaluation locally, rebuild the
dashboard, and compare the plan and recorded links against real coverage. The existing local inbox
concept remains a future option. Live tracking, medical-sensor features, nutrition and 3D terrain
need separate product and data decisions.

### Repository and coaching review

1. Inventory the tracked tree and its entry points. Classify release code, tests, operations,
   governance, research and historical screenshots. Record evidence of use before removing code.
2. Locate the owner archive and verify access. Use read-only source access and disposable output.
   Separate historical checks from fixtures, browser checks and local inference benchmarks.
3. Make the insight time budget, writing style and model configurable. Keep model residency
   separate from a small, local memory of previously reviewed evidence.
4. Improve the insight experience with the selected lens, linked readings and an explicit
   evidence comparison. Keep deployment, model quality and full manual audit status visible.
5. Verify the service entry points, cache invalidation, disabled paths and the dashboard.
   Record findings, decisions, and remaining evidence in [the repository review](docs/REPOSITORY_REVIEW.md).

The tracked-file inventory, verified cleanup, local coaching controls and Today layout are
implemented. Next, review the remaining modules in runtime order: sync and normalization,
analysis, dashboard and export, then Mac and publishing operations. Log the entry point and
test for each proposed removal. On the Mac, replay the real archive and compare the reviewed
answers on the fictional cases with the selected Qwen3.5 default. Check that each answer
connects readings, distinguishes an exception from a trend, and leaves a useful next
measurement. Then validate the chosen model through a scheduled refresh and check its
evidence links on the phone.

### Running performance review

1. Research running dashboards and distinguish recorded effort, pace stability, changing heart
   rate, and running dynamics. Record source decisions and where each method applies.
2. Build calendar-based training comparisons from the archive and an inspectable effort chart
   from qualifying FIT runs. Derive one action from the strongest available evidence.
3. Give Running its own local coaching prompt and a separate evidence review. Verify sparse
   history, indoor runs, stale snapshots, reference windows, model rejection and link targets.
4. Test the running view and linked run details at phone and desktop widths. Once Running
   passes, apply a small visual improvement to a shared dashboard element.
5. Update governance and release notes, run local and hosted checks, and merge the reviewed
   release to main. Track Mac archive and live model acceptance separately.

The v0.26 implementation covers the dated block, effort evidence, form comparisons and checks,
four-week coaching, local running prompt, and native split overlays. The shared follow-up explains
load and HRV in place and marks the active chart reading more clearly. [Source decisions](research_notes/Garmin%20connector%20feature%20research/running_performance_2026-11.md).
Open acceptance tasks are the private-archive coverage and wider model benchmark, followed by
Safari and phone checks. Consider best efforts or durability scoring after those checks.

### Local reasoning follow-up

- Add an opt-in daily interpretation across measured signals, with a testable question and
  inspectable sources. Keep guidance deterministic and reason about evidence separately.
- Qwen3.5 4B became the default in v0.26.1 at the owner's request. Verify real archive
  quality on the Mac and benchmark larger tags as optional settings.

### Coaching and Sleep follow-up

1. Preserve the current working tree and the Mac's local-only inference boundary. Record changes
   in published guidance, and turn a qualifying matched run into an evidence-linked next check.
2. Replace chart prompts with readings. Make Sleep a night-first view with week, month and
   year context. Add a stable wake anchor, an inspectable bedtime step and a shortfall scenario.
3. Give the local model eligible cross-signal findings to prioritize while Python owns claims
   and actions. Verify repeated builds, insufficient data, stale syncs, links and narrow layouts.
4. Messaging concept: a private, opt-in digest containing one reviewed change and a link to
   the local dashboard. Design a local inbox with deduplication by snapshot and finding;
   evaluate generic push alerts with quiet hours and private links only after checking delivery
   time and notification fatigue. Keep health details inside the dashboard. Implementation
   remains outside scope unless the owner asks for it.
5. v0.25 saves dated sessions, compares completed activities and displays sleep journal evidence.
   Verify real archive coverage and establish bedtime experiment outcomes before extending automation.

### Athlete intelligence follow-up

The current local-AI and dashboard work follows this sequence through device acceptance:

1. Verify the narrator on synthetic records across Today, Recovery, Sleep, Training, experiment,
   FIT-run and workout detail. Cover opt-in, unavailable service, invalid model selections, sync
   retry, and concurrent snapshot replacement. Keep the source rows visible.
2. Verify the dashboard's links, reading order, charts, keyboard controls, and scrolling in both
   themes at phone, tablet and desktop widths. Audit missing-data states and the saved HTML stamp.
3. Validate the Mac checkout used by launchd after rollout. Check `garmin-mcp-narrator --check`
   against the archive, let a scheduled run exercise the skipped-fetch path, and reload Safari.
   Compare local and iCloud snapshots and open key charts and activity links on the physical iPhone.
4. Measure cold and warm inference on the Mac and test priority choices against dated records.
   Before widening the model's scope, review where it picked weaker evidence or lacked coverage.
   Profile the saved dashboard on the phone before changing the chart or history retention limits.

| Order | Deliverable | Evidence needed |
|---|---|---|
| 1 | Daily briefing, personal signals and History | Verify dated raw readings, resting pulse trend/range, overnight breathing and Pulse Ox, and coverage at each time scale |
| 1a | Optional run overlay trial | Check cadence/step length and speed/HR on comparable real workouts. Seek feedback before broader rollout |
| 2 | Verify daily guidance and run comparisons on the Mac archive | Compare with dated Garmin records and inspect missing nights, unusual runs and completed syncs |
| 3 | Weekly coaching priorities and training response | v0.18.0 offers a conservative weekly start and optional cadence trial. Next, record what was tried and how it felt, and compare later efforts on similar terrain and pace before interpreting results |
| 3a | Finer workout detail across sports | Expand older activity traces and sport-specific comparisons after real-data review. Test route matching from full paths before claiming the same route |
| 4 | Feedback from iPhone and laptop use | Check Files preview and Safari, adjust the most-used interactions, verify private phone delivery |

[Request audit](docs/PROGRESS_AUDIT.md) and
[owner reference review](research_notes/Garmin%20connector%20feature%20research/owner_reference_review_2026-11.md)
record sources and checks. Competitor benchmarks guide which questions to answer. Proprietary recovery algorithms
and device-only measurements are separate evidence. Report matched coverage and the
limits of wrist HR, HRV, and training comparisons before expanding coaching claims.

### Environmental context

[Weather, air quality and sleep feasibility](research_notes/Garmin%20connector%20feature%20research/environmental_context_feasibility.md)
records sources and trial criteria. v0.17.0 shows existing Garmin snapshots and optional
source windows supplied locally for outdoor runs. Next, corroborate local Indian station
coverage and reporting windows using public stations, then assess opt-in coarse-location
fetching and separately validate any training interpretation. Indoor sleep exposure needs
its own input and validation.

### Phase 3: Recovery & readiness → v0.4.0 ✅ done (all items 3.1–3.6)
| ID | Item | Backlog/source |
|---|---|---|
| 3.1 | HRV baseline: ln RMSSD, 7-day mean vs 60-day normal range (SWC band), CV trend | R17, METRICS §Recovery |
| 3.2 | RHR, respiration, sleep baselines (z-scores) + sleep debt and bedtime consistency | METRICS §Recovery |
| 3.3 | Transparent readiness: component z-scores, shown next to Garmin's readiness and factors | R18 |
| 3.4 | Illness/strain flag: ≥2 of HRV↓, RHR↑, respiration↑ for ≥2 days | R25 (part) |
| 3.5 | Daily brief ("morning report"): readiness, what's driving it, today's suggestion | Athlete Intelligence style |
| 3.6 | Verify the formula constants used here (HRV SWC multiplier) against primary sources | FINDINGS open questions |
Tools: `readiness_today`, `recovery_trend`, `daily_brief`.

### Phase 4: Training load & performance → v0.5.0 ✅ done (4.1–4.11)
| ID | Item | Backlog/source |
|---|---|---|
| 4.1 | Thresholds store (HRmax, RHR, LTHR, threshold pace) with dates; seeded from Garmin zones/LT | R14 |
| 4.2 | Per-activity TRIMP (all sports) and rTSS (runs), next to Garmin load | R15 |
| 4.3 | Fitness/fatigue/form (CTL/ATL/TSB) + ramp rate | R16 |
| 4.4 | Intensity distribution (3 zones) + polarisation index, next to Garmin Load Focus | R19 |
| 4.5 | Monotony/strain and week-over-week load change | R24 |
| 4.6 | Pace-duration curve, critical speed | R21, R22 |
| 4.7 | Race prediction (VDOT, Riegel, CS) next to Garmin's | R23 |
| 4.8 | Weekly review (Athlete Intelligence style) | — |
| 4.9 | Verify TRIMP constants and VDOT/Riegel against primary sources (pinned by tests) | FINDINGS |
| 4.10 | Swim (lengths, SWOLF) and strength (sets, reps) analytics | your request |
| 4.11 | Sense checks vs Garmin values and physics, in `garmin-mcp-verify` | your request |

### Phase 5: Workout coaching → v0.6.0 ✅ done (5.1–5.8; 5.9 moved to Phase 8)
| ID | Item | Backlog/source |
|---|---|---|
| 5.1 | Efficiency factor + aerobic decoupling per steady run, with trend | R20 |
| 5.2 | Running form trends (cadence, stride, GCT, vertical oscillation/ratio vs pace) | METRICS §Workout |
| 5.3 | Activity recap: comparison with similar past sessions, pacing, HR drift, what it trained | Athlete Intelligence style |
| 5.4 | Downsampled activity stream tool | R11 |
| 5.5 | Outdoor conditions shown separately. Retired the wrist-temperature HR slope in v0.17.0; estimates of a heat effect require verified exposure and a held-out study | R29 |
| 5.6 | Metric glossary: meaning, healthy range, how to improve | goal: coaching |
| 5.7 | Fitness age: Garmin's value + Garmin's own levers and potential ages. Our own norm-based estimate not built (formula unverified) → Phase 8 | goal: fitness age |
| 5.8 | Running deep-dive: form at matched pace, cadence/stride strategy, GCT/VO/vertical ratio trends, power vs pace, HR drift; deeper swim/strength insights | your request; research in running_and_sport_metrics.md |
| 5.9 | Active Intelligence / Athlete Intelligence-style features beyond the recap (later) | research note §4 |

### Phase 6: Memory, goals, provenance → v0.7.0 ✅ done
| ID | Item | Backlog/source |
|---|---|---|
| 6.1 | Athlete context (goals, target race, preferences, notes) | R26 |
| 6.2 | Goal reality check (target time vs current fitness) | AthleteData parity |
| 6.3 | Provenance on every result (source, computed vs Garmin) | R30 |
| 6.4 | Profile/timezone for "today" (GARMIN_TZ; defaults to the computer's local time) | R7 |

### Phase 7: Workouts to the watch → v0.8.0 ✅ done (upload path tested with a stand-in client; real upload needs the Mac login)
| ID | Item | Backlog/source |
|---|---|---|
| 7.1 | Structured workout builder; push via unofficial upload; FIT-file fallback | R31 |

### Phase 8: Insight engine, levels 1–3 → v0.9.0 ✅ core done (`engine.py`)
Source: `research_notes/.../insights_and_dashboards.md` (24-item backlog). Statistical rules for
all items: subtract personal baselines, ≥ 30 paired days before showing a relationship,
bootstrap confidence intervals, Benjamini–Hochberg correction when scanning many pairs, no causal
wording, no "injury risk".
| ID | Level | Item |
|---|---|---|
| 8.1 | 1 | Calendar heatmaps (load, sleep, HRV, readiness); PR timeline; streaks ✅ |
| 8.2 | 2 | Sleep → next-day HRV / readiness (lagged, baseline-adjusted) ✅ (14 pairs, BH-controlled) |
| 8.3 | 2 | Training time-of-day and load → that night's sleep and next-day HRV ✅ built; time-of-day has too few evening sessions yet (3–4 days) |
| 8.4 | 2 | Heat → HR drift (5.5) and day-of-week patterns ✅ |
| 8.5 | 2 | User tags with Whoop-style impact estimates ✅ (needs ≥ 5 tagged days per tag) |
| 8.6 | 3 | HRV-guided training rule in the insight feed ✅ |
| 8.7 | 3 | Load-jump and long-run-jump flags ✅ |
| 8.8 | 3 | Marathon shape (Runalyze rules verified: 6-month weekly km ⅔ + long runs ≥ 13 km over 10 weeks ⅓; 5K 7 %, 10K 17 %, HM 43 %, M 100 %) → Phase 10 (target-volume formula still unverified) |
| 8.9 | 3 | Personal Banister fit → Phase 10 (needs more performance points than 19 runs give) |
| 8.10 | 3 | Robust 90-day trends (Theil-Sen + CI) ✅; formal changepoint detection → Phase 10 |
| 8.11 | 3 | Calibration-test workout exists (Phase 7); EF trend of steady runs exists (5.2); standardised protocol tracking → Phase 10 |
| 8.12 | 3 | Race readiness + taper simulator → when you pick a race |
| 8.13 | — | Active/Athlete Intelligence parity: daily brief, weekly review, activity recap facts, insight feed ✅; further items in Phase 10 |
| 8.14 | — | Own fitness-age estimate → Phase 10 (norm formula unverified) |

### Phase 9: Dashboard → v0.10.0 ✅ done (`garmin-mcp-dashboard`, rebuilt after every sync; 9.6 is a list, interactive explorer → Phase 10)
Static, mobile-friendly HTML pages built by Python after each sync (Plotly.js/Chart.js, data
embedded), optional Datasette for ad-hoc SQL. Garmin's values shown with a "G" badge beside ours,
never averaged; provenance footer on every chart.
| ID | View |
|---|---|
| 9.1 | Daily brief card + readiness gauge with contributors |
| 9.2 | Fitness/fatigue/form chart with Garmin acute load overlay |
| 9.3 | HRV with normal band; resting HR; sleep consistency |
| 9.4 | Running: pace curve, form at matched pace, efficiency trend, race predictions |
| 9.5 | Weekly summary; calendar heatmap; swim and strength trends |
| 9.6 | Correlations explorer (Phase 8 results) |

### Phase 10: Competitor-parity scores → v0.11.0 (10a done; rest moved to Phase 12)
Source: `research_notes/.../fitbit_whoop_bevel.md` (Fitbit/Google Health, Whoop, Bevel, Oura;
verified page reads marked [R]). Each item keeps Garmin's values beside ours.
| ID | Item | Inspired by |
|---|---|---|
| 10.1 | ✅ Recovery % 0–100 = Φ(our readiness z), bands green ≥ 67 / yellow 34–66 / red ≤ 33 (Whoop-style), contributors, signals-used count. Oura 85/70/60 bands dropped: Whoop's three colours are easier to read | Oura, Fitbit, Whoop |
| 10.2 | Sleep score breakdown (duration, time to sound sleep, sound sleep, restlessness, awakenings, interruptions) + heart-rate dip | Fitbit 2026, Bevel |
| 10.3 | ✅ Sleep % (hours vs need), 7-day debt, suggested bedtime from your usual wake time (Asia/Kolkata) | Whoop, Garmin sleep coach |
| 10.4 | ✅ Strain 0–21 = min(21, 6.3·ln(1 + TRIMP/20)) with target band by recovery colour (training sessions only) | Whoop, Bevel |
| 10.5 | Activity status (sick/injured/break) that pauses advice and excludes days from baselines | Bevel |
| 10.6 | Pace of ageing (30 days vs 6 months), ± years per input; own fitness age (8.14) | Whoop Healthspan |
| 10.7 | Marathon shape (8.8) and Banister fit (8.9), changepoints (8.10), standardised test tracking (8.11) | Runalyze, Phase 8 carry-over |
| 10.8 | VO2max range bar by age and sex; Active Zone Minutes view | Fitbit |
| 10.9 | Interactive correlations explorer; monthly report page | Whoop, Fitbit |
| 10.10 | ✅ partial: `calibrating` flag and signals used (2 of 4) on recovery; rest with the dashboard | Oura, Fitbit |

### Phase 11: Dashboard v2 → v0.12.0 ✅ done (multi-page, no JS; UI map in `DASHBOARD_PLAN.md` §6)
Full plan: `DASHBOARD_PLAN.md`. Steps 11.2–11.7: wireframe of hero + Today + Why → validated palette → tabs (Recovery, Sleep, Training, Running, Body) with table views → Patterns with a "how sure" meter → browser checks at 390/768/1200 px, dark mode → optional private phone snapshot.

### Phase 12: Remaining parity and Level-3 items → v0.12.0 ✅ done
✅ 10.2 sleep breakdown + heart-rate dip · ✅ 10.5 activity status · ✅ 10.6 pace of ageing (own fitness age: deferred, Garmin's is used) · ✅ 10.7 marathon shape and changepoints (shift detection) · ✅ 10.9 monthly report · ✅ running breakdown (form bands, pace-matched form, what to work on).

### Phase 13 → v0.13.0 ✅ done
✅ Correlations explorer (Patterns page + `explore_relationships`) · ✅ test-run tracking 8.11 (`test_runs`) · ✅ recovery weighting study (`recovery_weight_study`; equal weights kept, evidence in CHANGELOG 0.13.0).

### Phase 14 → v0.14.0 (reference bar implemented; device/user inputs remain)
VO2max reference bar: exact FRIEND 2015 Table 3 implemented and tested. Race readiness/taper
still needs a goal race; phone/iCloud checks need actual devices. Re-run the corrected recovery
study on real data before using its conclusions; keep equal weights until the existing rule is met.

Continuation order requested by the owner:

| Item | State | Remaining evidence |
|---|---|---|
| A: private phone access | Optional Cloudflare Pages publisher implemented in v0.13.1; disabled | Confirm current Access free plan, configure account and two Access apps, save token locally, verify owner OTP/anonymous denial and next scheduled update on Mac/phone |
| B: age/sex VO2max bar | Implemented v0.14.0 from primary FRIEND 2015 Table 3 | 84 code values checked against direct transcription; live Mac profile/data check remains |
| C: dashboard design | Review and small improvements implemented in v0.14.1; see `docs/UI_REVIEW.md` for screenshots and browser evidence | Check Safari/iCloud and private hosted phone navigation on real devices; collect owner feedback |
| D: docs with every change | Updated through v0.14.1 | Keep handover, roadmap, changelog, README, metrics and setup synchronized as relevant |

The constant-signal explorer crash found while validating A is fixed without changing statistical
thresholds. The empty-database dashboard failure is resolved in v0.14.1. See
`docs/CONTINUATION_REVIEW.md` for findings and validation, not a second plan.

### Deployment track (runs alongside, needs you once)
| ID | Item | Target |
|---|---|---|
| D.1 | Mac setup (`MAC_SETUP.md`): import, 1-year backfill (✅ 2,894 calls, 0 errors), Claude Desktop config, 3-hourly sync (✅). **Self-update (v0.11): after one last pull, every sync updates itself from `main`; settings come from `config/athlete.json`.** | v1.0.0 |

### Later / optional (only if you ask)
R32 intervals.icu source · R33 Apple Health import · R34 multi-device dedupe.
Grafana remains dropped; private remote hosting has been requested and moved to A above.

### Explicitly not building
Skin temperature/ECG (no FR955 sensor) · ACWR as injury risk · Strava as a source ·
our own Body Battery/Stress (no valid open method; Garmin's are shown).

## Needs from you
| # | Input / action | State |
|---|---|---|
| 1 | One last manual update (Terminal) | ✅ done by you; updates now arrive with every sync |
| 2 | **Max HR test** (calibration workout, or 3 × 3-min hard hill repeats): the one open question that moves most numbers (zones, load, effective VO2max). Data says 188 (age formula + repeatable peak 177); Garmin's model implies ~209 | open, recommended |
| 3 | Goal race | ✅ none yet (general fitness; marathon some day) |
| 4 | Goals, knee, timezone | ✅ saved, applied automatically via `config/athlete.json` |
| 5 | Optional: weights in strength sessions; watch "Log HRV"; Garmin Connect max HR setting once #2 is known | open |
| 6 | Rotate the Personal API key | deferred by you |
| 7 | Cloudflare account, free-plan confirmation, exact-email Access apps and locally saved token | needed only to activate A; no secrets in chat |
| 8 | Cloud network access for GitHub API and source research | ✅ enabled by owner; API access verified and PR #8 merged after CI |

## What's left (full backlog, 2026-11-23)
| Area | Items | State |
|---|---|---|
| Dashboard | Phase 11 v2 | ✅ done |
| Parity / Level 3 | Phases 12–13 | ✅ done; Phase 14 waits on inputs |
| Deployment | Mac checks in D.1, optional phone hosting A, then v1.0.0 | manual update #1 is done; live unattended/phone evidence still pending |
| Research | Whoop details snippet-only (site blocks bots); HRV4Training rule page empty; fitness-age norm formula unverified | accepted, flagged |
| Optional sources | R32 intervals.icu, R33 Apple Health, R34 multi-device dedupe | only if you ask |

## Planned earlier, now not relevant (flagged)
| Item | Why dropped |
|---|---|
| FIT workout encoder (7.1 fallback) | Garmin Connect provides the workout FIT after upload |
| Oura 85/70/60 readiness bands (10.1) | Whoop's three-colour bands read faster |
| Grafana view | Wrong tool for a personal glance view; the static dashboard replaces it |
| Remote hosting | Previously dropped in favor of a manual private snapshot; reopened at the owner's request as A (private access required) |
| Our own Body Battery/Stress, ACWR injury risk, Strava source, skin temp/ECG | Already excluded (no valid method / API terms / no sensor) |
| Copy-paste setup in a second Claude chat | Replaced by self-update + settings file |
| Banister impulse-response fit (8.9) | 19 runs is too little data for a 4-parameter fit; revisit after ~6 months of steady training |
| Active Zone Minutes view (10.8) | Same information as Garmin intensity minutes, already shown |
| Our own fitness age (10.6) | Garmin's fitness age with levers is shown; no citable open formula to beat it |

## Problems caused by incomplete information (and what fixes them)
| Problem | Effect | Fix |
|---|---|---|
| No all-out run efforts | Critical speed and best-effort predictions reflect training pace; rTSS off | #6 |
| Garmin's max-HR/LTHR settings look too high (209/185) | Garmin's own zones under-rate your effort | Ours use 188/166; optionally set Garmin Connect max HR to ~188 so the watch agrees |
| Last night's sleep sometimes missing / 14-min records | Readiness falls back; flagged as incomplete | Wear the watch overnight; sync in the morning |
| Unofficial extras gap after the export date | ✅ closed by the Mac backfill (365 days) | — |
| Low weekly running volume (~2 km/week recently) | Half/marathon predictions unreliable (warned) | Training, not data |
| Whoop blocks automated reading | Whoop details rest on search snippets and reviews | nothing needed |

## Side-quest rule
Research or fixes outside the current phase are done only when they feed an item above; each is
logged in CHANGELOG under the item it serves, then work returns to the current phase.

### Follow-up after the coach-first review

1. Verify the scheduled Mac, local HTML and iCloud/private iPhone copies using their
   separate version and sync timestamps. Run the five-second test on real data.
2. Record which coaching cue was tried, how it felt and the next comparable effort.
   Include real-data checks for bedtime windows, sleep findings and the weekly plan.
3. Reduce remaining file size and confirm Safari/Files rendering on the actual phone.
   Keep detailed tool evidence available even when an overview is shorter.
4. Validate local station and logger coverage, then add opt-in local provider retrieval
   and cross-source checking. Exercise, sleep and daytime energy use separate evidence.
   Automatic retrieval for the broader weather project is still open.

Use [the product review](docs/PRODUCT_REVIEW_2026-11.md) for the original critique and
[the source ledger](research_notes/Garmin%20connector%20feature%20research/owner_reference_review_2026-11.md)
for what changed because of the research. Keep decisions and active work in this roadmap;
older audits, checks and screenshots document what was tested.
