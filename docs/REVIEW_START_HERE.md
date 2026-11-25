# Independent review of the Garmin dashboard

Read [HANDOVER](../HANDOVER.md) for context and [AGENTS](../AGENTS.md) for repository rules.
The [roadmap](../ROADMAP.md) is the open work queue. The [changelog](../CHANGELOG.md) records
changes. [Garmin sources](GARMIN_DATA_REVIEW.md), [formulas](../METRICS.md) and
[architecture](../ARCHITECTURE.md) define what the software can claim.

| Follow a reading | Review these files in order |
|---|---|
| Sync and raw provenance | [sync](../src/garmin_mcp/sync.py), [import](../src/garmin_mcp/importer.py), [normalization](../src/garmin_mcp/normalize.py) |
| Daily pulse and archive coverage | [archive windows](../src/garmin_mcp/baseline.py), [history collection](../src/garmin_mcp/dashboard_history.py), [rendering](../src/garmin_mcp/dashboard.py), [coverage and pulse tests](../tests/test_signal_context.py) |
| Ecosystem decisions and archive checks | [40-link review](GARMIN_ECOSYSTEM_REVIEW.md), [audit](../src/garmin_mcp/archive_audit.py), [timeline decoder](../src/garmin_mcp/wellness_timeline.py), [tests](../tests/test_archive_audit.py) |
| Sleep and recovery | [sleep review](../src/garmin_mcp/sleep_review.py), [sleep need and shortfall](../src/garmin_mcp/recovery.py), [tests](../tests/test_recovery.py) |
| Patterns and reviewed AI | [engine](../src/garmin_mcp/engine.py), [evidence and validation](../src/garmin_mcp/deep_insight.py), [worker](../src/garmin_mcp/narrator.py), [AI configuration](OLLAMA.md) |
| Rendering and delivery | [dashboard interaction](../src/garmin_mcp/dashboard_interaction.py), [UI review](UI_REVIEW.md), [Mac setup](../MAC_SETUP.md), [publishing](../src/garmin_mcp/publish.py) |

Run `ruff check .` and `pytest`. Replay a local archive with `garmin-mcp-verify --replay-dashboard`
to render each of the last 36 recorded months from a disposable copy and check page links.
For provenance tests, use synthetic dated-versus-rolling pulse inputs and inspect disagreements
between the two live sources. If the Mac archive is available, compare the date for the reported
44 bpm in Garmin Connect, saved sources and the page. Exercise the Sleep week with a missing
date, month/year with time to support a trend, and archive baselines with an entirely missing metric.
Before a second repo-wide sweep, start from [the file register](repository-review-queue.tsv).
