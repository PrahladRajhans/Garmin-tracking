# Local Ollama narrator

The narrator is off by default. Enable it on the Mac using [Mac setup](../MAC_SETUP.md#local-ai-narrator-optional).
Python calculates the numbers and training guidance, qualifies findings for the dashboard, and
checks the model's response. The saved dashboard can be read on a phone. Ollama runs on the
computer that builds the file.

The shared default model is `qwen3.5:4b`. On upgrade, saved settings using the previous
`qwen2.5:3b-instruct` default move to Qwen3.5 once. Other model tags and the existing
enabled and thinking settings are preserved. A separate `--model` selection made after
the upgrade is saved normally. If Qwen3.5 has not been installed, download it with
`ollama pull qwen3.5:4b`. The dashboard can still render its calculated guidance while the
local model is unavailable.

The v0.26.1 live Linux smoke test accepted all five fictional routine summaries with
Qwen3.5 4B (median generation 13.36 seconds). The open-ended running test in v0.26.0
was withheld. The [current priorities](../ROADMAP.md#current-priorities) track the Mac
rollout, per-surface checks, reviewed weekly story and dashboard status detail.

The footer reports the last accepted result for the selected model and whether the
current snapshot is waiting, blocked by the local-only check, missing evidence, or withheld.
The optional Sunday review uses recorded training and sleep facts. Its next focus and
fallback remain deterministic. Run `--eval-insight --insight-case sunday-review --no-thinking`
on fictional evidence. The output distinguishes format and citation failures from the review verdict.

## Coverage

### Thinking insights

Daily and Sleep thinking can use the average sleep shortfall for two weeks with at least five
usable nights each, and a flagged Garmin resting estimate with a qualified personal 28-day
comparison. Longer qualified pulse medians add context without sending individual dates.
Rule-written pulse verification guidance remains outside model output. The archive is read
locally and only selected summaries enter the allowlist. See [metrics](../METRICS.md#day-readings-sleep-shortfall-and-archive-baselines).


Use `--enable --model qwen3.5:9b --thinking` with an installed thinking-capable model, or
`--eval-insight --model qwen3.5:9b` to exercise the same flow on fictional readings. Add `--no-thinking` to that evaluation to compare
the direct mode separately. An existing
configuration without the flag keeps its current behavior. The same setting is available as
`ai_narrator(thinking=True)`. `--check` reports model support and interpretation coverage.

The daily interpretation uses recent and previous sleep and resting-heart-rate windows,
seven-day HRV, and the current day's qualifying matched run when available. It requires at
least two domains. Python supplies exact readings, comparable baselines and links. The model
can write an interpretation and a question about the next comparable measurement.
Python checks the citation coverage, number references and question wording.
If only the question is unusable, Python substitutes a neutral repeat check from the cited
evidence. A separate completion checks the observation and the final question.
If drafting times out or the prose fails review, Ollama can choose an ID for one eligible pair
of current readings. Python renders both supplied statements verbatim with their evidence links
and a repeat-check question. The pair always spans two evidence categories. A rejected draft
never enters the fallback prompt or reaches the dashboard. An explicit abstention stays empty.
Reasoning traces do not appear in the snapshot or local response cache.

Thinking work runs first in a bounded background batch. The thinking draft keeps its
2,450-token allowance and defaults to ten minutes. Set `--thinking-minutes 5` (1–30 minutes
supported) to change its time limit. After a thinking timeout, the worker can attempt one short
direct draft when enough time remains for review and the comparison fallback. The direct
writing path can also make one correction before selection. Ollama writes one observation
and cites two current domains. Python supplies its neutral next question, and a separate
Ollama request reviews the observation against the readings. Broad conclusions about
fitness or recovery get withheld when only specific markers were measured. The job
reserves up to 45 seconds for exact-source selection, with warm-up budgeted separately.
A text model without thinking support can use the direct path. Later builds can retry unfinished
work when the service also fails to return a comparison.
Changing the draft budget gives the same evidence a fresh attempt.
[Ollama thinking controls](https://docs.ollama.com/capabilities/thinking)

### Sleep and the written-coaching check

Sleep has a separate review when the current snapshot includes a recorded night and
there is qualified sleep and recovery evidence. The review links to Sleep and Recovery.
It can contrast the week's sleep duration with the measured change in HRV or resting
pulse without turning either into a broader recovery diagnosis. This review uses the same
configured thinking allowance and bounded direct retry as Today and Running. The worker
queues Running ahead of the additional Sleep review. Missing night data and incomplete
snapshots suppress it.

To exercise the reviewed drafting path on fictional readings:

```bash
for case in today-written sleep-written running-block; do
  garmin-mcp-narrator --eval-insight --no-thinking --insight-case "$case" --model qwen3.5:4b
done
```

`reviewed_prose: true` identifies an accepted draft after the independent review completion.
A successful exact-reading fallback uses `mode: selected_comparison` with
`reviewed_prose: false`. The two outcomes are counted separately.

On 25 November 2026, Qwen3.5 4B with Ollama 0.40.17 on Linux CPU passed the direct-writing
checks for Today (89.96 seconds), Sleep (86.55 seconds), and Running (58.68 seconds), after
warm-up. The first drafts for Today and Sleep failed the numeric citation gate. The checked
revisions contrasted the latest moving heart rate with stable resting heart rate and longer
recorded sleep with lower HRV respectively. Running's first draft contrasted more running
days with a latest run whose moving pulse stayed in its earlier matched range. All three
produced reviewed prose with synthetic inputs. The owner's archive and Mac were unavailable.

### Post-run evidence check

The latest detailed run has a separate review when qualified measurements are available.
Its compact packet contains at most three checked observations. It uses cadence at matched
pace and grade within the run, moving pulse across earlier comparable runs, and recorded time
near the same configured cadence cue on this run and the latest attempt from an earlier date.
Each supplies units and the comparison window or sample size. The model receives no run IDs,
dates, routes, or notes.

Ollama chooses one numeric ID in a direct, 45-second request. Python rejects stable readings
when the packet has a measured change or a repeated cue. It uses the accepted observation
verbatim, with an alternative to consider, a question for the next comparable run and a link
to the recorded evidence. Cadence-cue exposure describes time at that cadence. Comparing
comfort or performance needs separate evidence. Pulse comparisons leave room for weather and
wrist-sensor fit. The dashboard uses a rule-written review while the model is off or pending,
and when the response fails validation. Thin or stale data does not qualify.

For fictional quality checks, run:

```bash
for case in post-run-cue post-run-outlier post-run-form post-run-thin; do
  garmin-mcp-narrator --eval-insight --insight-case "$case" --model qwen3.5:4b
done
```

`quality_pass` compares the model's accepted topic with the expected check. `dashboard_topic`
also shows what the local rule would display after a withheld or interrupted choice. The
thin case expects `insufficient_evidence` and does not contact the model. A returned status
of `accepted` shows a grounded choice. The expected topic separately tests its usefulness.

On 25 November 2026, local Qwen3.5 4B noticed the repeated cadence cue and the moving-pulse
outlier in 19.52 and 17.22 seconds after warm-up. It chose a stable pulse over a meaningful
late cadence change in the third case. The final guard withheld that choice and returned the
rule-written cadence review on the dashboard. The thin case made no model request. These
fictional Linux CPU checks cover topical usefulness and safe fallback separately from live
acceptance on the owner's Mac.

Before v0.27.1, Qwen3.5 4B on Linux spent
five minutes on the fictional matched-run case without completing its reasoning; its direct
retry was withheld after review. A direct mixed-recovery run was also withheld. Unit and
browser tests covered publication, review rejection, timeouts, and evidence links.
Mac latency and acceptance need separate verification before changing the active model.


The newest run can also ask the model to choose the next piece of evidence to check, if its
moving heart rate is outside the recorded span of similar efforts. The prompt uses matched
count, difference, span and eligible checks. The response is an ID, and the checked option
and reason appear as an evidence check. The model does not change the training suggestion.
A number-only filter would still accept fabricated causes or advice with valid numbers.


- Today and Recovery share one current recovery summary. Sleep uses the recorded night for the
  current snapshot. Training uses the current seven-day review's load, qualifying workouts and
  available sleep average.
- When there are at least two eligible Today findings, Ollama weighs their relevance to recovery
  and their evidence. It chooses which finding to show first. Python validates the returned
  choice against the supplied list and displays the original finding and its evidence. This is
  skipped when training is paused or the snapshot is stale or incomplete.
- The runs with detail pages use FIT-derived pace, heart rate and cadence where available. Recent
  workouts use recorded Garmin duration, distance and average heart rate. This includes recent
  runs that only have a Garmin activity summary.
- An active experiment uses the numbers already reviewed by the rules in `trials.py`.
- The snapshot includes up to eight newest FIT run pages and eight other workouts from the
  30-day History detail window. Running links to the narrated run detail pages. Body, Patterns,
  Trends and History provide calculations, source rows and links to the detail pages.
- Routine requests have a 20-second standard item limit, or 35 seconds for thinking-capable tags.
  Routine batches are limited to 120 seconds. Enabling, manual
  builds, and scheduled runs can start or retry it, including when Garmin downloads are
  skipped. The dashboard renders immediately, and the worker applies checked results only
  to the snapshot it started from. The next eligible worker can apply previously cached results.
- Use `garmin-mcp-narrator --check` for loopback availability, cloud-off confirmation,
  installed model, sync state and cache coverage by surface. The check sends no health facts.
  `cache_matches_dashboard` indicates whether the accepted cache is reflected in the local HTML.
  `last_insight_attempts` records mode, stage, outcome and whether a question needed replacement,
  without draft text or reasoning.
  Invalid selections are cached as rejected for that prompt and model. New evidence, prompt
  rules or a different model get a fresh attempt. Service failures and timeouts remain pending.

## Voice, lenses, and carry-over

Copy [the example profile](../config/narrator-prompt.example.json) to `narrator-prompt.json`
beside the active SQLite file. The voice and daily focus apply to every interpretation.
The sleep or running focus adds instructions for the selected topic.

Running has a separate `running_review` lens. With local narration enabled, it can review
completed four-week running frequency, second-half pace and pulse, matched effort, or a
cadence reading outside its observed matched span. It needs at least two qualifying categories.
It uses thinking when enabled and supported. Both the review and the daily interpretation
get a bounded opportunity to run without delaying initial HTML generation. Python supplies
the next-run action and source links. The model writes the interpretation and test question.

`--eval-insight --insight-case running-block` exercises this prompt on fictional data.
In live Linux direct-mode tests, Qwen2.5 3B Instruct produced one reviewed observation in
43 seconds. Qwen3.5 4B's result was withheld after 67 seconds. Compare the tags through
several cases on the Mac before choosing one. These results used no owner data.
Keep personal names and free-form health notes out of the profile. Invalid profiles fall back
to built-in text and `--check` reports which profile is active. Rebuild after editing to refresh
the snapshot. The model writes its own observation. The evidence, citation rules, and review
remain in code.

The archive stores only up to two eligible factual readings from each successful review.
One earlier reviewed date, within 14 days, can inform a later prompt. Older rows are pruned
on successful writes. Earlier evidence is labeled and cannot replace the required two current
domains. No generated narrative or reasoning is replayed. Ollama keeps model weights warm
for requests in a batch; that does not itself preserve the athlete's history between requests.

Use `--insight-case dated-health`, `mixed-recovery`, `run-exception`, `running-block`,
`longer-sleep`, or `sunday-review` with `--eval-insight` to preview prompts without the archive.
Add `--no-thinking` to compare the direct writing path or `--selection-only` to measure just
the fallback without changing model settings. A successful selection reports
`insight.mode = "selected_comparison"` and `outcome = "grounded_selection"` with elapsed
generation time, excluding warm-up. The numbered pair must contain two current categories and
preserve both source statements. See the [model and audit notes](REPOSITORY_REVIEW.md).

## Where to make changes

| Change | Location |
|---|---|
| Use a different local model or draft budget | `garmin-mcp-narrator --model … --thinking-minutes …` and `--check` |
| Change the coaching voice or focus | Local `narrator-prompt.json` and the fictional evaluations above |
| Add a measured signal or benchmark example | [Evidence and fixtures](../src/garmin_mcp/deep_insight.py). Qualify the reading, choose its evidence link, and cover sparse data. |
| Change model transport, acceptance or cache settings | [Background narrator](../src/garmin_mcp/narrator.py) and the local response tests |
| Change how the insight or links appear | [Today renderer](../src/garmin_mcp/dashboard.py) and [UI review](UI_REVIEW.md) |

## Runtime compatibility and wording

The worker confirms cloud-off status, reads model metadata with `/api/show`, and preloads the
model with an empty generation before sending facts. It uses the local suffix, bounds context,
requests `think: false` on routine calls to thinking-capable models, and parses only `response`.
[Thinking controls](https://docs.ollama.com/capabilities/thinking) ·
[Generate API](https://docs.ollama.com/api/generate).

A response may cite one or two checked clauses per sentence. It can combine supported clauses
with “and” or “while” and normalize numerical formatting. Complete clause checks reject new
causes, advice or uncited quantities. Invalid optional wording falls back to the selection;
invalid selections fall back to the deterministic dashboard. Sunday review and plan actions come
from Python. The prompt excludes check-in notes, routes, names, raw GPS, and dates.

`--eval --models qwen2.5:3b-instruct,qwen3.5:4b` ran five fictional cases per model on Linux.
Both accepted 5/5 under budget. Median generation was 6.56 s for Qwen2.5 and 17.35 s for
Qwen3.5. The recommendation favors speed among models that meet the acceptance threshold.
The small benchmark is a compatibility check, with Mac and other model tags still to verify.

## Verification

On 24 November 2026, Ollama 0.40.17 and the local Qwen2.5 3B Instruct model accepted every
eligible item from a synthetic archive built via MCP (20 of 20). The saved snapshot matched its
simulated iCloud copy. Disabling removed the AI results from both files. A separate fixture
covered the experiment summary and verified that Today's chooser favored several nights of
direct sleep evidence over an association. These runs used Linux. The owner's Mac, launchd
job and iCloud and iPhone path remain in the [roadmap](../ROADMAP.md).

On the v0.27.0 fictional Sunday case, Qwen3.5 4B first treated workout count as training volume.
A later draft compared the correct quantities and omitted the citation for the previous four
weeks. During the v0.27.1 repair, an intermediate model review also accepted a question about
unrecorded tiredness. The wording gate now checks for that premise before the model reviewer.
The weekly display retains its rule-written summary and dated links when no draft passes.

On the v0.27.1 candidate with Ollama 0.40.17 and local Qwen3.5 4B, the mixed-recovery and
matched-run exception direct drafts passed. The Sunday launch with a five-minute thinking
budget completed with an accepted direct fallback after 341 seconds end to end. The initial
thinking draft hit its time budget. These checks used fictional readings on Linux CPU.
The running-block trace also showed that Qwen used "felt steady" when it had a recorded
moving pulse comparison. The Running prompt now asks for measured directions and time windows.
Changing the shared observation instructions caused a Sunday regression in the Linux fixture.
Running-specific wording is kept in its own prompt so the tested Sunday wording is preserved.

On 25 November 2026, Ollama 0.40.17 and Qwen3.5 4B on Linux CPU accepted all six fictional
comparison-selection cases. Generation took 12.11–22.75 seconds after warm-up. On the
dated-health case, the final 2,450-token settings exhausted a one-minute thinking budget
and then returned an exact selected comparison in 85.39 seconds after warm-up.
The selected statements retained the sleep shortfall, usable-night counts, and the dated
resting-pulse baseline. The test establishes availability of the checked fallback.
Acceptance of freeform thinking prose and performance on the owner's Mac remain
separate checks.

## Changes to review

1. For each new fact, check the deterministic source, units, missing readings and allowed sentence
   variants. The model returns IDs and may return cited wording. Each clause has to match the cited meaning; invalid wording falls back to checked selection.
   Findings offered for prioritization must come from the deterministic daily brief.
   Keep dates, routes, names, notes and activity IDs out of model prompts.
2. Keep inference at loopback, require cloud-disabled status and use the local model suffix.
   Review these requirements when upgrading Ollama. [Ollama documentation](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features)
3. Run the mocked test suite and check that a slow, unavailable or invalid response leaves the
   original dashboard usable. Use fictional data for live model tests.
4. Update this page, the metrics rules and changelog when changing scope, privacy or validation.
   Record device acceptance separately from cloud workspace verification.

See [exact rules](../METRICS.md#optional-local-narration-v0220) and [review status](../HANDOVER.md#latest-changes-for-reviewers).
