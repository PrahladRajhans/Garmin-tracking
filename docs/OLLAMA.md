# Local Ollama narrator

The narrator is off by default. Enable it on the Mac using [Mac setup](../MAC_SETUP.md#local-ai-narrator-optional).
Python calculates the numbers and training guidance, qualifies findings for the dashboard, and
checks the model's response. The saved dashboard can be read on a phone. Ollama runs on the
computer that builds the file.

## Coverage

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
- The worker has a 20-second standard item limit, 35 seconds for thinking-capable tags, and a 120-second batch limit. Enabling, manual
  builds, and scheduled runs can start or retry it, including when Garmin downloads are
  skipped. The dashboard renders immediately, and the worker applies checked results only
  to the snapshot it started from. The next eligible worker can apply previously cached results.
- Use `garmin-mcp-narrator --check` for loopback availability, cloud-off confirmation,
  installed model, sync state and cache coverage by surface. The check sends no health facts.
  `cache_matches_dashboard` indicates whether the accepted cache is reflected in the local HTML.
  Invalid selections are cached as rejected for that prompt and model. New evidence, prompt
  rules or a different model get a fresh attempt. Service failures and timeouts remain pending.

## Runtime compatibility and wording

The worker confirms cloud-off status, reads model metadata with `/api/show`, and preloads the
model with an empty generation before sending facts. It uses the local suffix, bounds context,
requests `think: false` on thinking-capable models, and parses only `response`.
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
