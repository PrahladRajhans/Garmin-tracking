# Owner acceptance results: Mac run, 25 November 2026

First run of the v0.32.0 acceptance on the owner's Mac (Apple M5, 16 GB, Python 3.15, Ollama
0.40.17, Qwen3.5 4B). Personal readings, dates of readings and coverage counts stay in a local
report on the Mac (`~/.garmin-mcp/acceptance/report.md`). This page records methods and outcomes.

Evidence types: **fixture** (synthetic tests), **archive** (the owner's database, read-only or on
a disposable copy), **runtime** (Mac, Ollama, launchd, Garmin calls), **device** (watch or phone).

## Checklist

| # | Check | Evidence | Result |
|---|---|---|---|
| 1 | Checkout at v0.32.0, matches `origin/main`, launchd runs this checkout | runtime | Passed |
| 2 | Data directory, database, FIT folder, timezone, launchd environment resolved | runtime | Passed: defaults under `~/.garmin-mcp`, no environment overrides |
| 3 | Read-only archive audit: SQLite quick check, every FIT reference present and decoded | archive | Passed |
| 4 | Dashboard replay, one snapshot per recorded month | archive copy | Passed: no broken links or duplicate ids. Source checksum unchanged |
| 5 | 28-day, 90-day and full-history baselines on recent and old dates | archive | Passed: 135 windows match an independent recalculation |
| 6 | Reported 44 bpm against its dated Garmin source | none | **Open**: no confirmed date or label |
| 7 | Elapsed kilometre splits against watch auto-laps | archive | Passed: within 2 s |
| 8 | Sample-rate independence: real runs thinned to 2–8 s intervals | archive copy | Passed: graded speed within 1 %. Beyond the 10 s gap limit, metrics are unavailable by design |
| 9 | Cadence against watch lap values | archive | **Fixed**: 0.9 spm low, now within 0.02 spm |
| 10 | Grade-adjusted pace against Garmin | archive | Differences follow our moving-only filter (speed above 1 m/s). Method difference, not a bug |
| 11 | Workout with unusable load stays unknown in daily, weekly and dashboard text | archive copy | Passed. Weekly Garmin load fixed (was 0 or partial) |
| 12 | Monitoring FIT preview on an owner file | archive | **Fixed** a false resting-pulse disagreement. Import stays disabled |
| 13 | Nap totals and Body Battery charge/drain coverage | archive | Passed |
| 14 | Intraday Stress and Body Battery | archive + runtime | **Fixed**: never downloaded in the default sync mode |
| 15 | Daily distance across sources | archive copy | **Fixed**: export counted rides and swims |
| 16 | Interval and progression workout preview | runtime (offline) | Passed locally. **Watch unverified** (upload not approved) |
| 17 | Ollama version, cloud disabled, model | runtime | Passed. Thinking is off; draft budget 10 min |
| 18 | Ollama listens on loopback only | runtime | **Fixed by the owner and rechecked**: network exposure was on. Now `127.0.0.1` only, cloud disabled, narrator ready, one fictional Running case passed. Ollama had updated to 0.40.18 |
| 19 | Fictional AI cases | runtime | See below |
| 20 | Dated archive AI cases | archive copy + runtime | See below. **Usefulness still needs the owner's review** |
| 21 | Model unreachable; stale worker before and during generation | archive copy | Passed: page kept, status recorded, newer snapshot never overwritten |
| 22 | First build, then the AI update | archive copy + runtime | Passed: 3 s build, AI update 41 s later, page and cache agree |
| 23 | Test suite leaves the owner's files alone | runtime | **Fixed**: it had replaced the iCloud dashboard with a test page (restored) |
| 24 | iPhone, VoiceOver, offline reopen | device | Passed after the merge, as reported by the owner. [Details](#physical-iphone) |
| 25 | iOS Simulator | none | Not run: this Mac has no Xcode |
| 26 | Protected hosting | none | Pending: not selected or configured |

## After the merge (PR #46, commit `157a11c`)

| Check | Result |
|---|---|
| Real launchd job (`launchctl kickstart`) | Passed: fetched `main`, reinstalled, restarted on v0.32.1, skipped the download (nothing new), rebuilt the page and the iCloud copy. Publishing disabled |
| Database backup before the full sync | Taken with the SQLite backup API; quick check passed. FIT files not copied |
| Controlled full sync, 180 days forced | Passed: no errors or rate-limit waits, SQLite quick check passed, 116 of 116 activities decoded |
| Intraday Stress and Body Battery after backfill | Passed: usable from 1 July 2026 with no gaps; earlier requested days came back empty |
| Replay after backfill | Passed: no broken links or duplicate ids |
| AI worker while the sync was running | Passed: held with `sync_incomplete` |
| First AI pass after the sync | **Partial**: ended `incomplete` with the run summaries and Running review pending. The pending prompts all succeeded on a copy, and the next build completed all 18. Cause not established |

The dashboard grew from about 4.5 MB to 4.9 MB with the intraday timelines.

## Physical iPhone

The owner ran these on their iPhone with the v0.32.1 page opened from **Files → iCloud Drive →
Garmin**, the access path in use. These are the owner's reports; the agent did not see the device.

| Check | Result |
|---|---|
| Page controls (Light and Dark buttons) appear in Files | Passed |
| Today, Sleep, Running and a historical day, and back | Passed |
| Chart tap shows a reading; scrolling over the chart still works | Passed |
| Overlay switch and exact readings list | Passed |
| Light and dark readability; footer shows 0.32.1 | Passed |
| Reopen in Airplane Mode: pages and chart taps | Passed. Fetching a newer snapshot still needs a connection for iCloud |
| VoiceOver announces a chart selection and reads the readings list row by row | Passed |

Not tested: Safari and a Home Screen icon. A local file in Files offers neither; both belong to
protected hosting. The iOS Simulator was not used (no Xcode).

## AI results by path

Times are after model warm-up on the M5.

| Case | Surface | Outcome | Time |
|---|---|---|---|
| Fictional | Today, Running | Model prose passed review | 4–5 s |
| Fictional | Sleep | Draft and revision failed review; exact readings selected | 9 s |
| Fictional | Sleep, 5 min thinking | Thinking draft incomplete; concise retry passed review | 126 s |
| Fictional | Post-run (cue, outlier, thin) | Correct topic or correct abstention | under 2 s |
| Fictional | Post-run (form) | Low-signal choice withheld by the guard | under 1 s |
| Fictional | Sunday | Revision passed review | 8 s |
| Fictional | Dated health, mixed recovery | Exact readings selected | 5–9 s |
| Archive, latest day | Sleep | Prose passed | 5 s |
| Archive, latest day | Today (direct) | Revision passed | 12 s |
| Archive, latest day | Today (5 min thinking) | Incomplete, then exact readings selected | 161 s |
| Archive, latest day | Running | Exact readings selected | 15 s |
| Archive, contrast Sunday | Today, Sleep | Prose passed | 5–6 s |
| Archive, contrast Sunday | Weekly review | Exact readings selected | 12 s |
| Archive, no recorded nights | Today, Sleep | Correctly absent | |
| Archive, all dates | Post-run | Model chose among checked observations | under 1 s |

Every number in an accepted output also appeared in the supplied readings. Direction, wording and
whether the next step is useful need a person to read them; the prompts and outputs are in
`~/.garmin-mcp/acceptance/ai_review.md`. A selected exact reading is availability of the fallback,
not useful coaching. Running and the weekly review mostly end there.
