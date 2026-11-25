# Repository review and release readiness

Historical baseline: Garmin Tracking v0.25.0 plus the interpretation work since shipped
in v0.26.0. The remaining manual review and owner-device acceptance are in
[the current priorities](../ROADMAP.md#current-priorities).

| Workstream | Coverage | Decision and evidence |
|---|---|---|
| Inventory | Every one of the 152 tracked baseline files read. 116 text files, 21,953 lines, including 72 Python files. The 36 PNGs were checked for duplicate bytes. | AST parsed production and test code, identified functions with no static private references, compared exact function bodies with at least four statements, and resolved all eight CLI targets and 55 MCP decorators. Exact duplicate hashes and exact nontrivial function bodies were absent. |
| Dynamic entry points | Inspected Mac login, console commands, source adapters, sync, disabled publishing and weather guards, detached narration and dashboard rebuild. | Some entry points have no direct import caller. Login is a documented module command. Source adapters are imported in the sync factories. Weather and protected publishing are opt-in paths with existing tests. Keep them. |
| Cleanup | Confirmed the unused trial timestamp helper and running/bedtime arguments against repository callers. | Remove those dead paths. Keep the redirect override, source interface and importer divider flagged by the exploratory lint pass. Consolidate agent rules under AGENTS.md and point CLAUDE.md there. Correct the MCP count in the architecture. |
| Interpretation UX | Chromium checked Today at 390 px and 1200 px. | The interpretation comes before the weekly card. The disclosure shows earlier evidence as text and links current readings to their corresponding pages. Both widths rendered without page-level overflow. |
| Config and continuity | Check time-budget compatibility, local persona loading, cache key inputs and prior evidence bounds. | Allow 1–30 minutes for the draft with a separate overhead budget. Keep a local profile outside Git and a small SQLite evidence memory. The model gets evidence only, with no private reasoning or earlier drafts. |
| Three-year replay | 36 sampled months on a generated archive. | Zero bad fragment links or duplicate IDs and a byte-identical source after replay. The source is synthetic. The owner's Mac archive was absent from the execution workspace. |
| Remaining manual audit | Complete review of every formula, old note, screenshot and every dynamic deployment branch is still open. | Continue by module ownership and use evidence before removing or consolidating code. Cover real archive replay, launchd, iCloud, and physical-device behavior separately. |

The static pass traversed all Python ASTs and checked each tracked file. It flags candidates for
inspection. Static references do not prove runtime use or correctness. Photos, screenshots,
research notes, and old changelog material are historical evidence even when current code does
not reference them. Keep those unless the owner chooses to retire them.
The documentation pass also resolved 141 repository-relative Markdown paths without a missing
file target.

## File-by-file review record

The [file register](repository-review-queue.tsv) lists all 160 tracked paths at v0.26.1
(`aa14346`) and the three new paths in this release. Every path now has a review record.
Ten paths are marked `fixed and verified`. Review records describe the source, tests and
entry points examined. The remaining runtime, private archive and device gates are listed below.
Include added, renamed and removed paths as the audit moves forward.

For text files, record the reviewed headings or line ranges, their callers and inputs, the
settings or flags that activate them, known gaps, decisions and tests. For assets, record where
they are referenced, what release or source they document, and whether they still serve that
purpose. Mark code as reviewed only after tracing its callers and writing down a decision.
Use `reviewed`, `partial`, `blocked` or `fixed and verified` as evidence is added. `partial`
records an inspected slice with further manual or runtime checks identified in the register.
A blocked device or account path stays visible even when the local implementation passes.

## Dependency and failure paths

These are entry-point traces for planning. The [execution queue](../ROADMAP.md#detailed-execution-queue)
owns the sequence and acceptance checks.

| Path | Dependency to preserve | Effect to check when it changes |
|---|---|---|
| Scheduled update and fetch | `autoupdate` and the local scheduler → `sync.main` / gate → source factories → pagination and retries → SQLite/normalization → freshness stamp → dashboard and optional publishing | An install or source failure must remain visible and retry without stamping stale data as current. A skipped fetch can still rebuild the dashboard and retry narration. Check both paths and historical local-date boundaries. |
| Source data and archive | Personal API, Garmin Connect and importer → `db` raw/retained revisions and `fit.store` → `normalize.rebuild` → loads, recovery, running and history | A source or unit change can alter many pages, cached evidence and MCP tools at once. Exercise old schema, conflicting payloads, timestamp and distance gaps, rollback and restore paths. |
| Shared analytics | FIT and daily records → `coaching.run_metrics` / `run_evidence.matched_effort` / `running.form_comparison` / `running_block.collect` → dashboard and MCP → AI evidence | Compare actual IDs, pace ranges, inclusion rules, units and missing values across all consumers. Check that historical review uses prior observations and that cohort rules match the advice's wording. |
| Sleep and coaching feedback | `sleep_review`, tags, `coach_loop` and `trials` → `insights.daily_brief` / `training_plan.week` → Today, Sleep, Training and Running → later check-ins and observations | A changed recent/previous window or an incomplete sync changes how planned sessions and outcomes are interpreted. A previous-evening knee rating already changes the daily brief. Verify that related run recommendations and experiments agree, with old snapshots tied to their own dates. |
| Background AI and snapshot replacement | `dashboard.build` → initial HTML and queue → `narrator._worker` → local model and validator → cache → conditional `dashboard.build` | A second build, new sync, model change or timeout can make a queued result stale. Check that worker and snapshot guards stop an older result from replacing current HTML, that a worker rebuild does not requeue itself, and that fallback and cache keys remain correct. |
| Shared chart rendering | Run trace and exact elapsed crossings → SVG and density settings → split toggle, overlays and cursor → responsive layout and exact-value disclosures | A change to responsive geometry can shift all split guides or obscure readings. A shared colour or chart change can affect unrelated pages. Test both themes, low contrast, very dense/sparse traces, keyboard focus, and script-free links and disclosures. |
| Delivery | Atomic local HTML write → optional iCloud copy; configured publisher follows eligible builds → Safari/Files or private phone viewer | Local file success does not verify the copy the phone opens. Track different build and data timestamps; check publishing protection if enabled. Verify whether background AI is visible from each destination and when. |
| Release | CLI and MCP interfaces, schema, and output contract → component tests → replay and browser checks → CI and merge → scheduled Mac rollout | Pass test jobs on the exact candidate head and verify release and live view separately. Review the old config/database fixture and a known-good rollback before marking the slice complete. |

Specific loops to exercise are scheduler → retry → next scheduler, dashboard → AI worker →
conditional rebuild, plan → completed activity → following plan, and trial → comparable
repeat → revised advice. In each loop, record the trigger, advance condition, exit or
timeout, behavior on the same input twice, and the last valid state when an operation stops.

## Execution log

The v0.27.0 pass followed the [detailed queue](../ROADMAP.md#detailed-execution-queue).
The register records evidence against the v0.26.1 baseline. New bedtime, AI status, Sunday
and Running paths have dedicated coverage in the release tests.

| Queue | Completed in this pass | Next acceptance or work |
|---|---|---|
| 00–05 · Baseline and restore | Baseline suite passed 234 tests. Replayed 36 generated months with no broken in-page links or duplicate IDs and verified the original digest. Restored a disposable SQLite copy with both FIT revisions, then reparsed and regenerated HTML. | Run the real archive replay and restore a private copy on the Mac. Check launchd, skipped and full sync, Ollama, iCloud and the iPhone's actual snapshot, with data and build times recorded separately. |
| 10–16 · Code and data | Recorded line ranges, entry points and decisions for all 160 baseline paths. Tested missing-detail retries, malformed official pages, FIT attachment and units, historical trial boundaries, archive day coverage and changes that need a dashboard rebuild. | Exercise the live Mac, optional source and publishing branches. Recheck activity end times crossing midnight, degraded FIT inputs, sparse minutes, rollback on malformed normalization and potential dashboard page-module boundaries. |
| 20–24 · Local AI | Added a Sunday-specific prompt, inspectable evidence and a deterministic fallback. Dashboard and CLI show model state and last accepted time. Linux Qwen3.5 4B direct Sunday trials were withheld before and after clarifying that workout count does not express training volume. | Extend the evidence-to-action review across all display surfaces. Run the same cases on the owner's Mac, compare suitable larger models, and measure usefulness, acceptance and latency. |
| 30–34 · Readability | Checked nine dashboard pages at four widths in both themes and 348 additional route and viewport cases in Chromium. Fixed Sleep after target acceptance, intraday History's empty state and custom-directory isolation from iCloud. Verified keyboard focus, split guides, overlay labels and a 390 px script-disabled run view. | Check physical Safari/Files, reading density on the owner archive, and accessibility beyond the measured component checks. |
| 40–45 · Running | Matched early and late form on shared pace and grade, aligned split guides to the full FIT time origin and used the prior knee check for cadence and block advice. Trial efficiency claims now require three actual comparisons. | Compare against dated Garmin/FIT runs, exercise the full cue → recorded run → comparable repeat → next action loop, and evaluate best efforts and durability on the owner's archive. |
| 50–53 · Sleep and later ideas | Persisted the accepted weekly bedtime target, recorded follow-up outcomes by date and linked the evidence from Sleep. | Verify the sleep loop on the Mac. The tailored strength progression, evening stress/Body Battery reflection, research comparisons and optional private digest remain in the queue. |

## How to validate on the Mac

Use the existing local database and run `garmin-mcp-verify --replay-dashboard`. It opens the
source read-only, uses a temporary SQLite copy, renders up to 36 monthly snapshots, and prints
aggregate coverage and link counts. It sends no data to Ollama or a network service and does not
save rendered pages. The temporary disk needs space for a copy of the database.

## Model choice

- Qwen3.8 has a 27B local tag around 18 GB for the model alone. It is a candidate for drafting
  on a Mac with memory headroom. The current 8 GiB execution limit rules out loading that file
  here. [Qwen3.8 source](https://github.com/QwenLM/Qwen3.8) · [Ollama tags](https://ollama.com/library/qwen3.8/tags).
- Nimble v3 is a Qwen3.5-derived 9B decision fine-tune for classification, routing, and scoring.
  The tested 5.6 GB Q4 tag reported only the `decision` capability. Ollama rejected a live
  `/api/generate` request. Qwen3.5 4B is the v0.26.1 default. Nimble could be evaluated as a
  separate review classifier using its decision interface.
  [Publisher overview](https://ollama.com/library/nimble-v3) · [Local tags](https://ollama.com/library/nimble-v3/tags).
- On the fictional mixed recovery case, Qwen3.5 4B completed a direct run in about 55 seconds
  and the pipeline withheld the observation. Keep this case as a release check.
- On the fictional matched-run case, the same model hit the configured five-minute thinking
  limit. The direct retry was withheld. Total time was about 336 seconds on Linux CPU.
  A separate direct diagnostic showed two concrete problems: the draft inferred perceived
  effort from pulse data and introduced a sleep threshold without citing a sleep reading.
  The writer prompt now asks about repeat measurements without invented targets or perceptions.
  A direct retest of that case completed in about 55 seconds and was also withheld.
- Compare models on the same fictional cases. Record whether the model returned a useful
  reviewed observation, its latency, and whether it used thinking or a direct draft. Model
  file size and vendor benchmarks do not establish those outcomes for this workflow.


## Dated health evidence review

The v0.27.4 pass traced sync, normalization, archive windows, Sleep, History, Patterns
and Ollama evidence. It reused chart and inference paths and kept the preserved raw Garmin
payloads. The [reviewer index](REVIEW_START_HERE.md) records those entry points.
Further repository-wide formula and deployment review remains open in the [roadmap](../ROADMAP.md).

## Garmin ecosystem pass

[The 40-link review](GARMIN_ECOSYSTEM_REVIEW.md) identifies which findings came from a README,
which were confirmed in source, and what changed in v0.28.0. Runtime review covered the
Garmin Connect adapter, read-only SQLite and current FIT references, and the existing
History rendering path. Live coverage and the full repository line audit remain open.

## v0.29.0 handoff check

A reviewer can follow the running chart, glossary, local CSV, and model fallback
through the [review index](REVIEW_START_HERE.md). The [feature ledger](GARMIN_ECOSYSTEM_REVIEW.md)
pairs each supplied GitHub link with an exact implementation artifact or documented
constraint. The independent review checked all 88 pinned tree and file paths and
corrected earlier license classifications. The repository remains private and now
has an explicit [MIT license and author attribution](../LICENSE).

The release check passed 289 tests and the 36-month synthetic replay. The Mac archive,
physical iPhone and the wider manual audit are separate from this release check.

## 25 November continuation audit

The inventory is pinned to release commit `569eedf8325a50c32199cc5c51cca35cc2502ea5`
(v0.29.0). All 173 tracked paths were reconciled against the existing register. The preceding
register covered 172 of them. The missing `tests/test_archive_audit.py` is now recorded. All
85 Python files, totaling 19,858 lines, parsed as Python. The eight package console-script
targets resolve to functions, and the server declares 57 MCP tools. The 289 relative Markdown
file-link occurrences resolve within the pinned tree. The automated pass covers syntax, paths,
and registration. It does not establish behavior of all branches or verify external link
availability and Markdown anchors.

| Pinned code reviewed | Caller, behavior and verification |
|---|---|
| [Auto-update, lines 24–110](../src/garmin_mcp/autoupdate.py#L24) | The sync CLI honors no-update and repair status. The updater checks tracked edits and ancestry, pulls with fast-forward only, persists a pending-install marker before changing the checkout, and retains the marker on install failure. Targeted tests cover the disabled, diverged, failed-install, and subsequent retry paths. The real launchd checkout and package environment remain open. |
| [Sync, lines 70–429](../src/garmin_mcp/sync.py#L70) | Scheduled, forced, historical and skipped-fetch paths share the refresh path. Incomplete source or derived-load results preserve the retry flag. Fetch success can still mean a source returned no measurement. The dashboard refresh can retry on a skipped fetch. Targeted tests cover both retry paths and day boundaries. |
| [Archive import, lines 122–318](../src/garmin_mcp/importer.py#L122), [FIT retention and write, lines 42–105 and 208–223](../src/garmin_mcp/fit.py#L42) | The import keeps existing API activity summaries, matches activity FIT by unique nearest start time, retains changed bytes by hash, and uses a write savepoint for decoded activity data. Monitoring messages need a separate preview and source reconciliation. Imports commit completed phases, so an uncaught error need not undo earlier successful phases. |
| [Normalization, lines 144–213 and 408–493](../src/garmin_mcp/normalize.py#L144), [SQLite store, lines 159–264](../src/garmin_mcp/db.py#L159) | Reviewed dated versus rolling resting pulse, raw-row upserts and field-by-field source precedence. A synthetic SQLite authorizer denied a replacement insert and reproduced loss of the prior first normalized table despite rollback. The new savepoint protects all normalized table replacements. Regression checks deny writes into the first and a later table, confirm the previous rows survive, then verify a successful retry. |
| [Archive audit, lines 12–67](../src/garmin_mcp/archive_audit.py#L12), [CSV, lines 24–110](../src/garmin_mcp/archive_export.py#L24), [Verifier, lines 210–344](../src/garmin_mcp/verify.py#L210) | Traced stored versus usable wellness days, recorded FIT reference versus reachability and decode status, new-file-only export, temporary replay and default verifier behavior. Explicit audit, replay and CSV inputs are read-only. The default verifier opens the configured database normally and rebuilds tables. Fixtures use generated records. |
| [Pages publishing, lines 35–234](../src/garmin_mcp/publish.py#L35), [MCP workout paths, lines 315–357](../src/garmin_mcp/server.py#L315) | The opt-in publisher validates production and preview Access policy, checks anonymous redirects and stages the latest HTML under a lock. Fake-provider tests cover successful guarded upload, unsafe configuration, retries, publication ordering and deduplication. Workout list/delete and explicit upload use Garmin Connect. This continuation did not deploy a snapshot or mutate Garmin. |

The independent baseline operations run passed 63 tests across self-update, publishing, archive
audit/export, import, storage history and sync. The normalized-table fix covers its own writes.
Derived activity-load and fitness tables still rebuild as the next operation under their existing
commit behavior. Guaranteeing atomic replacement for that separate generation needs its own
review, including settings reads that can invoke SQLite `executescript`.

The current release also received a focused manual trace of the following paths.

| Release code reviewed | Caller, behavior and verification |
|---|---|
| [Dashboard output and recommendation history](../src/garmin_mcp/dashboard.py#L3174), [evidence and comparison](../src/garmin_mcp/coach_review.py#L9) | Dashboard build uses the snapshot lock during replacement and records the current guidance after the ordinary build succeeds. It skips partial and historical builds and keeps background narration rebuilds out of guidance history. Local and iCloud copies are separate atomic replacements. Four fixtures cover recommendation changes, unavailable readings, wellness evidence and cadence follow-up. |
| [Ollama item selection and transport](../src/garmin_mcp/narrator.py#L523), [detached worker](../src/garmin_mcp/narrator.py#L845) | Post-run, Running, daily and Sunday requests have separate evidence and cache identity. Selection, drafted text and fixed fallbacks remain distinguishable. Superseded or retrying syncs cannot replace a newer dashboard. Mac timing, failure recovery and prose quality are owner acceptance. |
| [Chart interaction](../src/garmin_mcp/dashboard_interaction.py#L8) | HTML contains the responsive chart drawings. JavaScript initializes visible charts near the viewport or on keyboard focus, retaining the eager fallback without `IntersectionObserver`. The HTML still contains the underlying drawings and data and needs physical iPhone performance measurements. |

The exhaustive manual review of remaining analytics, renderer, prompt, and legacy branches is
open. The earlier register preserves past review evidence, and the pinned inventory and code
paths above identify the additional coverage for this release. Owner acceptance also remains
open for the private archive, Mac-scheduled operations, live Garmin, and the physical iPhone.

## Post-v0.30.0 manual audit

This pass started at `e8dc20b` (v0.30.0), with 183 tracked files including 92 Python files.
The line spans below cover code read and traced across its callers. Behavioral checks are
listed separately. The audit prioritizes paths that can change archive state, omit an update,
trigger a network request, or mislead a coaching decision.

| Path and reviewed lines | Behavior and evidence | Acceptance still open |
|---|---|---|
| [MCP server](../src/garmin_mcp/server.py#L1), 1–804 | Traced all local reads, settings, bedtime/plan/experiment writes, workout preview/list/delete, dashboard rebuild, weather opt-in and source sync through registration and dispatch. Bedtime acceptance already marks the dashboard stale in the same SQLite transaction. Unsupported workout actions previously fell through to a live listing, so routing now rejects them before network work. An isolated SDK 2 stdio session initialized, listed 57 tools, verified synthetic coverage and rejected a misspelled workout command. | Real desktop client and Garmin sessions on the owner's Mac. |
| [Client](../src/garmin_mcp/client.py#L1), 1–70, [login](../src/garmin_mcp/login.py#L1), 1–23, [config](../src/garmin_mcp/config.py#L1), 1–25 | Traced lazy Garmin auth, saved session reuse, one-time password/MFA input, timezone selection, default Qwen tag, and alternate data/DB paths. No credentials or Garmin account were needed for the workspace checks. | Owner session renewal, saved timezone and scheduler environment. |
| [Source interface](../src/garmin_mcp/sources/base.py#L1), 1–34, [source export](../src/garmin_mcp/sources/__init__.py#L1), 1–5, [Connect adapter](../src/garmin_mcp/sources/garminconnect_source.py#L1), 1–97, [Personal API adapter](../src/garmin_mcp/sources/personal_api.py#L1), 1–130 | Traced per-source daily versus window requests, the Connect extras filter, token refresh, bounded pagination, activity details and raw/FIT zip intake. Personal API fixtures verify expired token refresh, missing or blank credential handling and malformed pagination. | Actual source coverage, both live sessions and representative original FIT formats. |
| [Scheduled sync](../src/garmin_mcp/sync.py#L1), 1–450 | Reviewed request budgets, incremental windows, partial sync/retry, activity/detail/FIT paths, dashboard and publishing retry, and CLI gates. Garmin Connect-only now checks for new activities through the Connect session. A separate per-archive SQLite lock prevents concurrent runs from clearing one another's retry state while preserving archive reads and partial commits. Fixtures reproduced both issues and verify retries. The default early probe still uses the Personal API. | Configured launchd job, Windows Task Scheduler and live timing. |
| [Self-update](../src/garmin_mcp/autoupdate.py#L1), 1–110, [CI](../.github/workflows/ci.yml#L1), 1–23, [package config](../pyproject.toml#L1), 1–42, [environment template](../.env.example#L1), 1–16, [ignore rules](../.gitignore#L1), 1–10 | Traced editable install, re-exec, pending-install retries, pinned CI actions, package dependencies and declared commands. Manual one-year backfill now explicitly bypasses the schedule gate. The interactive MCP process loads `.env`. Scheduled auth uses the documented key/token files or environment passed to the job. | Actual launchd checkout, virtual environment, and install-failure recovery on the Mac. |
| [Pages publisher](../src/garmin_mcp/publish.py#L1), 1–242, [Mac deployment guide](../MAC_SETUP.md#L1), 1–270, [operations guide](OPERATIONS.md#L1), 1–175 | Traced opt-in configuration, Access policy verification, anonymous redirects, deployment locking, staged file, successful upload receipt, hosted evidence rebuild, and owner-only device checks. Publishing uses stand-in provider fixtures. Its latest preflight checks the root and the HTML path on production and preview hostnames. | Actual Access policy and preview/deployment URLs, owner sign-in and Home Screen refresh on physical Safari. |

The first focused operations run passed 72 tests across sync, workouts, Personal API,
self-update and publishing. A later result covered the new concurrency regression and the
selected source gate together, with both tests passing.

The analytics pass read 1,257 lines from nine complete files at the starting revision.

| Baseline file and reviewed lines | Manual review |
|---|---|
| [Recovery](../src/garmin_mcp/recovery.py#L1), 1–314, [daily focus](../src/garmin_mcp/daily_focus.py#L1), 1–125, [reading availability](../src/garmin_mcp/reading_availability.py#L1), 1–60, [wellness review](../src/garmin_mcp/wellness_review.py#L1), 1–85 | Traced incompatible and missing source rows, freshness labels, recovery flags, input validation, breathing fallback and explicit zero recovery time. Reviewed minimum support for nap and Body Battery comparisons. |
| [Scores](../src/garmin_mcp/scores.py#L1), 1–248, [signal context](../src/garmin_mcp/signal_context.py#L1), 1–99 | Traced default and override paths, age/HR inputs, score bounds, baseline date exclusion and paired eligibility for recovery-weight comparisons. |
| [Sleep review](../src/garmin_mcp/sleep_review.py#L1), 1–174, [bedtime experiment](../src/garmin_mcp/bedtime_experiment.py#L1), 1–82, [training plan](../src/garmin_mcp/training_plan.py#L1), 1–70 | Traced recorded sleep stages, wraparound clock summaries, wake-statistic windows, weekly target persistence/comparisons, dated plan matching and unusable activity durations. |

The 50-test analytics run covered recovery, scoring, sleep, bedtime, coaching and signal context.
The identical-clock regression checks that repeated wake times keep a zero spread.

| Archive and model code reviewed | Manual review |
|---|---|
| [Importer](../src/garmin_mcp/importer.py#L1), 1–343, [FIT](../src/garmin_mcp/fit.py#L1), 1–244, [monitoring preview](../src/garmin_mcp/monitoring_preview.py#L1), 1–194, [verifier](../src/garmin_mcp/verify.py#L1), 1–371, [archive export](../src/garmin_mcp/archive_export.py#L1), 1–110, [archive audit](../src/garmin_mcp/archive_audit.py#L1), 1–67, [wellness timeline](../src/garmin_mcp/wellness_timeline.py#L1), 1–112 | Traced file retention, parser transactions, monitored metric and timestamp reconciliation, usable date ranges, export overwrite protection and import continuation. Also traced [normalization](../src/garmin_mcp/normalize.py#L400) lines 400–528 and [SQLite store](../src/garmin_mcp/db.py#L192) lines 192–257 and 283–322. Sixty focused tests passed across import, FIT, storage history, preview, audit/export, normalization and sync. |
| [Narrator](../src/garmin_mcp/narrator.py#L378), 378–510, 519–782, 787–907 and 960 through EOF, [deep insight](../src/garmin_mcp/deep_insight.py#L19), 19–184, 195–348, 351–482 and 484 through EOF | Traced loopback, capability checks and transport, cache signatures, prompt-specific evidence eligibility, review, selection and canonical snapshot rebuilding. The tests cover scoped Sleep and post-run diagnostics without relying on the owner's records. The reviewed spans follow the working revision and omit some setup and evaluation branches. |
| [Dashboard](../src/garmin_mcp/dashboard.py#L74), collection, Today and Sleep composition, Running lead, day-history rendering, and snapshot build; [archive baseline](../src/garmin_mcp/baseline.py#L1), [running block](../src/garmin_mcp/running_block.py#L1), [matched effort](../src/garmin_mcp/run_evidence.py#L1) and [readiness benchmark](../src/garmin_mcp/readiness_benchmark.py#L1), full files | Traced archive-to-page as-of selection, what counts as a historical observation, waking and running recommendations, phase-specific comparisons and the shared checked-evidence view. Clear rest advice overrides the cadence cue and Running lead. The browser matrix exercised the reviewed Sleep source link, availability and post-run explanations. |
| [Health](../src/garmin_mcp/health.py#L45), sleep breakdown and pulse comparison, and [insights](../src/garmin_mcp/insights.py#L329), trend and daily brief | Traced malformed archived sleep payloads, source fallback for awake pulse, valid sleep windows, finite metric series, and the empty half of a one-reading trend. |

This is a manual pass through the named paths and ranges. Further current-revision review
is open for the remaining dashboard pages and CSS, the full running and running-dynamics
calculation chains, relationships and other insight calculations, rarely used external
conditions paths, extended load and fixture logic, remaining AI setup paths, and the
untested deployment environments above. The earlier file register records each path's
prior status and the automated inventory remains distinct from manual trace coverage.
Replaying multiple whole-export JSON snapshots with overlapping raw-range keys can still
produce repeated supersession history. Canonical replay ordering requires dated source
snapshots that establish which conflicting version was newer.

## v0.31.0 release check

Ruff and 343 tests passed on Linux. A 36-month synthetic archive replay produced no
broken internal links or duplicate IDs and left the source SQLite hash unchanged.
Chromium and WebKit passed eight responsive browser configurations spanning phone and
desktop widths and light and dark themes. The real local Qwen3.5 4B model passed
reviewed prose checks on fictional Today, Sleep and Running evidence in direct mode.
The owner's archive, Mac runtime, physical iPhone and private hosting remain separate
checks documented in [owner acceptance](OWNER_ACCEPTANCE.md).

## v0.30.0 release check

Ruff and all 311 tests passed. The 36-month synthetic replay found zero broken
fragment links or duplicate IDs and preserved the source database hash. Eight
Chromium/WebKit integrated layouts passed. The live structured coaching evaluation
accepted the expected model topic in two of three eligible examples. A grounded
rule replaced the lower-value third choice. See
[the 14-item execution status](../ROADMAP.md#25-november-execution-status) for
the separate checks on private data, devices and the remaining manual branches.
