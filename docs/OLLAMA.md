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

Use `--enable --model qwen3.5:9b --thinking` with an installed thinking-capable model, or
`--eval-insight --model qwen3.5:9b` to exercise the same flow on fictional readings. Add `--no-thinking` to that evaluation to compare
the direct mode separately. An existing
configuration without the flag keeps its current behavior. The same setting is available as
`ai_narrator(thinking=True)`. `--check` reports model support and interpretation coverage.

The daily interpretation uses recent and previous sleep and resting-heart-rate windows,
seven-day HRV, and the current day's qualifying matched run when available. It requires at
least two domains. Python supplies exact readings, comparable baselines and links. The model
chooses the comparison and writes an interpretation and a question about the next comparable
measurement. Python checks the citation coverage, number references and question wording.
A separate completion checks claims and the question's premises. The renderer labels accepted
output separately from deterministic guidance.
Reasoning traces do not appear in the snapshot or local response cache.

Thinking work runs first in a bounded background batch. The thinking draft defaults to ten
minutes. Set `--thinking-minutes 5` (1–30 minutes supported) to change it. Routine summaries
keep their faster path. A thinking call that cannot finish can fall back to a direct draft.
The worker can also make one direct revision after a draft fails a content or review check.
Each draft passes the same checks. Review and direct work share an extra allowance of up to
four and a half minutes per interpretation, with warm-up budgeted separately. A text model
without thinking support can use the direct path. Later builds can retry unfinished work.
Changing the draft budget gives the same evidence a fresh attempt.
[Ollama thinking controls](https://docs.ollama.com/capabilities/thinking)

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
  `last_insight_attempts` records mode and outcome labels by surface, without draft text or reasoning.
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

Use `--insight-case mixed-recovery`, `run-exception`, `longer-sleep`, or `sunday-review` with
`--eval-insight` to preview prompts without the archive. Add `--no-thinking` to compare direct
drafting without changing model settings. See the [model and audit notes](REPOSITORY_REVIEW.md).

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
