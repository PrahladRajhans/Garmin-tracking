# Preview a Garmin wellness FIT file

Run against the local archive and a Garmin monitoring FIT file. Add `--include-dates`
to see each metric's local dates and counts as well as the totals.

```sh
.venv/bin/garmin-mcp-verify --preview-wellness-fit "/path/to/WELLNESS.fit"
.venv/bin/garmin-mcp-verify --preview-wellness-fit "/path/to/WELLNESS.fit" --include-dates
```

The command opens the input file and SQLite archive read-only. It makes no Garmin request
and does not import the file, rebuild derived tables or change the dashboard. Reports omit readings,
exact timestamps, paths, device identifiers and record details. The optional dates are personal
metadata.

If you also want to keep the original, explicitly add `--retain`. Only an integrity-checked
monitoring FIT can be retained. Its exact bytes are saved with a content-hash filename under
`$GARMIN_DATA_DIR/monitoring-fit` (default: `~/.garmin-mcp/monitoring-fit`). Retained files are
owner-only and a repeat call reuses an identical copy. This opt-in only writes the raw file.
The comparison and SQLite archive remain read-only.

- **Candidate gap** means a decoded FIT reading has no comparable saved reading at the same
  key. That does not establish that the entire day is missing. The sources may sample at different
  times.
- **Overlap** means one unambiguous value on each side at the same key. Agreements and
  disagreements count exact numeric comparisons, with no resampling or tolerance adjustment.
- **FIT conflict or archive conflict** means the values on that side disagree at a single key. These
  keys are withheld from both the gap count and overlap comparison. The preview preserves conflicting
  duplicates for this check even when the display shows only one value per timestamp.

Pulse, stress and Body Battery use the exact timestamp as their key. Pulse checks the saved
daily Garmin Connect and Personal API raw pulse streams. Stress and Body Battery use the existing
saved wellness timeline decoder. The FIT-side Body Battery comparison requires a standard Health
Snapshot Body Battery message decoded by the Garmin SDK. Proprietary and unknown fields are
left alone.

Resting pulse compares only FIT `current_day_resting_heart_rate` against the normalized archive
reading for the configured local date. FIT `resting_heart_rate` is a separate value and is excluded.
The preview cannot confirm which archive source produced the reported 44 bpm. Use the
[owner acceptance command](OWNER_ACCEPTANCE.md) for source reconciliation on that date.

Monitoring pulse samples with a short timestamp are recovered only when a previous full
monitoring timestamp anchors the rollover and a decoded full timestamp bounds the result.
Samples without those bounds are counted and excluded. Activity and workout FIT files are
rejected. This preview does not derive steps from cumulative counters, infer naps or fill in
unknown message fields. It reports counts for unexamined message types without their contents.

## What was checked

The preview uses the official Garmin FIT SDK. The pinned GarminDB fixture verified actual
monitoring message shapes. Scanning it against an empty synthetic archive decoded 130 unique
pulse timestamps, 64 unique stress timestamps and one current-day resting pulse key. It contained
no standard SDK Body Battery reading. Body Battery comparisons, blocked imports, source
conflicts, missing readings, local-date boundaries, timestamp rollover and repeat retention are
covered with synthetic SDK-encoded tests. No upstream FIT bytes were added to this repository. A representative
owner file and archive are still needed before a state-changing import policy can be validated.
[Garmin FIT SDK](https://github.com/garmin/fit-python-sdk) ·
[GarminDB pinned fixture](https://github.com/tcgoetz/GarminDB/blob/392beb49cfba7599b5a9ed4d195267cf79ec51b0/test/test_files/fit/monitoring/anonymized_WELLNESS.fit) ·
[GarminDB monitoring implementation](https://github.com/tcgoetz/GarminDB/blob/392beb49cfba7599b5a9ed4d195267cf79ec51b0/garmindb/monitoring_fit_file_processor.py)
