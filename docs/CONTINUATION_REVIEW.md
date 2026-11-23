# Continuation review — 23 November 2026

Reviewed against main `5c3d7e6`, v0.13.0. Work is on `codex/private-dashboard-access`.
This records findings and evidence; `ROADMAP.md` remains the single plan.

## What is where

| Layer | Files and verified entry points | Boundary to preserve |
|---|---|---|
| Sources | `sources/personal_api.py`, `sources/garminconnect_source.py`, `sources/base.py`, `client.py`, `login.py` | Official API first; unofficial extras isolated; no cloud credentials required for unit tests |
| Storage and import | `db.connect`, `importer.run_import`, `fit.store` | Raw payloads retained, FIT scaling handled by the SDK; cadence conversion belongs at presentation/calculation boundaries |
| Normalization | `normalize.EXTRACTORS`, `normalize.rebuild` | First non-null field by source priority; filters missing-value sentinels; rebuilds tidy/derived tables from raw data |
| Recovery and scores | `recovery.readiness`, `scores.daily_scores`, `scores.weight_study` | Scores and equal weights are heuristics with inputs; no reweighting without the existing two-outcome rule |
| Load/performance | `loads.thresholds`, `loads.rebuild`, `loads.effective_vo2max`, `loads.race_predictions` | Untested HRmax remains visible; no new max-HR inference or calibration changes |
| Coaching and health | `coaching.py`, `running.py`, `health.py`, `goals.py`, `workouts.py`, `athlete.py` | Distinguish Garmin from ours; thin-data reasons; workouts write only when requested; no race work without a race |
| Statistics | `engine.relationship`, `engine.bh_adjust`, `engine.explore` | Baseline adjustment, ≥30 pairs, 7-day blocks, bootstrap uncertainty, q < 0.10 and abs(r) ≥ 0.15 retained |
| Delivery | `server.py`, `dashboard.collect`, `dashboard.render`, `dashboard.build` | 43 tools; one script-free HTML file, CSS fragment navigation, inline SVG; Mac/iCloud copies |
| Automation | `sync.run_sync`, `sync.gate`, `autoupdate.update`, `athlete.seed_from_file` | 11-hour/new-activity gate; fast-forward-only updates; user settings filled only when missing |
| New optional publishing | `publish.publish_if_enabled`, `publish.check_access` | Off by default; protection checks before upload; HTML only; local build survives refused/failed uploads |

## How the project evolved

The commit history and CHANGELOG agree on this progression:

1. v0.1: live MCP reads and reusable Garmin login.
2. v0.2–0.3: raw SQLite ingestion, official API plus unofficial extras, export history, FIT,
   normalized tables and database-backed tools. v0.3.1 corrected units/timestamps and added verification.
3. v0.4–0.8: recovery, load/performance, run coaching, athlete memory/goals, workouts.
4. v0.9–0.11: statistics and insight engine, prototype dashboard, then daily scores,
   CI, self-update, settings seeding and the v2 design specification.
5. v0.12: replaced Chart.js/CDN output with the current static SVG/CSS dashboard; added
   health/running breakdowns, sync gate and activity status.
6. v0.13: correlations explorer, test-run tracking and recovery weighting study. Equal recovery
   weights were retained after the documented study; route matching and population norms remain open.

Research documents are historical evidence, not instructions to re-add dropped work. For example,
the early FINDINGS index still suggests a FIT encoder/Grafana and a smaller tool set; the current
roadmap explicitly drops those. The supplied handover's A–D order is the current continuation scope.

## Findings and scope of this change

- Cloudflare's default Access switch protects previews only. The new uploader requires the two
  whole-host apps and checks their policies before an upload. Account creation, a token on the
  Mac, current Access free-plan confirmation, and device tests are still required.
- `MAC_SETUP.md` pointed at an old feature branch; it now uses `main` and fast-forward-only pull.
  The dashboard plan had a non-default data path; it now names the environment override and
  actual default. The internal package version had stayed at 0.11.0; it now matches 0.13.1.
- A constant adjusted signal made `engine.relationship` index an empty bootstrap list, crashing
  dashboard collection. Reproduced using synthetic constant bedtimes; fixed by returning unavailable
  with a reason, with a regression test. Statistical thresholds/formulas are unchanged.
- A fresh empty database still cannot build the dashboard CLI: before normalization it lacks tidy
  tables; afterward it lacks the latest daily date. This is an existing limitation, recorded rather
  than silently changing initialization/data behavior during the hosting work.
- Primary VO2max norm retrieval was blocked by network policy. No numbers were reconstructed.
  The norm bar and its source-dependent implementation remain pending.
- The original screenshots were inspected. The mobile top navigation scrolls horizontally within
  its own container, and the current charts still need a full review of contrast, focus, table
  alternatives and all page screenshots. This change preserves the design; it does not claim a
  completed redesign or accessibility audit.

## Validation

- Original baseline: **59 tests passed**, Ruff passed on Python 3.12.14.
- Optional publishing tests cover production plus previews, broad/bypass policies, conflicting
  paths, destination overrides, custom domains, pagination, exact file staging, secret-safe errors,
  check-only mode, disabled mode and preservation of the local dashboard when publishing fails.
- The same collected synthetic data renders **byte-identical HTML** using main's renderer and
  the updated renderer. No layout, chart or metric presentation was changed in this patch.
- Chromium via Playwright checked **48 states**: Today, Sleep, Recovery, Training, Running,
  one run, Body and Patterns at **390/768/1200 px**, light/dark. Each had exactly the intended
  visible section, no document overflow, no broken fragment links, no page errors and no scripts.
  File URLs are blocked by cloud browser policy, so HTML was loaded with `page.setContent`;
  this does not verify Safari file/iCloud behavior. Synthetic Today screenshots were inspected.
- MCP stdio initialization, the 43-tool list and `data_coverage`/`build_dashboard` calls were exercised with a
  synthetic database. No live Garmin request, workout write or auto-update was run.
- No health data or credentials were uploaded. No user's Mac, iCloud or phone was accessed.
- GitHub API access was denied by cloud network policy. Git fetch works and main remained
  `5c3d7e6` at the last check. A PR, CI status and merge cannot be claimed without API access.

Transient synthetic fixtures and browser output are under `/tmp/garmin-review`, outside the
checkout. Existing screenshots in `docs/screenshots` are retained. The final test result is
recorded in CHANGELOG; live rollout checks belong to ROADMAP A and MAC_SETUP.

## Resolution update — v0.14.1, 23 November 2026

The earlier sections describe the v0.13.1 review point, not today's unresolved issue list.
Owner-enabled internet restored GitHub API and PMC access. PRs #8, #9, #10 and #11 passed
both CI jobs and merged; the FRIEND Table 3 source/bar is implemented. Empty databases now
render a waiting state. Dashboard design changes and evidence are in `UI_REVIEW.md`.

The expanded review fixed chunk/pagination termination, updater recovery, partial-sync gating,
local dates, sleep fallback/sufficiency, UTC HR comparisons, study pairing/zero correlations,
malformed/cyclic workout inputs, stale current-day ranges, missing bounds, incomplete derived
loads, atomic output and provenance. Each has tests in the affected module's test file.
Installed API client timeouts and bounded/date-advancing loops were inspected. This is a
bounded review of current paths, not a claim that every upstream/network failure is impossible.
No real-data weighting study, Garmin login, watch write or private hosting activation occurred.

Next operational checks are the Mac/device items already in ROADMAP; no additional feature
roadmap is introduced here. Historical source-retrieval limitations in older notes remain
dated evidence; the accuracy-review ledger names the sources subsequently verified.
