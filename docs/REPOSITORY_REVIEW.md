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
