# Local Ollama narrator

The narrator is off by default. Enable it on the Mac using [Mac setup](../MAC_SETUP.md#local-ai-narrator-optional).
Python calculates the numbers, decides what the dashboard recommends, and checks every sentence.
The saved dashboard can be read on a phone. Ollama runs on the computer that builds the file.

## Coverage

- Today uses current recovery facts, and Sleep uses the recorded night for the current snapshot.
- The runs with detail pages use FIT-derived pace, heart rate and cadence where available. Recent
  workouts use recorded Garmin duration, distance and average heart rate. This includes recent
  runs that only have a Garmin activity summary.
- An active experiment uses the numbers already reviewed by the rules in `trials.py`.
- The snapshot includes up to eight FIT run pages and eight other workouts from the latest
  30 days. The detached worker works within a 20-second per-item and 120-second batch budget.
  Missing summaries can be processed on later complete syncs. Existing rules and data display immediately.

## Changes to review

1. For each new fact, check the deterministic source, units, missing readings and allowed sentence
   variants. Keep dates, routes, names, notes and activity IDs out of model prompts.
2. Keep inference at loopback, require cloud-disabled status and use the local model suffix.
   Review these requirements when upgrading Ollama. [Ollama documentation](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features)
3. Run the mocked test suite and check that a slow, unavailable or invalid response leaves the
   original dashboard usable. Use fictional data for live model tests.
4. Update this page, the metrics rules and changelog when changing scope, privacy or validation.
   Record device acceptance separately from cloud workspace verification.

See [exact rules](../METRICS.md#optional-local-narration-v0220) and [review status](../HANDOVER.md#latest-changes-for-reviewers).
