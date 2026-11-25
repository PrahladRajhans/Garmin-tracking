# Owner acceptance on the Garmin Mac

Run this from the Garmin Tracking checkout on the machine holding the private archive.
Replace the placeholder with the exact day shown for the Garmin Connect resting-pulse value.

```bash
.venv/bin/python -m garmin_mcp.owner_acceptance --pulse-date YYYY-MM-DD --expected-bpm 44 --replay-dashboard
```

The command opens the original SQLite database in read-only mode. The optional replay renders
on a temporary SQLite copy. Model checks use only loopback status, installed tags and local
model capabilities, without calling inference or sending health data. The JSON omits the date
entered, source values, activity identifiers, credentials, reasoning and file paths.

- `pulse` indicates whether the normalized estimate matches the expected value and which
  independently dated Garmin sources agree. A rolling-only export value never counts as a
  dated match. If the fields disagree, verify the exact date and measurement type in Garmin
  Connect. These flags check provenance for the watch estimate. An awake pulse measurement is
  a separate confirmation.
- `recent_36_calendar_months` counts months with normalized daily records ending in the
  archive's latest daily month. Check the usable days by signal to distinguish an archive
  spanning three years from continuous coverage. The FIT and intraday counts cover the full
  retained archive.
- `ollama` checks availability, cloud-disabled status, the installed selected model and
  thinking support. It does not check whether the model produced an accepted interpretation.
  Use the fictional Running evaluation described in [Ollama diagnostics](OLLAMA.md) for that.
- `dashboard_replay` checks up to 36 recorded months for missing links and duplicate anchors.
  Check the coverage counts alongside replay success to establish how many months were
  exercised. Physical Safari, reviewer acceptance on actual data, and scheduled delivery
  require separate checks on the owner's devices.
