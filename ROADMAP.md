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
| 0.6.0 | Phase 5: workout coaching (running first) + activity recap + fitness age levers | **next** |
| 0.7.0 | Phase 6: memory, goals, provenance | |
| 0.8.0 | Phase 7: workouts to the watch | |
| 1.0.0 | All of the above running on your Mac with scheduled sync | |

## Done (traceable to the backlog)
R1–R6 ingest, store, FIT, sync, `refresh_data` · R8–R10 day/sleep/activity tools · R12 trends ·
R13 coverage · R27 unofficial adapter · R28 export importer · health snapshot · cross-source
verification · research (competitors, FR955 metrics, formulas, integrations) with a verification
pass on Garmin labels (`VERIFICATION_LOG.md`).

## Phases ahead (in order)

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

### Phase 5: Workout coaching → v0.6.0
| ID | Item | Backlog/source |
|---|---|---|
| 5.1 | Efficiency factor + aerobic decoupling per steady run, with trend | R20 |
| 5.2 | Running form trends (cadence, stride, GCT, vertical oscillation/ratio vs pace) | METRICS §Workout |
| 5.3 | Activity recap: comparison with similar past sessions, pacing, HR drift, what it trained | Athlete Intelligence style |
| 5.4 | Downsampled activity stream tool | R11 |
| 5.5 | Heat effect on HR (weather/FIT temperature) | R29 |
| 5.6 | Metric glossary: meaning, healthy range, how to improve | goal: coaching |
| 5.7 | Fitness age: Garmin's value + levers (VO2max, RHR, vigorous minutes, BMI); verify the norm formula | goal: fitness age |
| 5.8 | Running deep-dive: form at matched pace, cadence/stride strategy, GCT/VO/vertical ratio trends, power vs pace, HR drift; deeper swim/strength insights | your request; research in running_and_sport_metrics.md |
| 5.9 | Active Intelligence / Athlete Intelligence-style features beyond the recap (later) | research note §4 |

### Phase 6: Memory, goals, provenance → v0.7.0
| ID | Item | Backlog/source |
|---|---|---|
| 6.1 | Athlete context (goals, target race, preferences, notes) | R26 |
| 6.2 | Goal reality check (target time vs current fitness) | AthleteData parity |
| 6.3 | Provenance on every result (source, computed vs Garmin) | R30 |
| 6.4 | Profile/timezone for "today" | R7 |

### Phase 7: Workouts to the watch → v0.8.0
| ID | Item | Backlog/source |
|---|---|---|
| 7.1 | Structured workout builder; push via unofficial upload; FIT-file fallback | R31 |

### Deployment track (runs alongside, needs you once)
| ID | Item | Target |
|---|---|---|
| D.1 | Mac setup via one local Claude Code session (`MAC_SETUP.md`): import export, 1-year backfill, Claude Desktop config, 3-hourly sync | v1.0.0 |

### Later / optional (only if you ask)
R32 intervals.icu source · R33 Apple Health import · R34 multi-device dedupe · Grafana view ·
remote hosting.

### Explicitly not building
Skin temperature/ECG (no FR955 sensor) · ACWR as injury risk · Strava as a source ·
our own Body Battery/Stress (no valid open method; Garmin's are shown).

## Needs from you
| Item | When |
|---|---|
| Run the one-message Mac setup (D.1) | whenever convenient; nothing else blocks on it |
| Rotate the Personal API key (it was pasted in chat) | deferred by you |
| Optional: watch setting "Log HRV" for beat-to-beat data in activities | your choice |
| ~~Merge PR #1 into `main`~~ | done at v0.4.0 |

## Side-quest rule
Research or fixes outside the current phase are done only when they feed an item above; each is
logged in CHANGELOG under the item it serves, then work returns to the current phase.
