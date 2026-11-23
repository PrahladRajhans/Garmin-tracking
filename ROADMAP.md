# Roadmap: the single main plan

**This file is the one plan.** Every other planning document is reference material that feeds
into it, and every item there is mapped to a phase here:
- `reports/Garmin connector feature research.md`: 34-feature backlog, referenced as **R1–R34**.
- `METRICS.md`: how each metric is calculated (Garmin vs science vs ours).
- `research_notes/.../FINDINGS.md`: research index and open questions.
- `MAC_SETUP.md`: deployment steps for the Mac.
- `CHANGELOG.md`: what shipped, per version.

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

### Athlete intelligence follow-up

| Order | Deliverable | Evidence needed |
|---|---|---|
| 1 | Daily briefing, personal signals and History | Verify dated raw readings, resting pulse trend/range, overnight breathing and Pulse Ox, and coverage at each time scale |
| 1a | Optional run overlay trial | Check cadence/step length and speed/HR on comparable real workouts. Seek feedback before broader rollout |
| 2 | Verify daily guidance and run comparisons on the Mac archive | Compare with dated Garmin records and inspect missing nights, unusual runs and completed syncs |
| 3 | Weekly coaching priorities and training response | v0.17.0 ships matched efforts and a descriptive readiness benchmark. Validate coverage, repeat on later weeks and check weather/terrain before predictive use |
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
